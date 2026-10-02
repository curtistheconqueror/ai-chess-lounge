from __future__ import annotations

import os
from typing import Any

import httpx
from pydantic import ValidationError

from .adapters import (
    AdapterConfigurationError,
    AdapterError,
    provider_http_error,
    provider_transport_error,
)
from .player_protocol import (
    AssistanceDivision,
    ConnectionMode,
    EffortLevel,
    MoveProposal,
    MoveRequest,
    PlayerConfiguration,
    UsageMetrics,
)
from .structured_move import ANTHROPIC_MOVE_OUTPUT_SCHEMA, StructuredMoveOutput

ANTHROPIC_API_BASE = "https://api.anthropic.com/v1"
ANTHROPIC_API_VERSION = "2023-06-01"
DEFAULT_ANTHROPIC_MODELS = (
    "claude-fable-5-1",
    "claude-opus-5-5",
    "claude-sonnet-5-5",
)
ANTHROPIC_EFFORT_MAP = {
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


class AnthropicMessagesAdapter:
    adapter_id = "anthropic"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        models: tuple[str, ...] | None = None,
        base_url: str = ANTHROPIC_API_BASE,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self._models = models or self._models_from_environment()
        self._base_url = base_url.rstrip("/")
        self._client = client

    @staticmethod
    def _models_from_environment() -> tuple[str, ...]:
        configured = os.getenv("ANTHROPIC_CHESS_MODELS", "")
        if not configured.strip():
            return DEFAULT_ANTHROPIC_MODELS
        models = tuple(
            dict.fromkeys(item.strip() for item in configured.split(",") if item.strip())
        )
        return models or DEFAULT_ANTHROPIC_MODELS

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
                for effort, provider_effort in ANTHROPIC_EFFORT_MAP.items()
            },
            "thinking_mode": "adaptive",
            "structured_output": True,
            "credentials_required": True,
            "selectable": selectable,
            "availability": "configured_unverified" if selectable else "credentials_missing",
        }

    def validate_configuration(self, player: PlayerConfiguration) -> None:
        if not self.configured:
            raise AdapterConfigurationError("Anthropic is not configured on this Lounge server.")
        if player.connection_mode is not ConnectionMode.DIRECT_API:
            raise AdapterConfigurationError("Anthropic players must use direct_api mode.")
        if player.provider != "Anthropic":
            raise AdapterConfigurationError(
                "Anthropic players must disclose Anthropic as provider."
            )
        if player.model not in self._models:
            raise AdapterConfigurationError(
                f"Anthropic model {player.model!r} is not enabled for this Lounge server."
            )
        if player.effort is None:
            raise AdapterConfigurationError("Anthropic players require an effort level.")
        if player.division not in {
            AssistanceDivision.PURE_REASONING,
            AssistanceDivision.LEGAL_ASSIST,
            AssistanceDivision.TACTICAL_METADATA,
        }:
            raise AdapterConfigurationError(
                "Stage 3C Anthropic players support pure_reasoning, legal_assist, "
                "or tactical_metadata divisions."
            )

    async def choose_move(
        self,
        request: MoveRequest,
        player: PlayerConfiguration,
    ) -> MoveProposal:
        self.validate_configuration(player)
        payload = self._request_payload(request, player)
        timeout_seconds = max(0.1, request.move_deadline_ms / 1_000)
        response = await self._post_message(payload, timeout_seconds=timeout_seconds)
        body = self._response_json(response)
        if body.get("stop_reason") == "refusal":
            raise AdapterError("Anthropic refused to provide a chess move.")
        if body.get("stop_reason") != "end_turn":
            raise AdapterError("Anthropic returned an incomplete move response.")
        output_text = self._extract_output_text(body)
        try:
            output = StructuredMoveOutput.model_validate_json(output_text)
        except ValidationError as exc:
            raise AdapterError("Anthropic returned a malformed structured move.") from exc
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
            "max_tokens": max_output_tokens,
            "system": (
                "You are a chess competitor in AI Chess Lounge. Return one UCI move and "
                "brief public-facing summaries using the required structured format."
            ),
            "messages": [{"role": "user", "content": "\n".join(position_lines)}],
            "output_config": {
                "effort": ANTHROPIC_EFFORT_MAP[player.effort],
                "format": {
                    "type": "json_schema",
                    "schema": ANTHROPIC_MOVE_OUTPUT_SCHEMA,
                },
            },
        }

    async def _post_message(
        self,
        payload: dict[str, object],
        *,
        timeout_seconds: float,
    ) -> httpx.Response:
        headers = self._headers()
        try:
            if self._client is not None:
                response = await self._client.post(
                    f"{self._base_url}/messages",
                    headers=headers,
                    json=payload,
                    timeout=timeout_seconds,
                )
            else:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        f"{self._base_url}/messages",
                        headers=headers,
                        json=payload,
                        timeout=timeout_seconds,
                    )
        except httpx.HTTPError as exc:
            raise provider_transport_error("Anthropic Messages API", exc) from exc
        if not response.is_success:
            raise provider_http_error("Anthropic Messages API", response)
        return response

    def _headers(self) -> dict[str, str]:
        return {
            "x-api-key": str(self._api_key),
            "anthropic-version": ANTHROPIC_API_VERSION,
            "content-type": "application/json",
        }

    @staticmethod
    def _response_json(response: httpx.Response) -> dict[str, Any]:
        try:
            body = response.json()
        except ValueError as exc:
            raise AdapterError("Anthropic returned a non-JSON response.") from exc
        if not isinstance(body, dict):
            raise AdapterError("Anthropic returned an invalid response envelope.")
        return body

    @staticmethod
    def _extract_output_text(body: dict[str, Any]) -> str:
        for content in body.get("content", []):
            if (
                isinstance(content, dict)
                and content.get("type") == "text"
                and isinstance(content.get("text"), str)
            ):
                return content["text"]
        raise AdapterError("Anthropic returned no structured move output.")

    def normalize_usage(self, usage: object) -> UsageMetrics:
        if not isinstance(usage, dict):
            return UsageMetrics()
        return UsageMetrics(
            input_tokens=self._nonnegative_int(usage.get("input_tokens")),
            output_tokens=self._nonnegative_int(usage.get("output_tokens")),
            reasoning_tokens=None,
            estimated_cost_usd=None,
        )

    async def healthcheck(self) -> bool:
        if not self.configured or not self._models:
            return False
        try:
            if self._client is not None:
                response = await self._client.get(
                    f"{self._base_url}/models/{self._models[0]}",
                    headers=self._headers(),
                    timeout=5,
                )
            else:
                async with httpx.AsyncClient() as client:
                    response = await client.get(
                        f"{self._base_url}/models/{self._models[0]}",
                        headers=self._headers(),
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
