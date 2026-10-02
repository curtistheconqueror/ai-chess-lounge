from __future__ import annotations

import re
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator

PROTOCOL_VERSION = "1.0"

PUBLIC_SETTINGS_BY_ADAPTER: dict[str, frozenset[str]] = {
    "human": frozenset({"color"}),
    "scripted": frozenset({"moves", "move_timeout_ms", "spectator_delay_ms"}),
    "stockfish": frozenset(
        {
            "color",
            "target_elo",
            "move_time_ms",
            "move_timeout_ms",
            "spectator_delay_ms",
        }
    ),
    "openai": frozenset(
        {
            "color",
            "max_output_tokens",
            "move_timeout_ms",
            "spectator_delay_ms",
        }
    ),
    "anthropic": frozenset(
        {
            "color",
            "max_output_tokens",
            "move_timeout_ms",
            "spectator_delay_ms",
        }
    ),
    "google": frozenset(
        {
            "color",
            "max_output_tokens",
            "move_timeout_ms",
            "spectator_delay_ms",
        }
    ),
    "openrouter": frozenset(
        {
            "color",
            "max_output_tokens",
            "move_timeout_ms",
            "spectator_delay_ms",
        }
    ),
    "ollama": frozenset(
        {
            "color",
            "max_output_tokens",
            "move_timeout_ms",
            "spectator_delay_ms",
        }
    ),
    "vllm": frozenset(
        {
            "color",
            "max_output_tokens",
            "move_timeout_ms",
            "spectator_delay_ms",
        }
    ),
    "remote_runner": frozenset(
        {
            "runner_id",
            "move_timeout_ms",
            "spectator_delay_ms",
        }
    ),
}


class AssistanceDivision(StrEnum):
    PURE_REASONING = "pure_reasoning"
    LEGAL_ASSIST = "legal_assist"
    TACTICAL_METADATA = "tactical_metadata"
    ENGINE_ASSISTED = "engine_assisted"
    OPEN_AGENTIC = "open_agentic"
    HUMAN_AI_TEAM = "human_ai_team"


class EffortLevel(StrEnum):
    FAST = "fast"
    BALANCED = "balanced"
    DEEP = "deep"
    MAXIMUM = "maximum"


class ConnectionMode(StrEnum):
    HUMAN = "human"
    LOCAL = "local"
    DIRECT_API = "direct_api"
    REMOTE_RUNNER = "remote_runner"
    SUBSCRIPTION_BRIDGE = "subscription_bridge"


class UsageMetrics(BaseModel):
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    reasoning_tokens: int | None = Field(default=None, ge=0)
    estimated_cost_usd: float | None = Field(default=None, ge=0)


