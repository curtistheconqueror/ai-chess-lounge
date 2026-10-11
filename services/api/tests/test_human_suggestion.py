import asyncio

import pytest
from fastapi.testclient import TestClient
from lounge_api.adapter_prompt import move_prompt
from lounge_api.adapters import AdapterRegistry, ScriptedPlayerAdapter
from lounge_api.domain import MatchTransitionRejected, StalePosition
from lounge_api.main import create_app
from lounge_api.manager import GameManager
from lounge_api.models import CreateGameRequest, HumanSuggestionRequest, OpponentKind
from lounge_api.openai_compatible_adapter import OpenRouterChatAdapter, VLLMChatAdapter
from lounge_api.persistence import DatabaseStore
from lounge_api.player_protocol import AssistanceDivision, PlayerConfiguration
from test_manager import FakeEngine, scripted_player


class IndependentAgent(ScriptedPlayerAdapter):
    requests = None

    async def choose_move(self, request, player):
        self.requests = request
        return await super().choose_move(request, player)


def test_advice_survives_reload_and_ai_can_choose_differently(tmp_path):
    async def run():
        adapter = IndependentAgent()
        m = GameManager(
            engine=FakeEngine(),
            store=DatabaseStore(f"sqlite+aiosqlite:///{tmp_path / 'advice.db'}"),
            adapters=AdapterRegistry([adapter]),
            schedule_agents=False,
            schedule_timeouts=False,
        )
        await m.start()
        try:
            game = await m.create(
                CreateGameRequest(
                    opponent=OpponentKind.HUMAN,
                    white_player=scripted_player("Independent AI", "d2d4"),
                    start_paused=True,
                )
            )
            before = await m.snapshot(game.id)
            advised = await m.consultation.suggest_to_agent(
                game.id, HumanSuggestionRequest(move="e2e4", expected_revision=before.revision)
            )
            assert advised.fen == before.fen and advised.moves == []
            assert advised.clock.white_remaining_ms == before.clock.white_remaining_ms
            assert advised.consultations[-1].status == "ready"
            with pytest.raises(StalePosition):
                await m.consultation.suggest_to_agent(
                    game.id, HumanSuggestionRequest(move="g1f3", expected_revision=before.revision)
                )
            m.games.clear()
            reloaded = await m.snapshot(game.id)
            assert reloaded.consultations[-1].move == "e2e4"
            await m.resume(game.id, reloaded.revision)
            m._schedule_agents_enabled = True
            m._schedule_agent_runner(await m.get(game.id))
            await m.wait_for_automation(game.id)
            played = await m.snapshot(game.id)
            assert played.moves[0].uci == "d2d4"
            assert adapter.requests._human_suggestion == "e2e4"
            assert "you retain final move authority" in move_prompt(adapter.requests)
            assert played.moves[0].player_metadata.division is AssistanceDivision.HUMAN_AI_TEAM
            assert played.consultations[-1].status == "played"
            assert "Human suggestion to AI" in played.pgn
            assert "human.suggestion" in [e.type for e in await m.events(game.id)]
            await m.reset(game.id)
            assert not (await m.snapshot(game.id)).consultations
        finally:
            await m.close()

    asyncio.run(run())


