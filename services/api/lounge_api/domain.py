from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from time import perf_counter
from uuid import uuid4

import chess
import chess.pgn

from .models import (
    ClockSnapshot,
    Consultation,
    EngineSummary,
    GameSnapshot,
    GameStatus,
    MatchEvent,
    MatchState,
    MoveRecord,
    OpponentKind,
    SeatChange,
)
from .player_protocol import PlayerConfiguration, PlayerMoveMetadata


class MoveRejected(ValueError):
    """Raised when a proposed move cannot be applied to the current position."""


class StalePosition(MoveRejected):
    """Raised when a client submits against an older position version."""


class MatchTransitionRejected(ValueError):
    """Raised when a requested lifecycle transition is not permitted."""


class ClockExpired(MoveRejected, MatchTransitionRejected):
    """Raised when an action arrives after the authoritative turn deadline."""


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
    initial_time_ms: int = 300_000
    increment_ms: int = 2_000
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
    draw_reason: str | None = None
    adjudicated_result: str | None = None
    engine_summary: EngineSummary | None = None
    comparison_snapshot: dict | None = None
    white_remaining_ms: int | None = None
    black_remaining_ms: int | None = None
    turn_started_at: datetime | None = None
    timed_out_by: str | None = None
    white_player: PlayerConfiguration | None = None
    black_player: PlayerConfiguration | None = None
    seat_history: list[SeatChange] = field(default_factory=list)
    consultations: list[Consultation] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.white_remaining_ms is None:
            self.white_remaining_ms = self.initial_time_ms
        if self.black_remaining_ms is None:
            self.black_remaining_ms = self.initial_time_ms
        if self.white_player is None:
            self.white_player = PlayerConfiguration.human("white")
        if self.black_player is None:
            self.black_player = (
                PlayerConfiguration.stockfish(
                    "black",
                    target_elo=self.stockfish_elo,
                    move_time_ms=self.engine_move_time_ms,
                )
                if self.opponent is OpponentKind.STOCKFISH
                else PlayerConfiguration.human("black")
            )

    def player_for_color(self, color: str) -> PlayerConfiguration:
        player = self.white_player if color == "white" else self.black_player
        assert player is not None
        return player

    def active_player(self) -> PlayerConfiguration:
        return self.player_for_color("white" if self.board.turn is chess.WHITE else "black")

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
        if self.draw_reason:
            return GameStatus.DRAW
        if self.timed_out_by:
            return GameStatus.TIMEOUT
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
        if self.draw_reason:
            return "1/2-1/2"
        if self.adjudicated_result:
            return self.adjudicated_result
        if self.timed_out_by == "white":
            return "0-1"
        if self.timed_out_by == "black":
            return "1-0"
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
        now: datetime | None = None,
        player_metadata: PlayerMoveMetadata | None = None,
    ) -> MoveRecord:
        action_time = self._normalize_now(now)
        if self.lifecycle is not MatchState.RUNNING or self.status is not GameStatus.ACTIVE:
            raise MoveRejected("The game is already over.")
        if self.expire_if_needed(action_time):
            raise ClockExpired(f"{self.timed_out_by.title()} lost on time.")
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

        moving_color = "white" if self.board.turn is chess.WHITE else "black"
        if not self._settle_active_clock(action_time, add_increment=True):
            raise ClockExpired(f"{moving_color.title()} lost on time.")
        san = self.board.san(move)
        self.board.push(move)
        self.version += 1
        self.revision += 1
        self.updated_at = action_time
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
            timestamp=action_time.isoformat(),
            elapsed_ms=elapsed_ms,
            white_remaining_ms=self._stored_remaining("white"),
            black_remaining_ms=self._stored_remaining("black"),
            player_metadata=player_metadata,
        )
        self.moves.append(record)
        if self.status is not GameStatus.ACTIVE:
            self.lifecycle = MatchState.COMPLETED
            self.turn_started_at = None
        else:
            self.turn_started_at = action_time
        return record

    def resign(self, color: str, *, now: datetime | None = None) -> None:
        action_time = self._normalize_now(now)
        if self.status is not GameStatus.ACTIVE:
            raise MoveRejected("The game is already over.")
        if self.expire_if_needed(action_time):
            raise ClockExpired(f"{self.timed_out_by.title()} lost on time.")
        if color not in {"white", "black"}:
            raise MoveRejected("Color must be white or black.")
        self._settle_active_clock(action_time, add_increment=False)
        self.resigned_by = color
        self.version += 1
        self.revision += 1
        self.updated_at = action_time
        self.lifecycle = MatchState.COMPLETED
        self.turn_started_at = None

    def draw_claim_options(self) -> tuple[bool, list[str]]:
        if self.status is not GameStatus.ACTIVE or not self.active_player().is_human:
            return False, []
        current = self.board.is_fifty_moves() or self.board.is_repetition(3)
        if current:
            return True, []
        # Never mutate the live board while building a snapshot.
        candidate = self.board.copy()
        moves = []
        if candidate.can_claim_draw():
            for move in list(candidate.legal_moves):
                candidate.push(move)
                if candidate.is_fifty_moves() or candidate.is_repetition(3):
                    moves.append(move.uci())
                candidate.pop()
        return False, moves

    def claim_draw(self, intended_move: str | None, *, now: datetime | None = None) -> None:
        action_time = self._normalize_now(now)
        if self.status is not GameStatus.ACTIVE or not self.active_player().is_human:
            raise MoveRejected("Only the human whose turn it is may claim a draw.")
        if self.expire_if_needed(action_time):
            raise ClockExpired(f"{self.timed_out_by.title()} lost on time.")
        candidate = self.board.copy()
        if intended_move is not None:
            try:
                move = chess.Move.from_uci(intended_move)
            except ValueError as exc:
                raise MoveRejected("Invalid intended draw-claim move.") from exc
            if move not in candidate.legal_moves:
                raise MoveRejected("The intended draw-claim move is not legal.")
            candidate.push(move)
        if candidate.is_repetition(3):
            reason = "threefold_repetition"
        elif candidate.is_fifty_moves():
            reason = "fifty_move_rule"
        else:
            raise MoveRejected("This position does not support the requested draw claim.")
        self._settle_active_clock(action_time, add_increment=False)
        self.draw_reason = reason
        self.lifecycle = MatchState.COMPLETED
        self.version += 1
        self.revision += 1
        self.updated_at = action_time

    def change_seat(self, color: str, player: PlayerConfiguration, *, now: datetime) -> SeatChange:
        if self.lifecycle is not MatchState.PAUSED:
            raise MatchTransitionRejected("Pause the match before changing a seat.")
        if color not in {"white", "black"}:
            raise MatchTransitionRejected("Color must be white or black.")
        previous = self.player_for_color(color)
        if previous == player:
            raise MatchTransitionRejected("This player already controls the seat.")
        if player.settings.get("color", color) != color:
            raise MatchTransitionRejected("The player configuration belongs to the other color.")
        if color == "white":
            self.white_player = player.model_copy(deep=True)
        else:
            self.black_player = player.model_copy(deep=True)
        self.version += 1
        self.revision += 1
        self.updated_at = self._normalize_now(now)
        change = SeatChange(
            color=color,
            previous_player=previous.model_copy(deep=True),
            player=player.model_copy(deep=True),
            after_ply=len(self.moves),
            position_version=self.version,
            timestamp=self.updated_at.isoformat(),
        )
        self.seat_history.append(change)
        self.opponent = (
            OpponentKind.STOCKFISH
            if self.player_for_color("white").is_human
            and self.player_for_color("black").adapter_id == "stockfish"
            else OpponentKind.HUMAN
        )
        return change

    def reset(self, *, now: datetime | None = None) -> None:
        action_time = self._normalize_now(now)
        self.board.reset()
        self.moves.clear()
        self.seat_history.clear()
        self.consultations.clear()
        self.resigned_by = None
        self.draw_reason = None
        self.adjudicated_result = None
        self.timed_out_by = None
        self.white_remaining_ms = self.initial_time_ms
        self.black_remaining_ms = self.initial_time_ms
        self.turn_started_at = action_time
        self.lifecycle = MatchState.RUNNING
        self.comparison_snapshot = None
        self.generation += 1
        self.version += 1
        self.revision += 1
        self.updated_at = action_time

    def transition(self, target: MatchState, *, now: datetime | None = None) -> None:
        action_time = self._normalize_now(now)
        if target not in ALLOWED_TRANSITIONS[self.lifecycle]:
            raise MatchTransitionRejected(
                f"Cannot transition a match from {self.lifecycle.value} to {target.value}."
            )
        if self.lifecycle is MatchState.RUNNING:
            if self.expire_if_needed(action_time):
                raise ClockExpired(f"{self.timed_out_by.title()} lost on time.")
            if target is MatchState.PAUSED:
                self._settle_active_clock(action_time, add_increment=False)
            else:
                self.turn_started_at = None
        elif target is MatchState.RUNNING:
            self.turn_started_at = action_time
        self.lifecycle = target
        self.revision += 1
        self.updated_at = action_time

    def start(self, *, now: datetime | None = None) -> None:
        self.transition(MatchState.RUNNING, now=now)

    def pause(self, *, now: datetime | None = None) -> None:
        self.transition(MatchState.PAUSED, now=now)

    def resume(self, *, now: datetime | None = None) -> None:
        self.transition(MatchState.RUNNING, now=now)

    def abort(self, *, now: datetime | None = None) -> None:
        self.transition(MatchState.ABORTED, now=now)

    def adjudicate(self, result: str, *, now: datetime | None = None) -> None:
        if result not in {"1-0", "0-1", "1/2-1/2"}:
            raise MatchTransitionRejected("Invalid adjudication result.")
        self.transition(MatchState.ADJUDICATED, now=now)
        self.adjudicated_result = result

    def remaining_times(self, now: datetime | None = None) -> tuple[int, int]:
        action_time = self._normalize_now(now)
        white = self._stored_remaining("white")
        black = self._stored_remaining("black")
        if (
            self.lifecycle is MatchState.RUNNING
            and self.status is GameStatus.ACTIVE
            and self.turn_started_at is not None
        ):
            elapsed_ms = self._elapsed_since_turn_start(action_time)
            if self.board.turn is chess.WHITE:
                white = max(0, white - elapsed_ms)
            else:
                black = max(0, black - elapsed_ms)
        return white, black

    def deadline_at(self) -> datetime | None:
        if (
            self.lifecycle is not MatchState.RUNNING
            or self.status is not GameStatus.ACTIVE
            or self.turn_started_at is None
        ):
            return None
        color = "white" if self.board.turn is chess.WHITE else "black"
        return self.turn_started_at + timedelta(milliseconds=self._stored_remaining(color))

    def expire_if_needed(self, now: datetime | None = None) -> bool:
        action_time = self._normalize_now(now)
        if (
            self.lifecycle is not MatchState.RUNNING
            or self.status is not GameStatus.ACTIVE
            or self.turn_started_at is None
        ):
            return False
        color = "white" if self.board.turn is chess.WHITE else "black"
        remaining = self._stored_remaining(color) - self._elapsed_since_turn_start(action_time)
        if remaining > 0:
            return False
        self._set_remaining(color, 0)
        self.timed_out_by = color
        self.lifecycle = MatchState.COMPLETED
        self.turn_started_at = None
        self.version += 1
        self.revision += 1
        self.updated_at = action_time
        return True

    def clock_snapshot(self, now: datetime | None = None) -> ClockSnapshot:
        action_time = self._normalize_now(now)
        white, black = self.remaining_times(action_time)
        deadline = self.deadline_at()
        return ClockSnapshot(
            initial_time_ms=self.initial_time_ms,
            increment_ms=self.increment_ms,
            white_remaining_ms=white,
            black_remaining_ms=black,
            turn_started_at=(
                self.turn_started_at.isoformat() if self.turn_started_at is not None else None
            ),
            deadline_at=deadline.isoformat() if deadline is not None else None,
            server_time=action_time.isoformat(),
            timed_out_by=self.timed_out_by,
        )

    def _settle_active_clock(self, now: datetime, *, add_increment: bool) -> bool:
        if self.turn_started_at is None:
            self.turn_started_at = now
        color = "white" if self.board.turn is chess.WHITE else "black"
        remaining = max(
            0,
            self._stored_remaining(color) - self._elapsed_since_turn_start(now),
        )
        self._set_remaining(color, remaining)
        if remaining == 0:
            self.timed_out_by = color
            self.lifecycle = MatchState.COMPLETED
            self.turn_started_at = None
            self.version += 1
            self.revision += 1
            self.updated_at = now
            return False
        if add_increment:
            self._set_remaining(color, remaining + self.increment_ms)
        self.turn_started_at = None
        return True

    def _elapsed_since_turn_start(self, now: datetime) -> int:
        if self.turn_started_at is None:
            return 0
        started = self._normalize_now(self.turn_started_at)
        return max(0, int((now - started).total_seconds() * 1000))

    def _stored_remaining(self, color: str) -> int:
        value = self.white_remaining_ms if color == "white" else self.black_remaining_ms
        return self.initial_time_ms if value is None else value

    def _set_remaining(self, color: str, value: int) -> None:
        if color == "white":
            self.white_remaining_ms = value
        else:
            self.black_remaining_ms = value

    @staticmethod
    def _normalize_now(value: datetime | None) -> datetime:
        if value is None:
            return datetime.now(UTC)
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def event(
        self,
        event_type: str,
        payload: dict[str, object] | None = None,
        *,
        now: datetime | None = None,
    ) -> MatchEvent:
        self.event_sequence += 1
        return MatchEvent(
            sequence=self.event_sequence,
            type=event_type,
            position_version=self.version,
            payload=payload or {},
            timestamp=self._normalize_now(now).isoformat(),
        )

    def pgn(self) -> str:
        game = chess.pgn.Game.from_board(self.board)
        game.headers["Event"] = "AI Chess Lounge Exhibition"
        game.headers["Site"] = "AI Chess Lounge"
        game.headers["Date"] = self.created_at.strftime("%Y.%m.%d")
        game.headers["Round"] = "-"
        for color in ("white", "black"):
            original = next(
                (c.previous_player for c in self.seat_history if c.color == color),
                self.player_for_color(color),
            )
            game.headers[color.title()] = original.display_name
            if self.seat_history:
                game.headers[f"{color.title()}Current"] = self.player_for_color(color).display_name
        if self.seat_history:
            game.headers["SeatChanges"] = str(len(self.seat_history))
            nodes = [game, *game.mainline()]
            for change in self.seat_history:
                annotation = (
                    (
                        f"Seat change ({change.color}): {change.previous_player.display_name} "
                        f"to {change.player.display_name} ({change.player.provider}, "
                        f"{change.player.model}, {change.player.division.value})"
                    )
                    .replace("{", "(")
                    .replace("}", ")")
                    .replace("\n", " ")
                )
                node = nodes[change.after_ply]
                node.comment = f"{node.comment} {annotation}".strip()
        if self.consultations:
            game.headers["Assistance"] = "Human-AI Team exhibition"
            game.headers["Consultations"] = str(len(self.consultations))
            nodes = [game, *game.mainline()]
            for advice in self.consultations:
                text = (
                    (
                        f"Consultation ({advice.color}): {advice.advisor.display_name}; "
                        f"{advice.advisor.provider}/{advice.advisor.model}; "
                        f"{advice.advisor.effort or 'default'}; {advice.advisor.division.value}; "
                        f"suggested {advice.san or 'no published move'}"
                    )
                    .replace("{", "(")
                    .replace("}", ")")
                    .replace("\n", " ")
                )
                node = nodes[advice.after_ply]
                node.comment = f"{node.comment} {text}".strip()
        game.headers["Result"] = self.result
        return str(game)

    def consultation_snapshots(self, now: datetime) -> list[Consultation]:
        records = []
        for item in self.consultations:
            stale = item.status in {"pending", "ready"} and (
                item.revision != self.revision
                or item.position_version != self.version
                or self.lifecycle is not MatchState.RUNNING
                or (item.status == "pending" and datetime.fromisoformat(item.deadline_at) <= now)
            )
            records.append(item.model_copy(update={"status": "stale"}) if stale else item)
        return records

    def snapshot(self, *, now: datetime | None = None) -> GameSnapshot:
        snapshot_time = self._normalize_now(now)
        status = self.status
        side = "white" if self.board.turn is chess.WHITE else "black"
        if status is not GameStatus.ACTIVE:
            banner = self._finished_banner(status)
        else:
            active_player = self.player_for_color(side)
            banner = (
                f"{active_player.display_name} to move."
                if active_player.is_human
                else f"{active_player.display_name} is calculating through "
                f"{active_player.provider}."
            )

        can_claim_draw, draw_claim_moves = self.draw_claim_options()
        return GameSnapshot(
            id=self.id,
            comparison_snapshot=self.comparison_snapshot,
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
                and self.player_for_color(side).is_human
            ),
            can_claim_draw=can_claim_draw,
            draw_claim_moves=draw_claim_moves,
            draw_reason=self.draw_reason,
            seat_history=list(self.seat_history),
            consultations=self.consultation_snapshots(snapshot_time),
            opponent=self.opponent,
            engine=self.engine_summary,
            white_player=self.player_for_color("white"),
            black_player=self.player_for_color("black"),
            clock=self.clock_snapshot(snapshot_time),
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
        if status is GameStatus.TIMEOUT:
            winner = "Black" if self.timed_out_by == "white" else "White"
            return f"{self.timed_out_by.title()} lost on time — {winner} wins {self.result}."
        if status is GameStatus.PAUSED:
            return "Match paused — the authoritative position is safely preserved."
        if status is GameStatus.ABORTED:
            return "Match aborted — no competitive result was recorded."
        if status is GameStatus.ADJUDICATED:
            return f"Match adjudicated — final result {self.result}."
        if status is GameStatus.WAITING:
            return "Waiting for the match to start."
        return f"Draw — final result {self.result}."
