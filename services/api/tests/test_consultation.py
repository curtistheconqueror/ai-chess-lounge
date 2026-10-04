import asyncio
import io

import chess.pgn
import pytest
from lounge_api.adapters import AdapterError, AdapterRegistry, ScriptedPlayerAdapter
from lounge_api.domain import StalePosition
from lounge_api.manager import GameManager
from lounge_api.models import ConsultationRequest, CreateGameRequest, MatchState, OpponentKind
from lounge_api.persistence import DatabaseStore
from lounge_api.player_protocol import PlayerConfiguration
from lounge_api.provider_reliability import ProviderReliabilityController, ProviderRetryPolicy
from test_manager import FakeClock, FakeEngine, scripted_player
from test_provider_reliability import RecoveringProviderAdapter, provider_player


async def settle(manager):
    tasks = list(manager.consultation.tasks.values())
    if tasks:
        await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), 3)
        for task in tasks:
            if not task.cancelled():
                assert task.exception() is None


def test_advice_never_moves_and_human_confirmation_is_durable(tmp_path):
    async def run():
        url = f"sqlite+aiosqlite:///{tmp_path / 'advice.db'}"
        clock = FakeClock()
        manager = GameManager(
            engine=FakeEngine(),
            store=DatabaseStore(url),
            clock=clock,
            schedule_agents=False,
            schedule_timeouts=False,
        )
        await manager.start()
        try:
            game = await manager.create(CreateGameRequest(opponent=OpponentKind.HUMAN))
            pending = await manager.consultation.request(
                game.id,
                ConsultationRequest(
                    advisor=scripted_player("Coach", "e2e4"), expected_revision=game.revision
                ),
            )
            assert pending.moves == [] and pending.version == game.version
            await settle(manager)
            ready = await manager.snapshot(game.id)
            advice = ready.consultations[-1]
            assert advice.status == "ready" and advice.move == "e2e4"
            assert ready.fen == game.board.fen() and ready.moves == []
            clock.advance(seconds=4)
            thinking = await manager.snapshot(game.id)
            assert thinking.clock.white_remaining_ms == game.initial_time_ms - 4000
            assert '[Assistance "Human-AI Team exhibition"]' in thinking.pgn
        finally:
            await manager.close()
        manager = GameManager(
            engine=FakeEngine(),
            store=DatabaseStore(url),
            clock=clock,
            schedule_agents=False,
            schedule_timeouts=False,
        )
        await manager.start()
        try:
            recovered = await manager.snapshot(game.id)
            assert recovered.consultations[-1] == advice
            played = await manager.make_human_move(
                game.id,
                "e2e4",
                recovered.version,
                "consultation-retry-key",
                consultation_id=advice.id,
                consultation_revision=recovered.revision,
            )
            assert len(played.moves) == 1 and played.moves[0].actor == "human:white"
            assert played.consultations[-1].status == "played"
            repeated = await manager.make_human_move(
                game.id,
                "e2e4",
                recovered.version,
                "consultation-retry-key",
                consultation_id=advice.id,
                consultation_revision=recovered.revision,
            )
            assert len(repeated.moves) == 1
            parsed = chess.pgn.read_game(io.StringIO(played.pgn))
            assert "Coach" in parsed.comment and "e4" in parsed.comment
            await manager.reset(game.id)
            assert (await manager.snapshot(game.id)).consultations == []
            assert any(e.type == "consultation.ready" for e in await manager.events(game.id))
        finally:
            await manager.close()

    asyncio.run(run())


