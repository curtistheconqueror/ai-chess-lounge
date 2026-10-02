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
from .structured_move import GEMINI_MOVE_OUTPUT_SCHEMA, StructuredMoveOutput

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_GEMINI_MODELS = (
    "gemini-3.8-flash",
    "gemini-3.5-flash",
    "gemini-3.1-flash-lite",
)
GEMINI_THREE_LEVEL_EFFORT_MAP = {
    EffortLevel.FAST: "low",
    EffortLevel.BALANCED: "medium",
    EffortLevel.DEEP: "high",
}
GEMINI_FOUR_LEVEL_EFFORT_MAP = {
    EffortLevel.FAST: "minimal",
    EffortLevel.BALANCED: "low",
    EffortLevel.DEEP: "medium",
    EffortLevel.MAXIMUM: "high",
}
GEMINI_MINIMAL_THINKING_MODELS = frozenset(
    {
        "gemini-3.5-flash",
        "gemini-3.1-flash-lite",
    }
)
GEMINI_EFFORT_MAP_BY_MODEL = {
    "gemini-3.8-flash": GEMINI_THREE_LEVEL_EFFORT_MAP,
    **{model: GEMINI_FOUR_LEVEL_EFFORT_MAP for model in GEMINI_MINIMAL_THINKING_MODELS},
}
DEFAULT_OUTPUT_BUDGETS = {
    EffortLevel.FAST: 2_048,
    EffortLevel.BALANCED: 4_096,
    EffortLevel.DEEP: 8_192,
    EffortLevel.MAXIMUM: 16_384,
}


