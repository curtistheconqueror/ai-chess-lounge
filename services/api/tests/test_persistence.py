from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from lounge_api.domain import StalePosition
from lounge_api.manager import GameManager
from lounge_api.models import CreateGameRequest, GameStatus, MatchState, OpponentKind
from lounge_api.persistence import DatabaseStore


def database_url(path: Path) -> str:
    return f"sqlite+aiosqlite:///{path}"


class MutableClock:
    def __init__(self) -> None:
        self.current = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.current

    def advance(self, **kwargs: float) -> None:
        self.current += timedelta(**kwargs)


def test_match_survives_manager_restart(tmp_path: Path) -> None:
    async def run() -> None:
        url = database_url(tmp_path / "restart.db")
        first = GameManager(store=DatabaseStore(url))
        await first.start()
        game = await first.create(CreateGameRequest(opponent=OpponentKind.HUMAN))
        moved = await first.make_human_move(game.id, "e2e4", 0)
        await first.close()

        second = GameManager(store=DatabaseStore(url))
        await second.start()
        try:
            restored = await second.get(game.id)
            assert restored.snapshot().fen == moved.fen
            assert restored.snapshot().pgn == moved.pgn
            assert restored.snapshot().moves[0].san == "e4"
            assert restored.lifecycle is MatchState.RUNNING
        finally:
            await second.close()

    asyncio.run(run())


def test_reset_keeps_append_only_history(tmp_path: Path) -> None:
    async def run() -> None:
        manager = GameManager(store=DatabaseStore(database_url(tmp_path / "events.db")))
        await manager.start()
        try:
            game = await manager.create(CreateGameRequest(opponent=OpponentKind.HUMAN))
            await manager.make_human_move(game.id, "e2e4", 0)
            reset = await manager.reset(game.id)
            events = await manager.events(game.id)

            assert reset.moves == []
            assert reset.generation == 1
            assert [event.type for event in events] == [
                "match.created",
                "match.started",
                "move.accepted",
                "match.reset",
            ]
        finally:
            await manager.close()

    asyncio.run(run())


def test_database_compare_and_swap_rejects_second_writer(tmp_path: Path) -> None:
    async def run() -> None:
        url = database_url(tmp_path / "concurrency.db")
        first = GameManager(store=DatabaseStore(url))
        await first.start()
        game = await first.create(CreateGameRequest(opponent=OpponentKind.HUMAN))

        second = GameManager(store=DatabaseStore(url))
        await second.start()
        await second.get(game.id)
        try:
            await first.make_human_move(game.id, "e2e4", 0)
            with pytest.raises(StalePosition):
                await second.make_human_move(game.id, "d2d4", 0)
            refreshed = await second.get(game.id)
            assert refreshed.version == 1
            assert refreshed.moves[0].uci == "e2e4"
        finally:
            await first.close()
            await second.close()

    asyncio.run(run())


def test_clock_and_move_times_survive_restart(tmp_path: Path) -> None:
    async def run() -> None:
        clock = MutableClock()
        url = database_url(tmp_path / "clock-restart.db")
        first = GameManager(
            store=DatabaseStore(url),
            clock=clock,
            schedule_timeouts=False,
        )
        await first.start()
        game = await first.create(
            CreateGameRequest(
                opponent=OpponentKind.HUMAN,
                initial_time_ms=10_000,
                increment_ms=1_000,
            )
        )
        clock.advance(seconds=2)
        moved = await first.make_human_move(game.id, "e2e4", 0)
        await first.close()

        second = GameManager(
            store=DatabaseStore(url),
            clock=clock,
            schedule_timeouts=False,
        )
        await second.start()
        try:
            restored = await second.snapshot(game.id)
            assert restored.clock.white_remaining_ms == 9_000
            assert restored.clock.black_remaining_ms == 10_000
            assert restored.moves[0].white_remaining_ms == 9_000
            assert restored.moves[0].black_remaining_ms == 10_000
            assert restored.clock.deadline_at == moved.clock.deadline_at

            clock.advance(seconds=3)
            ticking = await second.snapshot(game.id)
            assert ticking.clock.black_remaining_ms == 7_000
        finally:
            await second.close()

    asyncio.run(run())


def test_restart_adjudicates_elapsed_deadline(tmp_path: Path) -> None:
    async def run() -> None:
        clock = MutableClock()
        url = database_url(tmp_path / "clock-expired.db")
        first = GameManager(
            store=DatabaseStore(url),
            clock=clock,
            schedule_timeouts=False,
        )
        await first.start()
        game = await first.create(
            CreateGameRequest(
                opponent=OpponentKind.HUMAN,
                initial_time_ms=1_000,
                increment_ms=0,
            )
        )
        await first.close()

        clock.advance(seconds=2)
        second = GameManager(
            store=DatabaseStore(url),
            clock=clock,
            schedule_timeouts=False,
        )
        await second.start()
        try:
            restored = await second.snapshot(game.id)
            events = await second.events(game.id)
            assert restored.status is GameStatus.TIMEOUT
            assert restored.result == "0-1"
            assert [event.type for event in events][-2:] == [
                "clock.timeout",
                "match.completed",
            ]
        finally:
            await second.close()

    asyncio.run(run())


def test_two_managers_converge_on_one_timeout_result(tmp_path: Path) -> None:
    async def run() -> None:
        clock = MutableClock()
        url = database_url(tmp_path / "clock-race.db")
        first = GameManager(
            store=DatabaseStore(url),
            clock=clock,
            schedule_timeouts=False,
        )
        await first.start()
        game = await first.create(
            CreateGameRequest(
                opponent=OpponentKind.HUMAN,
                initial_time_ms=1_000,
                increment_ms=0,
            )
        )
        second = GameManager(
            store=DatabaseStore(url),
            clock=clock,
            schedule_timeouts=False,
        )
        await second.start()
        try:
            clock.advance(seconds=1)
            outcomes = await asyncio.gather(
                first.expire_due_games(),
                second.expire_due_games(),
            )

            assert sum(game.id in outcome for outcome in outcomes) == 1
            first_snapshot = await first.snapshot(game.id)
            second_snapshot = await second.snapshot(game.id)
            events = await first.events(game.id)
            assert first_snapshot.status is GameStatus.TIMEOUT
            assert second_snapshot.status is GameStatus.TIMEOUT
            assert [event.type for event in events].count("clock.timeout") == 1
            assert [event.type for event in events].count("match.completed") == 1
        finally:
            await first.close()
            await second.close()

    asyncio.run(run())
