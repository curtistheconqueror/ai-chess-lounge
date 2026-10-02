from __future__ import annotations

import os
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .adapters import AdapterConfigurationError, AdapterError
from .player_protocol import (
    AssistanceDivision,
    ConnectionMode,
    EffortLevel,
    MoveProposal,
    MoveRequest,
    PlayerConfiguration,
    UsageMetrics,
)

OPENAI_API_BASE = "https://api.openai.com/v1"
DEFAULT_OPENAI_MODELS = (
    "gpt-6-astra",
    "gpt-6-sol",
    "gpt-6-luna",
    "gpt-5.6-sol",
    "gpt-5.6-terra",
    "gpt-5.6-luna",
)
OPENAI_EFFORT_MAP = {
    EffortLevel.FAST: "low",
    EffortLevel.BALANCED: "medium",
    EffortLevel.DEEP: "high",
    EffortLevel.MAXIMUM: "max",
}
DEFAULT_OUTPUT_BUDGETS = {
    EffortLevel.FAST: 1_024,
    EffortLevel.BALANCED: 4_096,
    EffortLevel.DEEP: 8_192,
    EffortLevel.MAXIMUM: 16_384,
}

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


class _OpenAIMoveOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    move: str = Field(pattern=r"^[a-h][1-8][a-h][1-8][qrbn]?$")
    plan: str = Field(max_length=280)
    threat: str = Field(max_length=280)
    confidence: int | None = Field(ge=0, le=100)


