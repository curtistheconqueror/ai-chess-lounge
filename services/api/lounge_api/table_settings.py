"""Shared next-match settings for the one Lounge table.

The document is stored once on the server so every trusted device (desktop, iPad)
sees the same defaults for the next match. Saves are optimistic: a client must
present the revision it last read, and a stale revision is rejected untouched.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# These mirror the web client's SeatChoice and timeControls keys (apps/web/src/App.tsx).
SeatChoiceName = Literal[
    "human",
    "stockfish",
    "scripted",
    "remote_runner",
    "openai",
    "anthropic",
    "google",
    "openrouter",
    "ollama",
    "vllm",
]
TimeControlName = Literal["1+0", "3+2", "5+2", "10+5"]

# Same bounds as CreateGameRequest; the live engine may narrow them further, and the
# match-creation path remains the authority that enforces the engine's real caps.
MIN_ELO = 800
MAX_ELO = 3200
MIN_SKILL = 0
MAX_SKILL = 20

# A never-saved document reports a fixed timestamp so repeated reads are stable.
UNSAVED_UPDATED_AT = datetime(1970, 1, 1, tzinfo=UTC)


class StockfishSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["elo", "skill", "full"]
    elo: int | None = Field(default=None, strict=True, ge=MIN_ELO, le=MAX_ELO)
    skill_level: int | None = Field(default=None, strict=True, ge=MIN_SKILL, le=MAX_SKILL)

    @model_validator(mode="after")
    def mode_matches_fields(self) -> StockfishSettings:
        if self.mode == "elo":
            if self.elo is None or self.skill_level is not None:
                raise ValueError("Elo mode requires elo and no skill_level.")
        elif self.mode == "skill":
            if self.skill_level is None or self.elo is not None:
                raise ValueError("Skill mode requires skill_level and no elo.")
        elif self.elo is not None or self.skill_level is not None:
            raise ValueError("Full-strength mode takes neither elo nor skill_level.")
        return self


class TableSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    white_seat: SeatChoiceName
    black_seat: SeatChoiceName
    stockfish: StockfishSettings
    time_control: TimeControlName
    start_paused: bool = Field(strict=True)

    @classmethod
    def defaults(cls) -> TableSettings:
        return cls(
            white_seat="human",
            black_seat="stockfish",
            stockfish=StockfishSettings(mode="elo", elo=1600, skill_level=None),
            time_control="5+2",
            start_paused=False,
        )


class TableSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    revision: int = Field(strict=True, ge=0)
    settings: TableSettings


class TableSettingsResponse(BaseModel):
    revision: int
    updated_at: datetime
    settings: TableSettings


class TableSettingsConflict(RuntimeError):
    """Raised when the presented revision is no longer the stored revision."""
