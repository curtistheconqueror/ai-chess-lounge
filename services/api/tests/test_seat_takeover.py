import asyncio
import io
from datetime import UTC, datetime

import chess.pgn
import pytest
from lounge_api.adapters import (
    AdapterConfigurationError,
    AdapterError,
    AdapterRegistry,
    ScriptedPlayerAdapter,
)
from lounge_api.domain import MatchTransitionRejected
from lounge_api.manager import GameManager
from lounge_api.models import CreateGameRequest, MatchState, OpponentKind
from lounge_api.persistence import ConcurrentGameUpdate, DatabaseStore, RunnerTrustError
from lounge_api.player_protocol import MoveProposal, PlayerConfiguration
from test_manager import FakeClock, FakeEngine, scripted_player
from test_runner_trust import paired


def test_takeover_api_guards_and_stale_moves(client):
    game = client.post("/api/games", json={"opponent": "human"}).json()
    url = f"/api/games/{game['id']}"
    player = scripted_player("Replacement", "e2e4").model_dump(mode="json")

    def change(revision, replacement=player, color="white"):
        return client.post(
            url + "/seats/" + color,
            json={
                "expected_revision": revision,
                "player": replacement,
            },
        )

    assert change(game["revision"]).status_code == 409
    paused = client.post(url + "/pause", json={"expected_revision": game["revision"]}).json()
    assert change(game["revision"]).status_code == 409
    assert change(paused["revision"], color="green").status_code == 422
    assert change(paused["revision"], paused["white_player"]).status_code == 409
    assert (
        change(
            paused["revision"],
            PlayerConfiguration.human("black")
            .model_copy(update={"settings": {"color": "black"}})
            .model_dump(mode="json"),
        ).status_code
        == 409
    )
    changed = change(paused["revision"]).json()
    assert changed["lifecycle"] == "paused"
    assert changed["version"] == paused["version"] + 1
    assert changed["fen"] == paused["fen"]
    assert (
        client.post(url + "/resume", json={"expected_revision": paused["revision"]}).status_code
        == 409
    )
    restored = change(changed["revision"], paused["white_player"]).json()
    resumed = client.post(url + "/resume", json={"expected_revision": restored["revision"]}).json()
    assert (
        client.post(
            url + "/moves", json={"move": "e2e4", "position_version": game["version"]}
        ).status_code
        == 409
    )
    assert resumed["moves"] == []
    assert len(resumed["seat_history"]) == 2
    assert (
        client.post(
            url + "/moves", json={"move": "e2e4", "position_version": resumed["version"]}
        ).status_code
        == 200
    )


def test_history_clocks_pgn_and_reset_survive_restart(tmp_path):
    async def run():
        url = f"sqlite+aiosqlite:///{tmp_path / 'history.db'}"
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
            original = game.white_player
            clock.advance(seconds=3)
            moved = await manager.make_human_move(game.id, "e2e4", game.version)
            clock.advance(seconds=2)
            paused = await manager.pause(game.id)
            changed = await manager.change_seat(
                game.id, "white", scripted_player("New {Agent}", "e2e4"), paused.revision
            )
            assert (changed.clock.white_remaining_ms, changed.clock.black_remaining_ms) == (
                paused.clock.white_remaining_ms,
                paused.clock.black_remaining_ms,
            )
            assert changed.fen == moved.fen
            clock.advance(hours=1)
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
            saved = await manager.snapshot(game.id)
            assert saved.seat_history == changed.seat_history
            assert saved.lifecycle is MatchState.PAUSED
            assert saved.clock.white_remaining_ms == changed.clock.white_remaining_ms
            exported = chess.pgn.read_game(io.StringIO(saved.pgn))
            assert exported.headers["White"] == original.display_name
            assert exported.headers["WhiteCurrent"] == "New {Agent}"
            assert "Seat change (white)" in exported.end().comment
            assert list(exported.mainline_moves()) == [chess.Move.from_uci("e2e4")]
            resumed = await manager.resume(game.id, saved.revision)
            assert resumed.clock.black_remaining_ms == saved.clock.black_remaining_ms
            await manager.reset(game.id)
            reset = await manager.snapshot(game.id)
            assert reset.seat_history == []
            assert any(e.type == "seat.changed" for e in await manager.events(game.id))
        finally:
            await manager.close()

    asyncio.run(run())


def test_two_workers_same_revision_only_one_seat_change(tmp_path):
    async def run():
        url = f"sqlite+aiosqlite:///{tmp_path / 'race.db'}"
        managers = [
            GameManager(
                engine=FakeEngine(),
                store=DatabaseStore(url),
                schedule_agents=False,
                schedule_timeouts=False,
            )
            for _ in range(2)
        ]
        for manager in managers:
            await manager.start()
        try:
            game = await managers[0].create(CreateGameRequest(opponent=OpponentKind.HUMAN))
            paused = await managers[0].pause(game.id)
            results = await asyncio.gather(
                *[
                    m.change_seat(
                        game.id, "white", scripted_player(f"Agent {i}", "e2e4"), paused.revision
                    )
                    for i, m in enumerate(managers)
                ],
                return_exceptions=True,
            )
            assert sum(not isinstance(r, Exception) for r in results) == 1
            assert any(
                isinstance(r, (MatchTransitionRejected, ConcurrentGameUpdate)) for r in results
            )
            assert len((await managers[0].snapshot(game.id)).seat_history) == 1
            assert sum(e.type == "seat.changed" for e in await managers[0].events(game.id)) == 1
        finally:
            for manager in managers:
                await manager.close()

    asyncio.run(run())