class OpenAIResponsesAdapter:
    adapter_id = "openai"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        models: tuple[str, ...] | None = None,
        base_url: str = OPENAI_API_BASE,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key = api_key or os.getenv("OPENAI_API_KEY")
        self._models = models or self._models_from_environment()
        self._base_url = base_url.rstrip("/")
        self._client = client

    @staticmethod
    def _models_from_environment() -> tuple[str, ...]:
        configured = os.getenv("OPENAI_CHESS_MODELS", "")
        if not configured.strip():
            return DEFAULT_OPENAI_MODELS
        models = tuple(
            dict.fromkeys(item.strip() for item in configured.split(",") if item.strip())
        )
        return models or DEFAULT_OPENAI_MODELS

    @property
    def configured(self) -> bool:
        return bool(self._api_key)

    def list_models(self) -> list[str]:
        return list(self._models)

    def capabilities(self, model: str) -> dict[str, object]:
        selectable = self.configured and model in self._models
        return {
            "model": model,
            "connection_mode": ConnectionMode.DIRECT_API.value,
            "effort_levels": [effort.value for effort in EffortLevel],
            "provider_effort_map": {
                effort.value: provider_effort
                for effort, provider_effort in OPENAI_EFFORT_MAP.items()
            },
            "structured_output": True,
            "credentials_required": True,
            "selectable": selectable,
            "availability": ("configured_unverified" if selectable else "credentials_missing"),
        }

    def validate_configuration(self, player: PlayerConfiguration) -> None:
        if not self.configured:
            raise AdapterConfigurationError("OpenAI is not configured on this Lounge server.")
        if player.connection_mode is not ConnectionMode.DIRECT_API:
            raise AdapterConfigurationError("OpenAI players must use direct_api mode.")
        if player.provider != "OpenAI":
            raise AdapterConfigurationError("OpenAI players must disclose OpenAI as provider.")
        if player.model not in self._models:
            raise AdapterConfigurationError(
                f"OpenAI model {player.model!r} is not enabled for this Lounge server."
            )
        if player.effort is None:
            raise AdapterConfigurationError("OpenAI players require an effort level.")
        if player.division not in {
            AssistanceDivision.PURE_REASONING,
            AssistanceDivision.LEGAL_ASSIST,
            AssistanceDivision.TACTICAL_METADATA,
        }:
            raise AdapterConfigurationError(
                "Stage 3B OpenAI players support pure_reasoning, legal_assist, "
                "or tactical_metadata divisions."
            )

    async def choose_move(
        self,
        request: MoveRequest,
        player: PlayerConfiguration,
    ) -> MoveProposal:
        self.validate_configuration(player)
        assert player.effort is not None
        payload = self._request_payload(request, player)
        timeout_seconds = max(0.1, request.move_deadline_ms / 1_000)
        response = await self._post_response(payload, timeout_seconds=timeout_seconds)
        body = self._response_json(response)
        if body.get("status") != "completed":
            raise AdapterError("OpenAI returned an incomplete move response.")
        output_text = self._extract_output_text(body)
        try:
            output = _OpenAIMoveOutput.model_validate_json(output_text)
        except ValidationError as exc:
            raise AdapterError("OpenAI returned a malformed structured move.") from exc
        return MoveProposal(
            request_id=request.request_id,
            match_id=request.match_id,
            position_version=request.position_version,
            move=output.move,
            plan=output.plan,
            threat=output.threat,
            confidence=output.confidence,
            usage=self.normalize_usage(body.get("usage")),
        )

    def _request_payload(
        self,
        request: MoveRequest,
        player: PlayerConfiguration,
    ) -> dict[str, object]:
        assert player.effort is not None
        max_output_tokens = player.settings.get(
            "max_output_tokens",
            DEFAULT_OUTPUT_BUDGETS[player.effort],
        )
        position_lines = [
            f"You are playing {request.color}.",
            f"FEN: {request.fen}",
            f"Moves (UCI): {' '.join(request.moves_uci) or '(none)'}",
            f"PGN: {request.pgn}",
            f"Assistance division: {request.division.value}",
        ]
        if request.legal_moves is not None:
            position_lines.append(f"Legal moves (UCI): {' '.join(request.legal_moves)}")
        position_lines.append(
            "Choose exactly one legal move. Provide only a concise public plan and threat; "
            "never reveal private chain-of-thought."
        )
        return {
            "model": player.model,
            "store": False,
            "instructions": (
                "You are a chess competitor in AI Chess Lounge. Return one UCI move and "
                "brief public-facing summaries using the required structured format."
            ),
            "input": "\n".join(position_lines),
            "reasoning": {"effort": OPENAI_EFFORT_MAP[player.effort]},
            "max_output_tokens": max_output_tokens,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "chess_move_proposal",
                    "strict": True,
                    "schema": MOVE_OUTPUT_SCHEMA,
                }
            },
        }

    async def _post_response(
        self,
        payload: dict[str, object],
        *,
        timeout_seconds: float,
    ) -> httpx.Response:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        try:
            if self._client is not None:
                response = await self._client.post(
                    f"{self._base_url}/responses",
                    headers=headers,
                    json=payload,
                    timeout=timeout_seconds,
                )
            else:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        f"{self._base_url}/responses",
                        headers=headers,
                        json=payload,
                        timeout=timeout_seconds,
                    )
        except httpx.HTTPError as exc:
            raise AdapterError(
                f"OpenAI Responses API request failed ({type(exc).__name__})."
            ) from exc
        if not response.is_success:
            raise AdapterError(f"OpenAI Responses API returned HTTP {response.status_code}.")
        return response

    @staticmethod
    def _response_json(response: httpx.Response) -> dict[str, Any]:
        try:
            body = response.json()
        except ValueError as exc:
            raise AdapterError("OpenAI returned a non-JSON response.") from exc
        if not isinstance(body, dict):
            raise AdapterError("OpenAI returned an invalid response envelope.")
        return body

    @staticmethod
    def _extract_output_text(body: dict[str, Any]) -> str:
        for item in body.get("output", []):
            if not isinstance(item, dict) or item.get("type") != "message":
                continue
            for content in item.get("content", []):
                if not isinstance(content, dict):
                    continue
                if content.get("type") == "refusal":
                    raise AdapterError("OpenAI refused to provide a chess move.")
                if content.get("type") == "output_text" and isinstance(content.get("text"), str):
                    return content["text"]
        raise AdapterError("OpenAI returned no structured move output.")

    def normalize_usage(self, usage: object) -> UsageMetrics:
        if not isinstance(usage, dict):
            return UsageMetrics()
        output_details = usage.get("output_tokens_details")
        reasoning_tokens = (
            output_details.get("reasoning_tokens") if isinstance(output_details, dict) else None
        )
        return UsageMetrics(
            input_tokens=self._nonnegative_int(usage.get("input_tokens")),
            output_tokens=self._nonnegative_int(usage.get("output_tokens")),
            reasoning_tokens=self._nonnegative_int(reasoning_tokens),
            estimated_cost_usd=None,
        )

    async def healthcheck(self) -> bool:
        if not self.configured or not self._models:
            return False
        headers = {"Authorization": f"Bearer {self._api_key}"}
        try:
            if self._client is not None:
                response = await self._client.get(
                    f"{self._base_url}/models/{self._models[0]}",
                    headers=headers,
                    timeout=5,
                )
            else:
                async with httpx.AsyncClient() as client:
                    response = await client.get(
                        f"{self._base_url}/models/{self._models[0]}",
                        headers=headers,
                        timeout=5,
                    )
        except httpx.HTTPError:
            return False
        return response.is_success

    @staticmethod
    def _nonnegative_int(value: object) -> int | None:
        if type(value) is int and value >= 0:
            return value
        return None
