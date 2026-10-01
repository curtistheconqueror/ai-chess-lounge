from __future__ import annotations

import asyncio

import chess
from lounge_api.engine import EngineMove, StockfishService
from lounge_api.manager import GameManager
from lounge_api.models import CreateGameRequest, EngineSummary, OpponentKind
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
