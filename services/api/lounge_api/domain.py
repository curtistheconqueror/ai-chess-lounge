from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from time import perf_counter
from uuid import uuid4

import chess
import chess.pgn

from .models import (
    EngineSummary,
    GameSnapshot,
    GameStatus,
    MoveRecord,
    OpponentKind,
)


class MoveRejected(ValueError):
    """Raised when a proposed move cannot be applied to the current position."""


class StalePosition(MoveRejected):
    """Raised when a client submits against an older position version."""


@dataclass(slots=True)
class GameSession:
    opponent: OpponentKind = OpponentKind.STOCKFISH
    stockfish_elo: int = 1600
    engine_move_time_ms: int = 450
    id: str = field(default_factory=lambda: str(uuid4()))
    board: chess.Board = field(default_factory=chess.Board)
    version: int = 0
    moves: list[MoveRecord] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    resigned_by: str | None = None
    engine_summary: EngineSummary | None = None

    @property
    def status(self) -> GameStatus:
        if self.resigned_by:
            return GameStatus.RESIGNED
        if self.board.is_checkmate():
            return GameStatus.CHECKMATE
        if self.board.is_stalemate():
            return GameStatus.STALEMATE
        if (
            self.board.is_insufficient_material()
            or self.board.is_fivefold_repetition()
            or self.board.is_seventyfive_moves()
        ):
            return GameStatus.DRAW
        return GameStatus.ACTIVE

    @property
    def result(self) -> str:
        if self.resigned_by == "white":
            return "0-1"
        if self.resigned_by == "black":
            return "1-0"
        return self.board.result(claim_draw=False) if self.board.is_game_over(claim_draw=False) else "*"

    def apply_uci(
        self,
        uci: str,
        *,
        actor: str,
        position_version: int | None = None,
        started_at: float | None = None,
    ) -> MoveRecord:
        if self.status is not GameStatus.ACTIVE:
            raise MoveRejected("The game is already over.")
        if position_version is not None and position_version != self.version:
            raise StalePosition(
                f"Position changed: expected version {position_version}, current version is {self.version}."
            )
        try:
            move = chess.Move.from_uci(uci)
        except ValueError as exc:
            raise MoveRejected("Move must use UCI notation, for example e2e4.") from exc
        if move not in self.board.legal_moves:
            raise MoveRejected(f"{uci} is not legal in the current position.")

        san = self.board.san(move)
        self.board.push(move)
        self.version += 1
        elapsed_ms = None
        if started_at is not None:
            elapsed_ms = max(0, round((perf_counter() - started_at) * 1000))
        record = MoveRecord(
            ply=len(self.moves) + 1,
            uci=move.uci(),
            san=san,
            actor=actor,
            fen=self.board.fen(),
            timestamp=datetime.now(UTC).isoformat(),
            elapsed_ms=elapsed_ms,
        )
        self.moves.append(record)
        return record

    def resign(self, color: str) -> None:
        if self.status is not GameStatus.ACTIVE:
            raise MoveRejected("The game is already over.")
        if color not in {"white", "black"}:
            raise MoveRejected("Color must be white or black.")
        self.resigned_by = color
        self.version += 1

    def reset(self) -> None:
        self.board.reset()
        self.moves.clear()
        self.resigned_by = None
        self.version += 1

    def pgn(self) -> str:
        game = chess.pgn.Game.from_board(self.board)
        game.headers["Event"] = "AI Chess Lounge Exhibition"
        game.headers["Site"] = "AI Chess Lounge"
        game.headers["Date"] = self.created_at.strftime("%Y.%m.%d")
        game.headers["Round"] = "-"
        game.headers["White"] = "Human"
        game.headers["Black"] = (
            f"Stockfish ({self.stockfish_elo})"
            if self.opponent is OpponentKind.STOCKFISH
            else "Human"
        )
        game.headers["Result"] = self.result
        return str(game)

    def snapshot(self) -> GameSnapshot:
        status = self.status
        side = "white" if self.board.turn is chess.WHITE else "black"
        if status is not GameStatus.ACTIVE:
            banner = self._finished_banner(status)
        elif side == "white":
            banner = "Your move — claim space, create a threat, and keep your king safe."
        elif self.opponent is OpponentKind.STOCKFISH:
            banner = f"Stockfish is calculating at target Elo {self.stockfish_elo}."
        else:
            banner = "Black to move."

        return GameSnapshot(
            id=self.id,
            status=status,
            result=self.result,
            turn=side,
            version=self.version,
            fen=self.board.fen(),
            initial_fen=chess.STARTING_FEN,
            pgn=self.pgn(),
            legal_moves=[move.uci() for move in self.board.legal_moves],
            moves=list(self.moves),
            last_move=self.moves[-1].uci if self.moves else None,
            in_check=self.board.is_check(),
            can_move=status is GameStatus.ACTIVE and side == "white",
            opponent=self.opponent,
            engine=self.engine_summary,
            strategy_banner=banner,
        )

    def _finished_banner(self, status: GameStatus) -> str:
        if status is GameStatus.CHECKMATE:
            winner = "White" if self.board.turn is chess.BLACK else "Black"
            return f"Checkmate — {winner} wins {self.result}."
        if status is GameStatus.STALEMATE:
            return "Stalemate — the position is drawn."
        if status is GameStatus.RESIGNED:
            winner = "Black" if self.resigned_by == "white" else "White"
            return f"{self.resigned_by.title()} resigned — {winner} wins {self.result}."
        return f"Draw — final result {self.result}."
