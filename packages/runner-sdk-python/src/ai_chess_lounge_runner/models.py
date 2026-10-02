from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

PROTOCOL_VERSION = "1.0"
_UCI_MOVE = re.compile(r"^[a-h][1-8][a-h][1-8][qrbn]?$")
_DIVISIONS = {
    "pure_reasoning",
    "legal_assist",
    "tactical_metadata",
    "engine_assisted",
    "open_agentic",
    "human_ai_team",
}


class ProtocolValueError(ValueError):
    """A server or handler value does not satisfy protocol version 1.0."""


def _object(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ProtocolValueError(f"{label} must be a JSON object.")
    return value


def _string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ProtocolValueError(f"{label} must be a non-empty string.")
    return value


def _integer(value: object, label: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ProtocolValueError(f"{label} must be an integer of at least {minimum}.")
    return value


def _strings(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ProtocolValueError(f"{label} must be an array of strings.")
    return tuple(value)


def _reject_unknown(value: dict[str, Any], allowed: set[str], label: str) -> None:
    unknown = sorted(set(value).difference(allowed))
    if unknown:
        raise ProtocolValueError(f"{label} contains unsupported fields: {', '.join(unknown)}.")


@dataclass(frozen=True, slots=True)
class UsageMetrics:
    input_tokens: int | None = None
    output_tokens: int | None = None
    reasoning_tokens: int | None = None
    estimated_cost_usd: float | None = None

    def __post_init__(self) -> None:
        for name in ("input_tokens", "output_tokens", "reasoning_tokens"):
            value = getattr(self, name)
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, int) or value < 0
            ):
                raise ProtocolValueError(f"{name} must be a non-negative integer or None.")
        if self.estimated_cost_usd is not None and (
            isinstance(self.estimated_cost_usd, bool)
            or not isinstance(self.estimated_cost_usd, (int, float))
            or self.estimated_cost_usd < 0
        ):
            raise ProtocolValueError("estimated_cost_usd must be non-negative or None.")
        if self.estimated_cost_usd is not None:
            object.__setattr__(self, "estimated_cost_usd", float(self.estimated_cost_usd))

    def to_dict(self) -> dict[str, int | float | None]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "reasoning_tokens": self.reasoning_tokens,
            "estimated_cost_usd": self.estimated_cost_usd,
        }


@dataclass(frozen=True, slots=True)
class MoveRequest:
    request_id: str
    match_id: str
    position_version: int
    color: str
    fen: str
    moves_uci: tuple[str, ...]
    pgn: str
    legal_moves: tuple[str, ...] | None
    remaining_ms: int
    move_deadline_ms: int
    division: str
    public_summary_required: bool
    schema_version: str = PROTOCOL_VERSION

    @classmethod
    def from_dict(cls, raw: object) -> MoveRequest:
        value = _object(raw, "turn request")
        _reject_unknown(
            value,
            {
                "schema_version",
                "request_id",
                "match_id",
                "position_version",
                "color",
                "fen",
                "moves_uci",
                "pgn",
                "legal_moves",
                "remaining_ms",
                "move_deadline_ms",
                "division",
                "public_summary_required",
            },
            "turn request",
        )
        schema_version = _string(value.get("schema_version"), "schema_version")
        if schema_version != PROTOCOL_VERSION:
            raise ProtocolValueError(f"Unsupported protocol version: {schema_version}.")
        color = _string(value.get("color"), "color")
        if color not in {"white", "black"}:
            raise ProtocolValueError("color must be white or black.")
        division = _string(value.get("division"), "division")
        if division not in _DIVISIONS:
            raise ProtocolValueError(f"Unsupported assistance division: {division}.")
        legal_raw = value.get("legal_moves")
        legal_moves = None if legal_raw is None else _strings(legal_raw, "legal_moves")
        summary_required = value.get("public_summary_required")
        if not isinstance(summary_required, bool):
            raise ProtocolValueError("public_summary_required must be a boolean.")
        pgn = value.get("pgn")
        if not isinstance(pgn, str):
            raise ProtocolValueError("pgn must be a string.")
        return cls(
            schema_version=schema_version,
            request_id=_string(value.get("request_id"), "request_id"),
            match_id=_string(value.get("match_id"), "match_id"),
            position_version=_integer(value.get("position_version"), "position_version"),
            color=color,
            fen=_string(value.get("fen"), "fen"),
            moves_uci=_strings(value.get("moves_uci"), "moves_uci"),
            pgn=pgn,
            legal_moves=legal_moves,
            remaining_ms=_integer(value.get("remaining_ms"), "remaining_ms"),
            move_deadline_ms=_integer(value.get("move_deadline_ms"), "move_deadline_ms", minimum=1),
            division=division,
            public_summary_required=summary_required,
        )


