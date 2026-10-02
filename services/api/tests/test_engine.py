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


def test_stockfish_analysis_returns_evaluation_and_pv() -> None:
    async def run() -> None:
        engine = StockfishService()
        if not engine.available:
            pytest.skip("Stockfish is not installed in this environment")
        board = chess.Board()
        result = await engine.analyse_position(board, analysis_time_ms=50)

        assert isinstance(result.score_cp, int)
        assert result.best_move in {move.uci() for move in board.legal_moves}
        assert result.pv_san
        await engine.close()

    asyncio.run(run())
