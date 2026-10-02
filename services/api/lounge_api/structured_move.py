from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

MOVE_OUTPUT_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "move": {
            "type": "string",
            "pattern": "^[a-h][1-8][a-h][1-8][qrbn]?$",
        },
        "plan": {"type": "string", "maxLength": 280},
        "threat": {"type": "string", "maxLength": 280},
        "confidence": {"type": ["integer", "null"], "minimum": 0, "maximum": 100},
    },
    "required": ["move", "plan", "threat", "confidence"],
    "additionalProperties": False,
}

# Anthropic's raw structured-output transport accepts the move regex but not numeric
# or string-length constraints. The complete constraints remain enforced below after
# the response returns to the Lounge.
ANTHROPIC_MOVE_OUTPUT_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "move": {
            "type": "string",
            "pattern": "^[a-h][1-8][a-h][1-8][qrbn]?$",
        },
        "plan": {
            "type": "string",
            "description": "A concise public plan of no more than 280 characters.",
        },
        "threat": {
            "type": "string",
            "description": "A concise public threat of no more than 280 characters.",
        },
        "confidence": {
            "type": ["integer", "null"],
            "description": "An integer from 0 through 100, or null.",
        },
    },
    "required": ["move", "plan", "threat", "confidence"],
    "additionalProperties": False,
}


class StructuredMoveOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    move: str = Field(pattern=r"^[a-h][1-8][a-h][1-8][qrbn]?$")
    plan: str = Field(max_length=280)
    threat: str = Field(max_length=280)
    confidence: int | None = Field(ge=0, le=100)
