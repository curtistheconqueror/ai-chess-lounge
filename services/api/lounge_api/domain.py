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
    MatchEvent,
    MatchState,
    MoveRecord,
    OpponentKind,
)


class MoveRejected(ValueError):
    """Raised when a proposed move cannot be applied to the current position."""


class StalePosition(MoveRejected):
    """Raised when a client submits against an older position version."""


class MatchTransitionRejected(ValueError):
    """Raised when a requested lifecycle transition is not permitted."""


ALLOWED_TRANSITIONS: dict[MatchState, set[MatchState]] = {
    MatchState.CREATED: {MatchState.WAITING, MatchState.RUNNING, MatchState.ABORTED},
    MatchState.WAITING: {MatchState.RUNNING, MatchState.ABORTED},
    MatchState.RUNNING: {
        MatchState.PAUSED,
        MatchState.COMPLETED,
        MatchState.ABORTED,
        MatchState.ADJUDICATED,
    },
    MatchState.PAUSED: {
        MatchState.RUNNING,
        MatchState.ABORTED,
        MatchState.ADJUDICATED,
    },
    MatchState.COMPLETED: set(),
    MatchState.ABORTED: set(),
    MatchState.ADJUDICATED: set(),
}


@dataclass(slots=True)
class GameSession:
    opponent: OpponentKind = OpponentKind.STOCKFISH
    stockfish_elo: int = 1600
    engine_move_time_ms: int = 450
    id: str = field(default_factory=lambda: str(uuid4()))
    board: chess.Board = field(default_factory=chess.Board)
    initial_fen: str = chess.STARTING_FEN
    lifecycle: MatchState = MatchState.CREATED
    version: int = 0
    revision: int = 0
    generation: int = 0
    event_sequence: int = 0
    moves: list[MoveRecord] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    resigned_by: str | None = None
    adjudicated_result: str | None = None
    engine_summary: EngineSummary | None = None

    @property
    def status(self) -> GameStatus:
        if self.lifecycle in {MatchState.CREATED, MatchState.WAITING}:
            return GameStatus.WAITING
        if self.lifecycle is MatchState.PAUSED:
            return GameStatus.PAUSED
        if self.lifecycle is MatchState.ABORTED:
            return GameStatus.ABORTED
        if self.lifecycle is MatchState.ADJUDICATED:
            return GameStatus.ADJUDICATED
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
        if self.adjudicated_result:
            return self.adjudicated_result
        if self.resigned_by == "white":
            return "0-1"
        if self.resigned_by == "black":
            return "1-0"
        return (
            self.board.result(claim_draw=False)
            if self.board.is_game_over(claim_draw=False)
            else "*"
        )

    def apply_uci(
        self,
        uci: str,
        *,
        actor: str,
        position_version: int | None = None,
        started_at: float | None = None,
    ) -> MoveRecord:
        if self.lifecycle is not MatchState.RUNNING or self.status is not GameStatus.ACTIVE:
            raise MoveRejected("The game is already over.")
        if position_version is not None and position_version != self.version:
            raise StalePosition(
                "Position changed: expected version "
                f"{position_version}, current version is {self.version}."
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
        self.revision += 1
        self.updated_at = datetime.now(UTC)
        elapsed_ms = None
        if started_at is not None:
            elapsed_ms = max(0, round((perf_counter() - started_at) * 1000))
        record = MoveRecord(
            generation=self.generation,
            ply=len(self.moves) + 1,
            uci=move.uci(),
            san=san,
            actor=actor,
            fen=self.board.fen(),
            timestamp=datetime.now(UTC).isoformat(),
            elapsed_ms=elapsed_ms,
        )
        self.moves.append(record)
        if self.status is not GameStatus.ACTIVE:
            self.lifecycle = MatchState.COMPLETED
        return record

    def resign(self, color: str) -> None:
        if self.status is not GameStatus.ACTIVE:
            raise MoveRejected("The game is already over.")
        if color not in {"white", "black"}:
            raise MoveRejected("Color must be white or black.")
        self.resigned_by = color
        self.version += 1
        self.revision += 1
        self.updated_at = datetime.now(UTC)
        self.lifecycle = MatchState.COMPLETED

    def reset(self) -> None:
        self.board.reset()
        self.moves.clear()
        self.resigned_by = None
        self.adjudicated_result = None
        self.lifecycle = MatchState.RUNNING
        self.generation += 1
        self.version += 1
        self.revision += 1
        self.updated_at = datetime.now(UTC)

    def transition(self, target: MatchState) -> None:
        if target not in ALLOWED_TRANSITIONS[self.lifecycle]:
            raise MatchTransitionRejected(
                f"Cannot transition a match from {self.lifecycle.value} to {target.value}."
            )
        self.lifecycle = target
        self.revision += 1
        self.updated_at = datetime.now(UTC)

    def start(self) -> None:
        self.transition(MatchState.RUNNING)

    def pause(self) -> None:
        self.transition(MatchState.PAUSED)

    def resume(self) -> None:
        self.transition(MatchState.RUNNING)

    def abort(self) -> None:
        self.transition(MatchState.ABORTED)

    def adjudicate(self, result: str) -> None:
        if result not in {"1-0", "0-1", "1/2-1/2"}:
            raise MatchTransitionRejected("Invalid adjudication result.")
        self.transition(MatchState.ADJUDICATED)
        self.adjudicated_result = result

    def event(self, event_type: str, payload: dict[str, object] | None = None) -> MatchEvent:
        self.event_sequence += 1
        return MatchEvent(
            sequence=self.event_sequence,
            type=event_type,
            position_version=self.version,
            payload=payload or {},
            timestamp=datetime.now(UTC).isoformat(),
        )

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
            lifecycle=self.lifecycle,
            status=status,
            result=self.result,
            turn=side,
            version=self.version,
            revision=self.revision,
            generation=self.generation,
            event_sequence=self.event_sequence,
            fen=self.board.fen(),
            initial_fen=self.initial_fen,
            pgn=self.pgn(),
            legal_moves=[move.uci() for move in self.board.legal_moves],
            moves=list(self.moves),
            last_move=self.moves[-1].uci if self.moves else None,
            in_check=self.board.is_check(),
            can_move=(
                self.lifecycle is MatchState.RUNNING
                and status is GameStatus.ACTIVE
                and side == "white"
            ),
            opponent=self.opponent,
            engine=self.engine_summary,
            strategy_banner=banner,
            created_at=self.created_at.isoformat(),
            updated_at=self.updated_at.isoformat(),
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
        if status is GameStatus.PAUSED:
            return "Match paused — the authoritative position is safely preserved."
        if status is GameStatus.ABORTED:
            return "Match aborted — no competitive result was recorded."
        if status is GameStatus.ADJUDICATED:
            return f"Match adjudicated — final result {self.result}."
        if status is GameStatus.WAITING:
            return "Waiting for the match to start."
        return f"Draw — final result {self.result}."