class PlayerConfiguration(BaseModel):
    protocol_version: str = PROTOCOL_VERSION
    player_id: str = Field(default_factory=lambda: str(uuid4()), min_length=1, max_length=120)
    adapter_id: str = Field(min_length=1, max_length=80, pattern=r"^[a-z0-9][a-z0-9._-]*$")
    display_name: str = Field(min_length=1, max_length=120)
    provider: str = Field(min_length=1, max_length=80)
    model: str = Field(min_length=1, max_length=120)
    connection_mode: ConnectionMode
    effort: EffortLevel | None = None
    division: AssistanceDivision = AssistanceDivision.LEGAL_ASSIST
    settings: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_public_settings(self) -> PlayerConfiguration:
        allowed = PUBLIC_SETTINGS_BY_ADAPTER.get(self.adapter_id, frozenset())
        unsupported = sorted(set(self.settings).difference(allowed))
        if unsupported:
            raise ValueError(
                "Player settings cannot contain credentials or undisclosed fields; "
                f"unsupported public settings: {', '.join(unsupported)}."
            )
        if self.adapter_id not in PUBLIC_SETTINGS_BY_ADAPTER and self.settings:
            raise ValueError("Unregistered adapters cannot declare public settings.")

        color = self.settings.get("color")
        if color is not None and color not in {"white", "black"}:
            raise ValueError("Player color must be white or black.")

        for key, minimum, maximum in (
            ("move_timeout_ms", 1, 86_400_000),
            ("spectator_delay_ms", 0, 2_000),
        ):
            setting = self.settings.get(key)
            if setting is not None and (
                type(setting) is not int or not minimum <= setting <= maximum
            ):
                raise ValueError(f"{key} must be an integer between {minimum} and {maximum}.")

        if self.adapter_id == "stockfish":
            target_elo = self.settings.get("target_elo", 1600)
            move_time_ms = self.settings.get("move_time_ms", 450)
            if type(target_elo) is not int or not 800 <= target_elo <= 3200:
                raise ValueError("Stockfish target_elo must be between 800 and 3200.")
            if type(move_time_ms) is not int or not 50 <= move_time_ms <= 10_000:
                raise ValueError("Stockfish move_time_ms must be between 50 and 10000.")

        if self.adapter_id == "openai":
            max_output_tokens = self.settings.get("max_output_tokens", 4_096)
            if type(max_output_tokens) is not int or not 256 <= max_output_tokens <= 32_768:
                raise ValueError("OpenAI max_output_tokens must be between 256 and 32768.")
            move_timeout_ms = self.settings.get("move_timeout_ms", 20_000)
            if type(move_timeout_ms) is not int or not 1 <= move_timeout_ms <= 120_000:
                raise ValueError("OpenAI move_timeout_ms must be between 1 and 120000.")

        if self.adapter_id == "anthropic":
            max_output_tokens = self.settings.get("max_output_tokens", 4_096)
            if type(max_output_tokens) is not int or not 256 <= max_output_tokens <= 128_000:
                raise ValueError("Anthropic max_output_tokens must be between 256 and 128000.")
            move_timeout_ms = self.settings.get("move_timeout_ms", 20_000)
            if type(move_timeout_ms) is not int or not 1 <= move_timeout_ms <= 120_000:
                raise ValueError("Anthropic move_timeout_ms must be between 1 and 120000.")

        if self.adapter_id == "google":
            max_output_tokens = self.settings.get("max_output_tokens", 4_096)
            if type(max_output_tokens) is not int or not 256 <= max_output_tokens <= 65_536:
                raise ValueError("Google Gemini max_output_tokens must be between 256 and 65536.")
            move_timeout_ms = self.settings.get("move_timeout_ms", 20_000)
            if type(move_timeout_ms) is not int or not 1 <= move_timeout_ms <= 120_000:
                raise ValueError("Google Gemini move_timeout_ms must be between 1 and 120000.")

        if self.adapter_id in {"openrouter", "ollama", "vllm"}:
            max_output_tokens = self.settings.get("max_output_tokens", 4_096)
            if type(max_output_tokens) is not int or not 256 <= max_output_tokens <= 131_072:
                raise ValueError(
                    f"{self.adapter_id} max_output_tokens must be between 256 and 131072."
                )
            move_timeout_ms = self.settings.get("move_timeout_ms", 20_000)
            if type(move_timeout_ms) is not int or not 1 <= move_timeout_ms <= 120_000:
                raise ValueError(f"{self.adapter_id} move_timeout_ms must be between 1 and 120000.")

        if self.adapter_id == "remote_runner":
            runner_id = self.settings.get("runner_id")
            if not isinstance(runner_id, str) or not re.fullmatch(
                r"[A-Za-z0-9][A-Za-z0-9._:-]{7,119}", runner_id
            ):
                raise ValueError("Remote runner_id must be a safe identifier of 8-120 characters.")
            if runner_id != self.player_id:
                raise ValueError("Remote runner_id must match the scoped player_id.")
            if self.connection_mode is not ConnectionMode.REMOTE_RUNNER:
                raise ValueError("Remote runner seats must use remote_runner connection mode.")
            move_timeout_ms = self.settings.get("move_timeout_ms", 30_000)
            if type(move_timeout_ms) is not int or not 1 <= move_timeout_ms <= 120_000:
                raise ValueError("Remote runner move_timeout_ms must be between 1 and 120000.")

        if self.adapter_id == "scripted":
            moves = self.settings.get("moves", [])
            if (
                not isinstance(moves, list)
                or len(moves) > 512
                or not all(
                    isinstance(move, str)
                    and re.fullmatch(r"[a-h][1-8][a-h][1-8][qrbn]?", move.lower())
                    for move in moves
                )
            ):
                raise ValueError("Scripted moves must be at most 512 UCI move strings.")
        return self

    @field_validator("protocol_version")
    @classmethod
    def validate_protocol_version(cls, value: str) -> str:
        if value != PROTOCOL_VERSION:
            raise ValueError(f"Unsupported player protocol version: {value}")
        return value

    @property
    def is_human(self) -> bool:
        return self.adapter_id == "human"

    @classmethod
    def human(cls, color: str) -> PlayerConfiguration:
        return cls(
            adapter_id="human",
            display_name="Human",
            provider="Human seat",
            model="Manual input",
            connection_mode=ConnectionMode.HUMAN,
            effort=None,
            division=AssistanceDivision.LEGAL_ASSIST,
        )

    @classmethod
    def stockfish(
        cls,
        color: str,
        *,
        target_elo: int = 1600,
        move_time_ms: int = 450,
    ) -> PlayerConfiguration:
        return cls(
            adapter_id="stockfish",
            display_name=f"Stockfish {target_elo}",
            provider="Local UCI",
            model="Stockfish",
            connection_mode=ConnectionMode.LOCAL,
            effort=EffortLevel.BALANCED,
            division=AssistanceDivision.ENGINE_ASSISTED,
            settings={
                "color": color,
                "target_elo": target_elo,
                "move_time_ms": move_time_ms,
            },
        )


