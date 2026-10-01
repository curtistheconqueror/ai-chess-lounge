from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field, field_validator


class OpponentKind(StrEnum):
    STOCKFISH = "stockfish"
    HUMAN = "human"


class GameStatus(StrEnum):
    ACTIVE = "active"
    CHECKMATE = "checkmate"
    STALEMATE = "stalemate"
    DRAW = "draw"
    RESIGNED = "resigned"


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


class MoveRecord(BaseModel):
    ply: int
    uci: str
    san: str
    actor: str
    fen: str
    timestamp: str
    elapsed_ms: int | None = None


class EngineSummary(BaseModel):
    name: str
    available: bool
    target_elo: int
    move_time_ms: int
    version: str | None = None
    path: str | None = None


class GameSnapshot(BaseModel):
    id: str
    status: GameStatus
    result: str
    turn: str
    version: int
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


class HealthResponse(BaseModel):
    ok: bool = True
    service: str = "ai-chess-lounge-api"
    version: str
    stockfish_available: bool


class ApiError(BaseModel):
    detail: str
