from __future__ import annotations

from datetime import UTC, datetime, timedelta

import chess
import pytest
from lounge_api.domain import (
    ClockExpired,
    GameSession,
    MatchTransitionRejected,
    MoveRejected,
    StalePosition,
)
from lounge_api.models import GameStatus, MatchState, OpponentKind


def running_game(opponent: OpponentKind = OpponentKind.HUMAN) -> GameSession:
    game = GameSession(opponent=opponent)
    game.start()
    return game


def test_legal_move_updates_authoritative_state() -> None:
    game = running_game()

    move = game.apply_uci("e2e4", actor="human:white", position_version=0)

    assert move.san == "e4"
    assert game.version == 1
    assert game.board.piece_at(chess.E4) == chess.Piece(chess.PAWN, chess.WHITE)
    assert game.snapshot().turn == "black"


def test_illegal_move_does_not_change_position() -> None:
    game = running_game()
    original_fen = game.board.fen()

    with pytest.raises(MoveRejected, match="not legal"):
        game.apply_uci("e2e5", actor="human:white", position_version=0)

    assert game.board.fen() == original_fen
    assert game.version == 0


def test_stale_position_is_rejected() -> None:
    game = running_game()
    game.apply_uci("e2e4", actor="human:white", position_version=0)

    with pytest.raises(StalePosition):
        game.apply_uci("e7e5", actor="human:black", position_version=0)


def test_castling_en_passant_and_promotion_are_supported() -> None:
    castle = running_game()
    for uci in ["e2e4", "e7e5", "g1f3", "b8c6", "f1c4", "g8f6", "e1g1"]:
        castle.apply_uci(uci, actor="test")
    assert castle.board.king(chess.WHITE) == chess.G1
    assert castle.board.piece_at(chess.F1) == chess.Piece(chess.ROOK, chess.WHITE)

    passant = running_game()
    for uci in ["e2e4", "a7a6", "e4e5", "d7d5", "e5d6"]:
        passant.apply_uci(uci, actor="test")
    assert passant.board.piece_at(chess.D5) is None
    assert passant.board.piece_at(chess.D6) == chess.Piece(chess.PAWN, chess.WHITE)

    promotion = running_game()
    promotion.board = chess.Board("7k/P7/8/8/8/8/8/6K1 w - - 0 1")
    promotion.apply_uci("a7a8q", actor="test")
    assert promotion.board.piece_at(chess.A8) == chess.Piece(chess.QUEEN, chess.WHITE)


def test_checkmate_sets_result_and_banner() -> None:
    game = running_game()
    for uci in ["f2f3", "e7e5", "g2g4", "d8h4"]:
        game.apply_uci(uci, actor="test")

    snapshot = game.snapshot()
    assert snapshot.status is GameStatus.CHECKMATE
    assert snapshot.lifecycle is MatchState.COMPLETED
    assert snapshot.result == "0-1"
    assert "Checkmate" in snapshot.strategy_banner


def test_pgn_contains_complete_move_history() -> None:
    game = running_game()
    for uci in ["d2d4", "d7d5", "c2c4"]:
        game.apply_uci(uci, actor="test")

    pgn = game.pgn()
    assert '[White "Human"]' in pgn
    assert "1. d4 d5 2. c4" in pgn


def test_explicit_lifecycle_transitions() -> None:
    game = GameSession(opponent=OpponentKind.HUMAN)
    assert game.lifecycle is MatchState.CREATED

    game.start()
    game.pause()
    assert game.status is GameStatus.PAUSED
    game.resume()
    game.abort()
    assert game.status is GameStatus.ABORTED

    with pytest.raises(MatchTransitionRejected):
        game.resume()


def test_pause_blocks_moves_and_adjudication_records_result() -> None:
    game = running_game()
    game.pause()

    with pytest.raises(MoveRejected):
        game.apply_uci("e2e4", actor="test", position_version=0)

    game.adjudicate("1/2-1/2")
    assert game.lifecycle is MatchState.ADJUDICATED
    assert game.status is GameStatus.ADJUDICATED
    assert game.result == "1/2-1/2"


def test_fischer_clock_charges_elapsed_time_and_adds_increment() -> None:
    started = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
    game = GameSession(
        opponent=OpponentKind.HUMAN,
        initial_time_ms=60_000,
        increment_ms=2_000,
    )
    game.start(now=started)

    move = game.apply_uci(
        "e2e4",
        actor="human:white",
        position_version=0,
        now=started + timedelta(seconds=10),
    )
    snapshot = game.snapshot(now=started + timedelta(seconds=15))

    assert move.white_remaining_ms == 52_000
    assert move.black_remaining_ms == 60_000
    assert snapshot.clock.white_remaining_ms == 52_000
    assert snapshot.clock.black_remaining_ms == 55_000
    assert snapshot.clock.deadline_at == (started + timedelta(seconds=70)).isoformat()


def test_pause_freezes_clock_and_resume_reanchors_deadline() -> None:
    started = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
    game = GameSession(
        opponent=OpponentKind.HUMAN,
        initial_time_ms=60_000,
        increment_ms=0,
    )
    game.start(now=started)
    game.pause(now=started + timedelta(seconds=12))

    paused = game.snapshot(now=started + timedelta(hours=2))
    assert paused.clock.white_remaining_ms == 48_000
    assert paused.clock.deadline_at is None

    resumed_at = started + timedelta(hours=2)
    game.resume(now=resumed_at)
    resumed = game.snapshot(now=resumed_at + timedelta(seconds=5))
    assert resumed.clock.white_remaining_ms == 43_000
    assert resumed.clock.deadline_at == (resumed_at + timedelta(seconds=48)).isoformat()


def test_deadline_is_terminal_and_late_move_is_rejected() -> None:
    started = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
    game = GameSession(
        opponent=OpponentKind.HUMAN,
        initial_time_ms=1_000,
        increment_ms=0,
    )
    game.start(now=started)

    assert game.expire_if_needed(started + timedelta(milliseconds=999)) is False
    with pytest.raises(ClockExpired, match="White lost on time"):
        game.apply_uci(
            "e2e4",
            actor="human:white",
            position_version=0,
            now=started + timedelta(seconds=1),
        )

    snapshot = game.snapshot(now=started + timedelta(seconds=1))
    assert snapshot.status is GameStatus.TIMEOUT
    assert snapshot.result == "0-1"
    assert snapshot.clock.white_remaining_ms == 0
    assert snapshot.clock.timed_out_by == "white"
    assert snapshot.moves == []
