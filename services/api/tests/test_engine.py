from __future__ import annotations

import asyncio

import chess
import pytest

from lounge_api.engine import StockfishService


def test_stockfish_returns_a_legal_move_when_available() -> None:
    async def run() -> None:
        engine = StockfishService()
        if not engine.available:
            pytest.skip("Stockfish is not installed in this environment")
        board = chess.Board()
        result = await engine.choose_move(board, target_elo=1600, move_time_ms=50)
        assert chess.Move.from_uci(result.uci) in board.legal_moves
        assert result.elapsed_ms >= 0
        await engine.close()

    asyncio.run(run())