@pytest.mark.parametrize("change", ["move", "pause", "reset", "resign", "takeover", "cancel"])
def test_other_worker_supersedes_pending_advice_without_late_result(tmp_path, change):
    class Slow(ScriptedPlayerAdapter):
        def __init__(self):
            self.started, self.release, self.cancelled = (
                asyncio.Event(),
                asyncio.Event(),
                asyncio.Event(),
            )

        async def choose_move(self, request, player):
            self.started.set()
            try:
                await self.release.wait()
                return await super().choose_move(request, player)
            except asyncio.CancelledError:
                self.cancelled.set()
                raise

    async def run():
        url = f"sqlite+aiosqlite:///{tmp_path / 'race.db'}"
        adapter = Slow()
        first = GameManager(
            engine=FakeEngine(),
            store=DatabaseStore(url),
            adapters=AdapterRegistry([adapter]),
            schedule_agents=False,
            schedule_timeouts=False,
        )
        second = GameManager(
            engine=FakeEngine(),
            store=DatabaseStore(url),
            schedule_agents=False,
            schedule_timeouts=False,
        )
        await first.start()
        await second.start()
        try:
            game = await first.create(CreateGameRequest(opponent=OpponentKind.HUMAN))
            pending = await first.consultation.request(
                game.id,
                ConsultationRequest(
                    advisor=scripted_player("Slow", "e2e4"), expected_revision=game.revision
                ),
            )
            await asyncio.wait_for(adapter.started.wait(), 2)
            if change == "move":
                await second.make_human_move(game.id, "d2d4", game.version)
            elif change == "resign":
                await second.resign(game.id, color="white", position_version=game.version)
            elif change == "cancel":
                await second.consultation.cancel(
                    game.id, pending.consultations[-1].id, pending.revision
                )
            elif change == "takeover":
                paused = await second.pause(game.id)
                await second.change_seat(
                    game.id, "white", scripted_player("New seat", "e2e4"), paused.revision
                )
            else:
                await getattr(second, change)(game.id)
            await asyncio.wait_for(adapter.cancelled.wait(), 2)
            await settle(first)
            result = await second.snapshot(game.id)
            assert not any(c.status == "ready" for c in result.consultations)
            assert len(result.moves) == (1 if change == "move" else 0)
            assert not any(e.type == "consultation.ready" for e in await second.events(game.id))
        finally:
            adapter.release.set()
            await first.close()
            await second.close()

    asyncio.run(run())


@pytest.mark.parametrize("kind", ["illegal", "provider_failure", "deadline"])
def test_failed_advice_keeps_human_turn_running(tmp_path, kind):
    class Broken(ScriptedPlayerAdapter):
        async def choose_move(self, request, player):
            if kind == "provider_failure":
                raise AdapterError("SECRET provider payload must never be published")
            if kind == "deadline":
                await asyncio.Event().wait()
            return await super().choose_move(request, player)

    async def run():
        manager = GameManager(
            engine=FakeEngine(),
            store=DatabaseStore(f"sqlite+aiosqlite:///{tmp_path / 'failure.db'}"),
            adapters=AdapterRegistry([Broken()]),
            schedule_agents=False,
            schedule_timeouts=False,
        )
        await manager.start()
        try:
            game = await manager.create(CreateGameRequest(opponent=OpponentKind.HUMAN))
            advisor = scripted_player("Broken", "a1a8")
            advisor.settings["move_timeout_ms"] = 20
            await manager.consultation.request(
                game.id, ConsultationRequest(advisor=advisor, expected_revision=game.revision)
            )
            await settle(manager)
            result = await manager.snapshot(game.id)
            assert result.lifecycle is MatchState.RUNNING and result.moves == []
            assert result.consultations[-1].status == "failed"
            assert "SECRET" not in result.model_dump_json()
            assert "SECRET" not in str(await manager.events(game.id))
        finally:
            await manager.close()

    asyncio.run(run())