@pytest.mark.parametrize("late_error", [None, RunnerTrustError, AdapterError])
def test_old_worker_cannot_move_or_pause_new_controller(tmp_path, late_error):
    class DelayedAdapter(ScriptedPlayerAdapter):
        def __init__(self):
            self.started = asyncio.Event()
            self.release = asyncio.Event()

        async def choose_move(self, request, player):
            self.started.set()
            await self.release.wait()
            if late_error:
                raise late_error("Old authorization was revoked")
            return MoveProposal(
                request_id=request.request_id,
                match_id=request.match_id,
                position_version=request.position_version,
                move="e2e4",
            )

    async def run():
        url = f"sqlite+aiosqlite:///{tmp_path / 'late.db'}"
        adapter = DelayedAdapter()
        old = GameManager(
            engine=FakeEngine(),
            store=DatabaseStore(url),
            adapters=AdapterRegistry([adapter]),
            schedule_timeouts=False,
        )
        new = GameManager(
            engine=FakeEngine(),
            store=DatabaseStore(url),
            schedule_agents=False,
            schedule_timeouts=False,
        )
        await old.start()
        await new.start()
        try:
            game = await old.create(
                CreateGameRequest(
                    opponent=OpponentKind.HUMAN, white_player=scripted_player("Old", "e2e4")
                )
            )
            await asyncio.wait_for(adapter.started.wait(), 2)
            paused = await new.pause(game.id)
            changed = await new.change_seat(
                game.id, "white", PlayerConfiguration.human("white"), paused.revision
            )
            await new.resume(game.id, changed.revision)
            adapter.release.set()
            await old.wait_for_automation(game.id, timeout=2)
            current = await new.snapshot(game.id)
            assert current.lifecycle is MatchState.RUNNING
            assert current.moves == []
            assert current.white_player.is_human
        finally:
            adapter.release.set()
            await old.close()
            await new.close()

    asyncio.run(run())


def test_remote_runner_return_preserves_original_grant(tmp_path):
    async def run():
        store = DatabaseStore(f"sqlite+aiosqlite:///{tmp_path / 'runner.db'}")
        broker, creds = await paired(store, max_turns=3)
        manager = GameManager(
            engine=FakeEngine(),
            store=store,
            remote_runners=broker,
            schedule_agents=False,
            schedule_timeouts=False,
        )
        await manager.start()
        try:
            game = await manager.create(
                CreateGameRequest(opponent=OpponentKind.HUMAN, white_player=creds.player)
            )
            await store.reserve_runner_turn(
                creds.session_id, game.id, "white", now=datetime.now(UTC)
            )
            grant = await store.runner_grant(creds.session_id)
            paused = await manager.pause(game.id)
            human = await manager.change_seat(
                game.id, "white", PlayerConfiguration.human("white"), paused.revision
            )
            resumed = await manager.resume(game.id, human.revision)
            with pytest.raises(RunnerTrustError, match="seat"):
                await store.reserve_runner_turn(
                    creds.session_id,
                    game.id,
                    "white",
                    now=datetime.now(UTC),
                    position_version=resumed.version,
                    match_revision=resumed.revision,
                )
            paused = await manager.pause(game.id)
            with pytest.raises(AdapterConfigurationError, match="original match and seat"):
                await manager.change_seat(game.id, "black", creds.player, paused.revision)
            returned = await manager.change_seat(game.id, "white", creds.player, paused.revision)
            assert returned.white_player == creds.player
            assert await store.runner_grant(creds.session_id) == grant
        finally:
            await manager.close()

    asyncio.run(run())


def test_remote_reservation_after_cross_worker_takeover_exits_cleanly(tmp_path):
    async def run():
        url = f"sqlite+aiosqlite:///{tmp_path / 'reservation.db'}"
        store = DatabaseStore(url)
        broker, creds = await paired(store)
        started, release = asyncio.Event(), asyncio.Event()
        reserve = store.reserve_runner_turn

        async def delayed_reserve(*args, **kwargs):
            started.set()
            await release.wait()
            return await reserve(*args, **kwargs)

        store.reserve_runner_turn = delayed_reserve
        old = GameManager(
            engine=FakeEngine(), store=store, remote_runners=broker, schedule_timeouts=False
        )
        new = GameManager(
            engine=FakeEngine(),
            store=DatabaseStore(url),
            schedule_agents=False,
            schedule_timeouts=False,
        )
        await old.start()
        await new.start()
        try:
            game = await old.create(
                CreateGameRequest(opponent=OpponentKind.HUMAN, white_player=creds.player)
            )
            await asyncio.wait_for(started.wait(), 2)
            task = old._agent_tasks[game.id]
            paused = await new.pause(game.id)
            changed = await new.change_seat(
                game.id, "white", PlayerConfiguration.human("white"), paused.revision
            )
            await new.resume(game.id, changed.revision)
            release.set()
            await asyncio.wait_for(asyncio.shield(task), 2)
            current = await new.snapshot(game.id)
            assert current.lifecycle is MatchState.RUNNING
            assert current.moves == []
            assert current.white_player.is_human
            assert await store.runner_grant(creds.session_id) is None
        finally:
            release.set()
            await old.close()
            await new.close()

    asyncio.run(run())