@dataclass(frozen=True, slots=True)
class TurnDelivery:
    delivery_id: str
    expires_at: str
    request: MoveRequest

    @classmethod
    def from_dict(cls, raw: object) -> TurnDelivery:
        value = _object(raw, "turn delivery")
        _reject_unknown(value, {"delivery_id", "expires_at", "request"}, "turn delivery")
        return cls(
            delivery_id=_string(value.get("delivery_id"), "delivery_id"),
            expires_at=_string(value.get("expires_at"), "expires_at"),
            request=MoveRequest.from_dict(value.get("request")),
        )


@dataclass(frozen=True, slots=True)
class MoveProposal:
    request_id: str
    match_id: str
    position_version: int
    move: str
    plan: str = ""
    threat: str = ""
    confidence: int | None = None
    usage: UsageMetrics = field(default_factory=UsageMetrics)
    schema_version: str = PROTOCOL_VERSION

    def __post_init__(self) -> None:
        normalized = self.move.strip().lower()
        object.__setattr__(self, "move", normalized)
        if self.schema_version != PROTOCOL_VERSION:
            raise ProtocolValueError(f"Unsupported protocol version: {self.schema_version}.")
        if not self.request_id or not self.match_id:
            raise ProtocolValueError("request_id and match_id are required.")
        if self.position_version < 0:
            raise ProtocolValueError("position_version must be non-negative.")
        if not _UCI_MOVE.fullmatch(normalized):
            raise ProtocolValueError("move must be a legal-shaped UCI move string.")
        if len(self.plan) > 280 or len(self.threat) > 280:
            raise ProtocolValueError("plan and threat must be at most 280 characters.")
        if self.confidence is not None and not 0 <= self.confidence <= 100:
            raise ProtocolValueError("confidence must be between 0 and 100 or None.")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "request_id": self.request_id,
            "match_id": self.match_id,
            "position_version": self.position_version,
            "move": self.move,
            "plan": self.plan,
            "threat": self.threat,
            "confidence": self.confidence,
            "usage": self.usage.to_dict(),
        }


def proposal_for(
    delivery: TurnDelivery,
    *,
    move: str,
    plan: str = "",
    threat: str = "",
    confidence: int | None = None,
    usage: UsageMetrics | None = None,
) -> MoveProposal:
    """Create a proposal bound to the exact delivered request identity."""

    request = delivery.request
    return MoveProposal(
        request_id=request.request_id,
        match_id=request.match_id,
        position_version=request.position_version,
        move=move,
        plan=plan,
        threat=threat,
        confidence=confidence,
        usage=usage or UsageMetrics(),
    )


@dataclass(frozen=True, slots=True, repr=False)
class RunnerCredentials:
    session_id: str
    runner_token: str
    signing_key: str
    permissions: tuple[str, ...]
    expires_at: str
    player: dict[str, Any]
    websocket_path: str = "/ws/runners"
    next_turn_path: str = "/api/runner-sessions/turns/next"
    proposal_path_template: str = "/api/runner-sessions/turns/{delivery_id}/proposal"
    heartbeat_path: str = "/api/runner-sessions/heartbeat"

    def __repr__(self) -> str:
        return (
            "RunnerCredentials("
            f"session_id={self.session_id!r}, runner_token='<redacted>', "
            "signing_key='<redacted>', "
            f"permissions={self.permissions!r}, expires_at={self.expires_at!r})"
        )

    @classmethod
    def from_dict(cls, raw: object) -> RunnerCredentials:
        value = _object(raw, "runner credentials")
        permissions = _strings(value.get("permissions"), "permissions")
        player = _object(value.get("player"), "player")
        return cls(
            session_id=_string(value.get("session_id"), "session_id"),
            runner_token=_string(value.get("runner_token"), "runner_token"),
            signing_key=_string(value.get("signing_key"), "signing_key"),
            permissions=permissions,
            expires_at=_string(value.get("expires_at"), "expires_at"),
            player=dict(player),
            websocket_path=str(value.get("websocket_path", "/ws/runners")),
            next_turn_path=str(value.get("next_turn_path", "/api/runner-sessions/turns/next")),
            proposal_path_template=str(
                value.get(
                    "proposal_path_template",
                    "/api/runner-sessions/turns/{delivery_id}/proposal",
                )
            ),
            heartbeat_path=str(value.get("heartbeat_path", "/api/runner-sessions/heartbeat")),
        )


@dataclass(frozen=True, slots=True)
class ProposalReceipt:
    delivery_id: str
    accepted: bool
    duplicate: bool

    @classmethod
    def from_dict(cls, raw: object) -> ProposalReceipt:
        value = _object(raw, "proposal receipt")
        accepted = value.get("accepted")
        duplicate = value.get("duplicate")
        if not isinstance(accepted, bool) or not isinstance(duplicate, bool):
            raise ProtocolValueError("receipt accepted and duplicate values must be booleans.")
        return cls(
            delivery_id=_string(value.get("delivery_id"), "delivery_id"),
            accepted=accepted,
            duplicate=duplicate,
        )
