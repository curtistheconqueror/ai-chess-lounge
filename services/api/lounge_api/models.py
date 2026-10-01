from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class OpponentKind(StrEnum):
    STOCKFISH = "stockfish"
    HUMAN = "human"


class GameStatus(StrEnum):
    WAITING = "waiting"
    ACTIVE = "active"
    PAUSED = "paused"
    CHECKMATE = "checkmate"
    STALEMATE = "stalemate"
    DRAW = "draw"
    RESIGNED = "resigned"
    ABORTED = "aborted"
    ADJUDICATED = "adjudicated"


class MatchState(StrEnum):
    CREATED = "created"
    WAITING = "waiting"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    ABORTED = "aborted"
    ADJUDICATED = "adjudicated"


class CreateGameRequest(BaseModel):
    opponent: OpponentKind = OpponentKind.STOCKFISH
    stockfish_elo: int = Field(default=1600, ge=800, le=3200)
    engine_move_time_ms: int = Field(default=450, ge=50, le=10_000)


class MoveRequest(BaseModel):
    move: str = Field(min_length=4, max_length=5)
    position_version: int = Field(ge=0)

    @field_validator("move")
    @classmethod
    def normalize_move(cls, value: str) -> str:
        return value.strip().lower()


class AdjudicateRequest(BaseModel):
    result: str

    @field_validator("result")
    @classmethod
    def validate_result(cls, value: str) -> str:
        if value not in {"1-0", "0-1", "1/2-1/2"}:
            raise ValueError("Result must be 1-0, 0-1, or 1/2-1/2.")
        return value


class MoveRecord(BaseModel):
    generation: int = 0
    ply: int
    uci: str
    san: str
    actor: str
    fen: str
    timestamp: str
    elapsed_ms: int | None = None


class MatchEvent(BaseModel):
    sequence: int
    type: str
    position_version: int
    payload: dict[str, Any] = Field(default_factory=dict)
    timestamp: str


class EngineSummary(BaseModel):
    name: str
    available: bool
    target_elo: int
    move_time_ms: int
    version: str | None = None
    path: str | None = None


class GameSnapshot(BaseModel):
    id: str
    lifecycle: MatchState
    status: GameStatus
    result: str
    turn: str
    version: int
    revision: int
    generation: int
    event_sequence: int
    fen: str
    initial_fen: str
    pgn: str
    legal_moves: list[str]
    moves: list[MoveRecord]
    last_move: str | None
    in_check: bool
    can_move: bool
    opponent: OpponentKind
    engine: EngineSummary | None
    strategy_banner: str
    created_at: str
    updated_at: str


class HealthResponse(BaseModel):
    ok: bool = True
    service: str = "ai-chess-lounge-api"
    version: str
    stockfish_available: bool


class ApiError(BaseModel):
    detail: str