def test_confirmation_rejects_old_advice_even_if_fen_is_unchanged(tmp_path):
    async def run():
        manager = GameManager(
            engine=FakeEngine(),
            store=DatabaseStore(f"sqlite+aiosqlite:///{tmp_path / 'stale.db'}"),
            schedule_agents=False,
            schedule_timeouts=False,
        )
        await manager.start()
        try:
            game = await manager.create(CreateGameRequest(opponent=OpponentKind.HUMAN))
            await manager.consultation.request(
                game.id,
                ConsultationRequest(
                    advisor=scripted_player("Coach", "e2e4"), expected_revision=game.revision
                ),
            )
            await settle(manager)
            ready = await manager.snapshot(game.id)
            advice = ready.consultations[-1]
            await manager.pause(game.id)
            resumed = await manager.resume(game.id)
            assert resumed.fen == ready.fen
            with pytest.raises(StalePosition):
                await manager.make_human_move(
                    game.id,
                    advice.move,
                    ready.version,
                    consultation_id=advice.id,
                    consultation_revision=ready.revision,
                )
            assert (await manager.snapshot(game.id)).moves == []
        finally:
            await manager.close()

    asyncio.run(run())


def test_consultation_reuses_bounded_provider_recovery(tmp_path):
    async def run():
        adapter = RecoveringProviderAdapter(1)
        manager = GameManager(
            engine=FakeEngine(),
            store=DatabaseStore(f"sqlite+aiosqlite:///{tmp_path / 'provider.db'}"),
            adapters=AdapterRegistry([adapter]),
            provider_reliability=ProviderReliabilityController(
                ProviderRetryPolicy(base_delay_ms=0, max_delay_ms=0)
            ),
            schedule_agents=False,
            schedule_timeouts=False,
        )
        await manager.start()
        try:
            game = await manager.create(CreateGameRequest(opponent=OpponentKind.HUMAN))
            await manager.consultation.request(
                game.id,
                ConsultationRequest(advisor=provider_player(), expected_revision=game.revision),
            )
            await settle(manager)
            snapshot = await manager.snapshot(game.id)
            assert adapter.calls == 2
            assert snapshot.consultations[-1].attempts == 2
            assert snapshot.moves == []
        finally:
            await manager.close()

    asyncio.run(run())


def test_api_rejects_stale_paused_automated_and_remote_advisers(client):
    game = client.post("/api/games", json={"opponent": "human"}).json()
    url = f"/api/games/{game['id']}"
    command = {
        "advisor": scripted_player("Coach", "e2e4").model_dump(mode="json"),
        "expected_revision": game["revision"],
    }
    assert (
        client.post(url + "/consultations", json={**command, "expected_revision": 999}).status_code
        == 409
    )
    human = PlayerConfiguration.human("white").model_dump(mode="json")
    assert (
        client.post(url + "/consultations", json={**command, "advisor": human}).status_code == 422
    )
    remote = {**human, "adapter_id": "remote_runner", "connection_mode": "remote_runner"}
    assert (
        client.post(url + "/consultations", json={**command, "advisor": remote}).status_code == 422
    )
    engine = PlayerConfiguration.stockfish("white").model_dump(mode="json")
    engine["division"] = "pure_reasoning"
    assert (
        client.post(url + "/consultations", json={**command, "advisor": engine}).status_code == 422
    )
    client.app.state.game_manager._schedule_agents_enabled = False
    automated = client.post(
        "/api/games", json={"white_player": command["advisor"], "opponent": "human"}
    ).json()
    assert (
        client.post(
            f"/api/games/{automated['id']}/consultations",
            json={**command, "expected_revision": automated["revision"]},
        ).status_code
        == 409
    )
    paused = client.post(url + "/pause").json()
    assert (
        client.post(
            url + "/consultations", json={**command, "expected_revision": paused["revision"]}
        ).status_code
        == 409
    )