@pytest.mark.parametrize("action", ["clear", "seat", "resume_pause", "reset"])
def test_advice_is_fenced_by_lifecycle_and_seat(tmp_path, action):
    async def run():
        m = GameManager(
            engine=FakeEngine(),
            store=DatabaseStore(f"sqlite+aiosqlite:///{tmp_path / 'fences.db'}"),
            schedule_agents=False,
            schedule_timeouts=False,
        )
        await m.start()
        try:
            game = await m.create(
                CreateGameRequest(
                    opponent=OpponentKind.HUMAN,
                    white_player=scripted_player("AI", "d2d4"),
                    start_paused=True,
                )
            )
            with pytest.raises(MatchTransitionRejected):
                await m.consultation.suggest_to_agent(
                    game.id, HumanSuggestionRequest(move="e2e5", expected_revision=game.revision)
                )
            snap = await m.consultation.suggest_to_agent(
                game.id, HumanSuggestionRequest(move="e2e4", expected_revision=game.revision)
            )
            if action == "clear":
                await m.consultation.suggest_to_agent(
                    game.id, HumanSuggestionRequest(expected_revision=snap.revision)
                )
            elif action == "seat":
                await m.change_seat(
                    game.id, "white", PlayerConfiguration.human("white"), snap.revision
                )
            elif action == "resume_pause":
                snap = await m.resume(game.id, snap.revision)
                with pytest.raises(MatchTransitionRejected):
                    await m.consultation.suggest_to_agent(
                        game.id,
                        HumanSuggestionRequest(move="e2e4", expected_revision=snap.revision),
                    )
                await m.pause(game.id, snap.revision)
            else:
                await m.reset(game.id)
            assert (await m.get(game.id)).current_human_suggestion() is None
        finally:
            await m.close()

    asyncio.run(run())


def test_single_game_guard_and_suggestion_api(tmp_path):
    m = GameManager(
        engine=FakeEngine(),
        store=DatabaseStore(f"sqlite+aiosqlite:///{tmp_path / 'api.db'}"),
        schedule_agents=False,
        schedule_timeouts=False,
    )
    with TestClient(create_app(m)) as c:
        body = {
            "opponent": "human",
            "single_game": True,
            "start_paused": True,
            "white_player": scripted_player("AI", "d2d4").model_dump(mode="json"),
        }
        first = c.post("/api/games", json=body)
        assert first.status_code == 201
        game = first.json()
        assert game["lifecycle"] == "paused" and game["moves"] == []
        assert c.post("/api/games", json=body).status_code == 409
        url = f"/api/games/{game['id']}/human-suggestion"
        assert (
            c.post(url, json={"move": "a9a8", "expected_revision": game["revision"]}).status_code
            == 422
        )
        assert (
            c.post(url, json={"move": "e2e5", "expected_revision": game["revision"]}).status_code
            == 409
        )
        assert (
            c.post(url, json={"move": "e2e4", "expected_revision": game["revision"]}).status_code
            == 200
        )
        assert c.post(f"/api/games/{game['id']}/abort").status_code == 200
        assert c.post("/api/games", json=body).status_code == 201


def test_two_independent_agents_finish_one_game_without_browser_moves(tmp_path):
    async def run():
        m = GameManager(
            engine=FakeEngine(),
            store=DatabaseStore(f"sqlite+aiosqlite:///{tmp_path / 'two.db'}"),
            schedule_timeouts=False,
        )
        await m.start()
        try:
            game = await m.create(
                CreateGameRequest(
                    white_player=scripted_player("White fixture", "f2f3", "g2g4"),
                    black_player=scripted_player("Black fixture", "e7e5", "d8h4"),
                    start_paused=True,
                )
            )
            assert not game.moves
            await m.resume(game.id, game.revision)
            final = await m.wait_for_automation(game.id)
            assert final.status.value == "checkmate"
            assert [move.uci for move in final.moves] == ["f2f3", "e7e5", "g2g4", "d8h4"]
            assert all(move.actor.startswith("scripted:") for move in final.moves)
        finally:
            await m.close()

    asyncio.run(run())


@pytest.mark.parametrize("cost", [None, "0.2", -1, True, float("nan"), float("inf"), 0, 0.0023])
def test_openrouter_cost_is_reported_only_and_reasoning_not_added(cost):
    adapter = OpenRouterChatAdapter(api_key="unused-test-fixture")
    usage = {
        "prompt_tokens": 100,
        "completion_tokens": 50,
        "completion_tokens_details": {"reasoning_tokens": 30},
        "cost": cost,
    }
    metrics = adapter.normalize_usage(usage)
    assert metrics.output_tokens == 50 and metrics.reasoning_tokens == 30
    assert metrics.estimated_cost_usd == (
        cost if type(cost) in {int, float} and cost in {0, 0.0023} else None
    )
    assert VLLMChatAdapter(models=("local",)).normalize_usage(usage).estimated_cost_usd is None
