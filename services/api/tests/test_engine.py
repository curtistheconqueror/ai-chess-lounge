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


def test_real_engine_advertised_boundaries_and_full_strength():
    async def run():
        engine = StockfishService()
        if not engine.available:
            pytest.skip("Stockfish is not installed in this environment")
        try:
            caps = await engine.strength_capabilities()
            if caps["elo_min"] is None:
                pytest.skip("This runtime does not advertise UCI_Elo")
            for elo, full in [(caps["elo_min"], False), (caps["elo_max"], False), (1600, True)]:
                move = await engine.choose_move(
                    chess.Board(), target_elo=elo, move_time_ms=50, full_strength=full
                )
                assert chess.Move.from_uci(move.uci) in chess.Board().legal_moves
                config = engine._engine.protocol.config
                assert config["UCI_LimitStrength"] is (not full)
                if not full:
                    assert config["UCI_Elo"] == elo
        finally:
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
