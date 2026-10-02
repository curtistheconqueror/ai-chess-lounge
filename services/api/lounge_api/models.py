from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator

from .player_protocol import (
    AssistanceDivision,
    EffortLevel,
    PlayerConfiguration,
    PlayerMoveMetadata,
)
from .player_protocol import (
    MoveProposal as PlayerMoveProposal,
)
from .player_protocol import (
    MoveRequest as PlayerMoveRequest,
)


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
    TIMEOUT = "timeout"
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
    initial_time_ms: int = Field(default=300_000, ge=100, le=86_400_000)
    increment_ms: int = Field(default=2_000, ge=0, le=60_000)
    white_player: PlayerConfiguration | None = None
    black_player: PlayerConfiguration | None = None


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


class RunnerPairingCreate(BaseModel):
    display_name: str = Field(min_length=1, max_length=120)
    provider: str = Field(min_length=1, max_length=80)
    model: str = Field(min_length=1, max_length=120)
    division: AssistanceDivision = AssistanceDivision.LEGAL_ASSIST
    effort: EffortLevel | None = None
    pairing_ttl_ms: int = Field(default=600_000, ge=60_000, le=1_800_000)
    session_ttl_ms: int = Field(default=14_400_000, ge=300_000, le=86_400_000)
    move_timeout_ms: int = Field(default=30_000, ge=1, le=120_000)
    webhook_url: str | None = Field(default=None, max_length=2_048)


class RunnerPairingClaim(BaseModel):
    pairing_code: str = Field(min_length=12, max_length=128)


class RunnerPairingRecord(BaseModel):
    pairing_id: str
    code_digest: str
    player: PlayerConfiguration
    session_ttl_ms: int
    webhook_url: str | None
    created_at: str
    expires_at: str
    claimed_at: str | None = None


class RunnerPairingResponse(BaseModel):
    pairing_id: str
    pairing_code: str
    expires_at: str
    player: PlayerConfiguration


class RunnerSessionRecord(BaseModel):
    session_id: str
    pairing_id: str
    player: PlayerConfiguration
    token_digest: str
    issuer_digest: str
    permissions: list[str]
    webhook_url: str | None
    created_at: str
    expires_at: str
    last_heartbeat_at: str
    revoked_at: str | None = None


class RunnerSessionCredentials(BaseModel):
    session_id: str
    runner_token: str
    signing_key: str
    permissions: list[str]
    expires_at: str
    player: PlayerConfiguration
    websocket_path: str = "/ws/runners"
    next_turn_path: str = "/api/runner-sessions/turns/next"
    proposal_path_template: str = "/api/runner-sessions/turns/{delivery_id}/proposal"
    heartbeat_path: str = "/api/runner-sessions/heartbeat"


class RunnerSessionStatus(BaseModel):
    session_id: str
    player: PlayerConfiguration
    player_id: str
    display_name: str
    provider: str
    model: str
    permissions: list[str]
    transport: str
    connected: bool
    created_at: str
    expires_at: str
    last_heartbeat_at: str
    expired: bool
    revoked: bool


class RunnerTurnDelivery(BaseModel):
    delivery_id: str
    expires_at: str
    request: PlayerMoveRequest


class RunnerProposalSubmission(BaseModel):
    idempotency_key: str = Field(
        min_length=8,
        max_length=128,
        pattern=r"^[A-Za-z0-9._:-]+$",
    )
    proposal: PlayerMoveProposal
    signature: str = Field(pattern=r"^[0-9a-f]{64}$")


class RunnerProposalReceipt(BaseModel):
    delivery_id: str
    accepted: bool = True
    duplicate: bool = False


class MoveRecord(BaseModel):
    generation: int = 0
    ply: int
    uci: str
    san: str
    actor: str
    fen: str
    timestamp: str
    elapsed_ms: int | None = None
    white_remaining_ms: int
    black_remaining_ms: int
    player_metadata: PlayerMoveMetadata | None = None


class MatchEvent(BaseModel):
    sequence: int
    type: str
    position_version: int
    payload: dict[str, Any] = Field(default_factory=dict)
    timestamp: str


class TurnLease(BaseModel):
    match_id: str
    owner_id: str
    token: str
    position_version: int
    acquired_at: str
    expires_at: str


class EngineSummary(BaseModel):
    name: str
    available: bool
    target_elo: int
    move_time_ms: int
    version: str | None = None


class AnalysisPoint(BaseModel):
    ply: int
    fen: str
    score_cp: int
    mate: int | None = None
    best_move: str | None = None
    pv_san: list[str] = Field(default_factory=list)
    depth: int | None = None
    classification: str | None = None


class GameAnalysis(BaseModel):
    game_id: str
    generation: int
    position_version: int
    engine_name: str
    engine_version: str | None = None
    perspective: str = "white"
    points: list[AnalysisPoint]


class ClockSnapshot(BaseModel):
    initial_time_ms: int
    increment_ms: int
    white_remaining_ms: int
    black_remaining_ms: int
    turn_started_at: str | None
    deadline_at: str | None
    server_time: str
    timed_out_by: str | None


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
    white_player: PlayerConfiguration
    black_player: PlayerConfiguration
    clock: ClockSnapshot
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