def test_shutdown_cancels_pending_advice_and_restart_does_not_redispatch(tmp_path):
    class Slow(ScriptedPlayerAdapter):
        def __init__(self):
            self.started = asyncio.Event()

        async def choose_move(self, request, player):
            self.started.set()
            await asyncio.Event().wait()

    async def run():
        url = f"sqlite+aiosqlite:///{tmp_path / 'restart.db'}"
        adapter = Slow()
        manager = GameManager(
            engine=FakeEngine(),
            store=DatabaseStore(url),
            adapters=AdapterRegistry([adapter]),
            schedule_agents=False,
            schedule_timeouts=False,
        )
        await manager.start()
        game = await manager.create(CreateGameRequest(opponent=OpponentKind.HUMAN))
        await manager.consultation.request(
            game.id,
            ConsultationRequest(
                advisor=scripted_player("Slow", "e2e4"), expected_revision=game.revision
            ),
        )
        await asyncio.wait_for(adapter.started.wait(), 2)
        await manager.close()
        manager = GameManager(
            engine=FakeEngine(),
            store=DatabaseStore(url),
            schedule_agents=False,
            schedule_timeouts=False,
        )
        await manager.start()
        try:
            current = await manager.snapshot(game.id)
            assert current.consultations[-1].status == "cancelled"
            assert current.moves == [] and not manager.consultation.tasks
            await manager.consultation.request(
                game.id,
                ConsultationRequest(
                    advisor=scripted_player("Coach", "e2e4"), expected_revision=current.revision
                ),
            )
            await settle(manager)
            assert (await manager.snapshot(game.id)).consultations[-1].status == "ready"
        finally:
            await manager.close()

    asyncio.run(run())


def test_one_pending_consultation_per_position_across_workers(tmp_path):
    class Slow(ScriptedPlayerAdapter):
        async def choose_move(self, request, player):
            await asyncio.Event().wait()

    async def run():
        url = f"sqlite+aiosqlite:///{tmp_path / 'duplicates.db'}"
        managers = [
            GameManager(
                engine=FakeEngine(),
                store=DatabaseStore(url),
                adapters=AdapterRegistry([Slow()]),
                schedule_agents=False,
                schedule_timeouts=False,
            )
            for _ in range(2)
        ]
        for manager in managers:
            await manager.start()
        try:
            game = await managers[0].create(CreateGameRequest(opponent=OpponentKind.HUMAN))
            results = await asyncio.gather(
                *[
                    m.consultation.request(
                        game.id,
                        ConsultationRequest(
                            advisor=scripted_player("Slow", "e2e4"), expected_revision=game.revision
                        ),
                    )
                    for m in managers
                ],
                return_exceptions=True,
            )
            assert sum(not isinstance(r, Exception) for r in results) == 1
            snapshot = await managers[0].snapshot(game.id)
            assert len(snapshot.consultations) == 1
            with pytest.raises(ValueError, match="already thinking"):
                await managers[1].consultation.request(
                    game.id,
                    ConsultationRequest(
                        advisor=scripted_player("Slow", "e2e4"), expected_revision=snapshot.revision
                    ),
                )
        finally:
            for manager in managers:
                await manager.close()

    asyncio.run(run())


def test_black_consultation_and_clock_expiry(tmp_path):
    class Delay(ScriptedPlayerAdapter):
        def __init__(self, clock):
            self.clock = clock

        async def choose_move(self, request, player):
            assert request.color == "black"
            self.clock.advance(minutes=10)
            return await super().choose_move(request, player)

    async def run():
        clock = FakeClock()
        manager = GameManager(
            engine=FakeEngine(),
            clock=clock,
            store=DatabaseStore(f"sqlite+aiosqlite:///{tmp_path / 'clock.db'}"),
            adapters=AdapterRegistry([Delay(clock)]),
            schedule_agents=False,
            schedule_timeouts=False,
        )
        await manager.start()
        try:
            game = await manager.create(CreateGameRequest(opponent=OpponentKind.HUMAN))
            moved = await manager.make_human_move(game.id, "e2e4", game.version)
            await manager.consultation.request(
                game.id,
                ConsultationRequest(
                    advisor=scripted_player("Coach", "e7e5"), expected_revision=moved.revision
                ),
            )
            await settle(manager)
            result = await manager.snapshot(game.id)
            assert result.clock.timed_out_by == "black"
            assert len(result.moves) == 1
            assert result.consultations[-1].status == "stale"
        finally:
            await manager.close()

    asyncio.run(run())
