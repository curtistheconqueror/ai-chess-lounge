from __future__ import annotations

import chess
import pytest

from lounge_api.domain import GameSession, MoveRejected, StalePosition
from lounge_api.models import GameStatus, OpponentKind


def test_legal_move_updates_authoritative_state() -> None:
    game = GameSession(opponent=OpponentKind.HUMAN)

    move = game.apply_uci("e2e4", actor="human:white", position_version=0)

    assert move.san == "e4"
    assert game.version == 1
    assert game.board.piece_at(chess.E4) == chess.Piece(chess.PAWN, chess.WHITE)
    assert game.snapshot().turn == "black"


def test_illegal_move_does_not_change_position() -> None:
    game = GameSession(opponent=OpponentKind.HUMAN)
    original_fen = game.board.fen()

    with pytest.raises(MoveRejected, match="not legal"):
        game.apply_uci("e2e5", actor="human:white", position_version=0)

    assert game.board.fen() == original_fen
    assert game.version == 0


def test_stale_position_is_rejected() -> None:
    game = GameSession(opponent=OpponentKind.HUMAN)
    game.apply_uci("e2e4", actor="human:white", position_version=0)

    with pytest.raises(StalePosition):
        game.apply_uci("e7e5", actor="human:black", position_version=0)


def test_castling_en_passant_and_promotion_are_supported() -> None:
    castle = GameSession(opponent=OpponentKind.HUMAN)
    for uci in ["e2e4", "e7e5", "g1f3", "b8c6", "f1c4", "g8f6", "e1g1"]:
        castle.apply_uci(uci, actor="test")
    assert castle.board.king(chess.WHITE) == chess.G1
    assert castle.board.piece_at(chess.F1) == chess.Piece(chess.ROOK, chess.WHITE)

    passant = GameSession(opponent=OpponentKind.HUMAN)
    for uci in ["e2e4", "a7a6", "e4e5", "d7d5", "e5d6"]:
        passant.apply_uci(uci, actor="test")
    assert passant.board.piece_at(chess.D5) is None
    assert passant.board.piece_at(chess.D6) == chess.Piece(chess.PAWN, chess.WHITE)

    promotion = GameSession(opponent=OpponentKind.HUMAN)
    promotion.board = chess.Board("7k/P7/8/8/8/8/8/6K1 w - - 0 1")
    promotion.apply_uci("a7a8q", actor="test")
    assert promotion.board.piece_at(chess.A8) == chess.Piece(chess.QUEEN, chess.WHITE)


def test_checkmate_sets_result_and_banner() -> None:
    game = GameSession(opponent=OpponentKind.HUMAN)
    for uci in ["f2f3", "e7e5", "g2g4", "d8h4"]:
        game.apply_uci(uci, actor="test")

    snapshot = game.snapshot()
    assert snapshot.status is GameStatus.CHECKMATE
    assert snapshot.result == "0-1"
    assert "Checkmate" in snapshot.strategy_banner


def test_pgn_contains_complete_move_history() -> None:
    game = GameSession(opponent=OpponentKind.HUMAN)
    for uci in ["d2d4", "d7d5", "c2c4"]:
        game.apply_uci(uci, actor="test")

    pgn = game.pgn()
    assert '[White "Human"]' in pgn
    assert "1. d4 d5 2. c4" in pgn