class MoveRequest(BaseModel):
    schema_version: str = PROTOCOL_VERSION
    request_id: str = Field(default_factory=lambda: str(uuid4()))
    match_id: str
    position_version: int = Field(ge=0)
    color: str = Field(pattern=r"^(white|black)$")
    fen: str
    moves_uci: list[str]
    pgn: str
    legal_moves: list[str] | None = None
    remaining_ms: int = Field(ge=0)
    move_deadline_ms: int = Field(ge=1)
    division: AssistanceDivision
    public_summary_required: bool = True

    @field_validator("schema_version")
    @classmethod
    def validate_protocol_version(cls, value: str) -> str:
        if value != PROTOCOL_VERSION:
            raise ValueError(f"Unsupported player protocol version: {value}")
        return value


class MoveProposal(BaseModel):
    schema_version: str = PROTOCOL_VERSION
    request_id: str
    match_id: str
    position_version: int = Field(ge=0)
    move: str = Field(min_length=4, max_length=5)
    plan: str = Field(default="", max_length=280)
    threat: str = Field(default="", max_length=280)
    confidence: int | None = Field(default=None, ge=0, le=100)
    usage: UsageMetrics = Field(default_factory=UsageMetrics)

    @field_validator("move")
    @classmethod
    def normalize_move(cls, value: str) -> str:
        return value.strip().lower()

    @model_validator(mode="after")
    def validate_protocol_version(self) -> MoveProposal:
        if self.schema_version != PROTOCOL_VERSION:
            raise ValueError(f"Unsupported player protocol version: {self.schema_version}")
        return self


class PlayerMoveMetadata(BaseModel):
    protocol_version: str = PROTOCOL_VERSION
    player_id: str
    adapter_id: str
    provider: str
    model: str
    effort: EffortLevel | None = None
    division: AssistanceDivision
    latency_ms: int = Field(ge=0)
    plan: str = ""
    threat: str = ""
    confidence: int | None = Field(default=None, ge=0, le=100)
    usage: UsageMetrics = Field(default_factory=UsageMetrics)
    attempt: int = Field(default=1, ge=1)
