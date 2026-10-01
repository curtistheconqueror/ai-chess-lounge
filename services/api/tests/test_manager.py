from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import chess
from lounge_api.engine import EngineMove, StockfishService
from lounge_api.manager import GameManager
from lounge_api.models import CreateGameRequest, EngineSummary, GameStatus, OpponentKind
from lounge_api.persistence import DatabaseStore


class FakeEngine(StockfishService):
    @property
    def available(self) -> bool:
        return True

    async def summary(self, target_elo: int, move_time_ms: int) -> EngineSummary:
        return EngineSummary(
            name="Deterministic Test Engine",
            available=True,
            target_elo=target_elo,
            move_time_ms=move_time_ms,
            version="test-1",
        )

    async def choose_move(
        self, board: chess.Board, *, target_elo: int, move_time_ms: int
    ) -> EngineMove:
        return EngineMove(uci=sorted(move.uci() for move in board.legal_moves)[0], elapsed_ms=1)

    async def close(self) -> None:
        return None


class FakeClock:
    def __init__(self) -> None:
        self.current = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.current

    def advance(self, **kwargs: float) -> None:
        self.current += timedelta(**kwargs)


def test_human_move_triggers_engine_reply() -> None:
    async def run() -> None:
        manager = GameManager(
            engine=FakeEngine(),
            store=DatabaseStore("sqlite+aiosqlite:///:memory:"),
        )
        await manager.start()
        try:
            game = await manager.create(
                CreateGameRequest(opponent=OpponentKind.STOCKFISH, stockfish_elo=1600)
            )
            snapshot = await manager.make_human_move(game.id, "e2e4", 0)

            assert len(snapshot.moves) == 2
            assert snapshot.moves[0].actor == "human:white"
            assert snapshot.moves[1].actor == "stockfish:black"
            assert snapshot.turn == "white"
            assert snapshot.version == 2
            assert snapshot.event_sequence == 4
        finally:
            await manager.close()

    asyncio.run(run())


def test_manager_persists_timeout_and_completion_events() -> None:
    async def run() -> None:
        clock = FakeClock()
        manager = GameManager(
            store=DatabaseStore("sqlite+aiosqlite:///:memory:"),
            clock=clock,
            schedule_timeouts=False,
        )
        await manager.start()
        try:
            game = await manager.create(
                CreateGameRequest(
                    opponent=OpponentKind.HUMAN,
                    initial_time_ms=1_000,
                    increment_ms=0,
                )
            )
            clock.advance(seconds=1)

            assert await manager.expire_due_games() == [game.id]
            snapshot = await manager.snapshot(game.id)
            events = await manager.events(game.id)

            assert snapshot.status is GameStatus.TIMEOUT
            assert snapshot.result == "0-1"
            assert snapshot.clock.timed_out_by == "white"
            assert [event.type for event in events][-2:] == [
                "clock.timeout",
                "match.completed",
            ]
            assert events[-2].payload["white_remaining_ms"] == 0
            assert events[-2].timestamp == clock.current.isoformat()
        finally:
            await manager.close()

    asyncio.run(run())


def test_background_deadline_task_broadcasts_timeout() -> None:
    async def run() -> None:
        manager = GameManager(store=DatabaseStore("sqlite+aiosqlite:///:memory:"))
        await manager.start()
        try:
            game = await manager.create(
                CreateGameRequest(
                    opponent=OpponentKind.HUMAN,
                    initial_time_ms=100,
                    increment_ms=0,
                )
            )
            await asyncio.sleep(0.14)
            snapshot = await manager.snapshot(game.id)
            assert snapshot.status is GameStatus.TIMEOUT
        finally:
            await manager.close()

    asyncio.run(run())