class GeminiInteractionsAdapter:
    adapter_id = "google"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        models: tuple[str, ...] | None = None,
        base_url: str = GEMINI_API_BASE,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key = api_key or os.getenv("GEMINI_API_KEY")
        self._models = models or self._models_from_environment()
        self._base_url = base_url.rstrip("/")
        self._client = client

    @staticmethod
    def _models_from_environment() -> tuple[str, ...]:
        configured = os.getenv("GEMINI_CHESS_MODELS", "")
        if not configured.strip():
            return DEFAULT_GEMINI_MODELS
        models = tuple(
            dict.fromkeys(item.strip() for item in configured.split(",") if item.strip())
        )
        return models or DEFAULT_GEMINI_MODELS

    @property
    def configured(self) -> bool:
        return bool(self._api_key)

    def list_models(self) -> list[str]:
        return list(self._models)

    def capabilities(self, model: str) -> dict[str, object]:
        effort_map = self._effort_map(model)
        selectable = self.configured and model in self._models and effort_map is not None
        return {
            "model": model,
            "connection_mode": ConnectionMode.DIRECT_API.value,
            "effort_levels": [effort.value for effort in effort_map or {}],
            "provider_effort_map": {
                effort.value: provider_effort
                for effort, provider_effort in (effort_map or {}).items()
            },
            "thinking_mode": "level",
            "structured_output": True,
            "credentials_required": True,
            "selectable": selectable,
            "availability": (
                "configured_unverified"
                if selectable
                else "unsupported_capabilities"
                if model in self._models and effort_map is None
                else "credentials_missing"
            ),
        }

    def validate_configuration(self, player: PlayerConfiguration) -> None:
        if not self.configured:
            raise AdapterConfigurationError(
                "Google Gemini is not configured on this Lounge server."
            )
        if player.connection_mode is not ConnectionMode.DIRECT_API:
            raise AdapterConfigurationError("Google Gemini players must use direct_api mode.")
        if player.provider != "Google":
            raise AdapterConfigurationError(
                "Google Gemini players must disclose Google as provider."
            )
        if player.model not in self._models:
            raise AdapterConfigurationError(
                f"Gemini model {player.model!r} is not enabled for this Lounge server."
            )
        effort_map = self._effort_map(player.model)
        if effort_map is None:
            raise AdapterConfigurationError(
                f"Gemini model {player.model!r} does not have a verified Lounge "
                "thinking-level mapping."
            )
        if player.effort is None:
            raise AdapterConfigurationError("Google Gemini players require an effort level.")
        if player.effort not in effort_map:
            raise AdapterConfigurationError(
                f"Gemini model {player.model!r} does not support Lounge effort "
                f"{player.effort.value!r}."
            )
        if player.division not in {
            AssistanceDivision.PURE_REASONING,
            AssistanceDivision.LEGAL_ASSIST,
            AssistanceDivision.TACTICAL_METADATA,
        }:
            raise AdapterConfigurationError(
                "Stage 3D Google Gemini players support pure_reasoning, legal_assist, "
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
        response = await self._post_interaction(payload, timeout_seconds=timeout_seconds)
        body = self._response_json(response)
        status = body.get("status")
        if status != "completed":
            if status in {"failed", "cancelled"}:
                raise AdapterError("Google Gemini failed to provide a chess move.")
            raise AdapterError("Google Gemini returned an incomplete move response.")
        output_text = self._extract_output_text(body)
        try:
            output = StructuredMoveOutput.model_validate_json(output_text)
        except ValidationError as exc:
            raise AdapterError("Google Gemini returned a malformed structured move.") from exc
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
        effort_map = self._effort_map(player.model)
        assert effort_map is not None
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
            "system_instruction": (
                "You are a chess competitor in AI Chess Lounge. Return one UCI move and "
                "brief public-facing summaries using the required structured format."
            ),
            "input": "\n".join(position_lines),
            "generation_config": {
                "thinking_level": effort_map[player.effort],
                "thinking_summaries": "none",
                "max_output_tokens": max_output_tokens,
            },
            "response_format": {
                "type": "text",
                "mime_type": "application/json",
                "schema": GEMINI_MOVE_OUTPUT_SCHEMA,
            },
        }

    async def _post_interaction(
        self,
        payload: dict[str, object],
        *,
        timeout_seconds: float,
    ) -> httpx.Response:
        headers = self._headers()
        try:
            if self._client is not None:
                response = await self._client.post(
                    f"{self._base_url}/interactions",
                    headers=headers,
                    json=payload,
                    timeout=timeout_seconds,
                )
            else:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        f"{self._base_url}/interactions",
                        headers=headers,
                        json=payload,
                        timeout=timeout_seconds,
                    )
        except httpx.HTTPError as exc:
            raise provider_transport_error("Google Gemini Interactions API", exc) from exc
        if not response.is_success:
            raise provider_http_error("Google Gemini Interactions API", response)
        return response

    def _headers(self) -> dict[str, str]:
        return {
            "x-goog-api-key": str(self._api_key),
            "content-type": "application/json",
        }

    @staticmethod
    def _response_json(response: httpx.Response) -> dict[str, Any]:
        try:
            body = response.json()
        except ValueError as exc:
            raise AdapterError("Google Gemini returned a non-JSON response.") from exc
        if not isinstance(body, dict):
            raise AdapterError("Google Gemini returned an invalid response envelope.")
        return body

    @staticmethod
    def _extract_output_text(body: dict[str, Any]) -> str:
        steps = body.get("steps", [])
        if isinstance(steps, list):
            for step in reversed(steps):
                if not isinstance(step, dict) or step.get("type") != "model_output":
                    continue
                content = step.get("content", [])
                if not isinstance(content, list):
                    continue
                for item in content:
                    if (
                        isinstance(item, dict)
                        and item.get("type") == "text"
                        and isinstance(item.get("text"), str)
                    ):
                        return item["text"]
        raise AdapterError("Google Gemini returned no structured move output.")

    def normalize_usage(self, usage: object) -> UsageMetrics:
        if not isinstance(usage, dict):
            return UsageMetrics()
        return UsageMetrics(
            input_tokens=self._nonnegative_int(usage.get("total_input_tokens")),
            output_tokens=self._nonnegative_int(usage.get("total_output_tokens")),
            reasoning_tokens=self._nonnegative_int(usage.get("total_thought_tokens")),
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
    def _effort_map(model: str) -> dict[EffortLevel, str] | None:
        return GEMINI_EFFORT_MAP_BY_MODEL.get(model)

    @staticmethod
    def _nonnegative_int(value: object) -> int | None:
        if type(value) is int and value >= 0:
            return value
        return None
