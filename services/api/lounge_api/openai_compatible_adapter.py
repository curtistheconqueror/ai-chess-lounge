from __future__ import annotations

import math
import os
from typing import Any

import httpx
from pydantic import ValidationError

from .adapter_prompt import SYSTEM_INSTRUCTION, move_prompt
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
from .structured_move import MOVE_OUTPUT_SCHEMA, StructuredMoveOutput

OPENROUTER_API_BASE = "https://openrouter.ai/api/v1"
VLLM_API_BASE = "http://127.0.0.1:8000/v1"
DEFAULT_OPENROUTER_MODELS = (
    "openai/gpt-6.1-sol",
    "openai/gpt-6-astra",
    "anthropic/claude-opus-5.5",
    "anthropic/claude-sonnet-5.5",
    "google/gemini-3.8-flash",
)
OPENROUTER_FOUR_LEVEL_EFFORT_MAP = {
    EffortLevel.FAST: "low",
    EffortLevel.BALANCED: "medium",
    EffortLevel.DEEP: "high",
    EffortLevel.MAXIMUM: "max",
}
OPENROUTER_THREE_LEVEL_EFFORT_MAP = {
    EffortLevel.FAST: "low",
    EffortLevel.BALANCED: "medium",
    EffortLevel.DEEP: "high",
}
OPENROUTER_EFFORT_MAP_BY_MODEL = {
    **{
        model: OPENROUTER_FOUR_LEVEL_EFFORT_MAP
        for model in (
            "openai/gpt-6.1-sol",
            "openai/gpt-6-astra",
            "anthropic/claude-opus-5.5",
            "anthropic/claude-sonnet-5.5",
        )
    },
    "google/gemini-3.8-flash": OPENROUTER_THREE_LEVEL_EFFORT_MAP,
}
DEFAULT_OUTPUT_BUDGET = 4_096


def models_from_environment(name: str, defaults: tuple[str, ...] = ()) -> tuple[str, ...]:
    configured = os.getenv(name, "")
    if not configured.strip():
        return defaults
    return tuple(dict.fromkeys(item.strip() for item in configured.split(",") if item.strip()))


class OpenAICompatibleChatAdapter:
    adapter_id = ""
    provider_name = ""
    credentials_required = False
    connection_mode = ConnectionMode.LOCAL

    def __init__(
        self,
        *,
        models: tuple[str, ...],
        base_url: str,
        api_key: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._models = models
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._client = client

    @property
    def configured(self) -> bool:
        return bool(self._models) and (bool(self._api_key) or not self.credentials_required)

    def list_models(self) -> list[str]:
        return list(self._models)

    def _effort_map(self, model: str) -> dict[EffortLevel, str] | None:
        del model
        return None

    def capabilities(self, model: str) -> dict[str, object]:
        effort_map = self._effort_map(model) or {}
        selectable = self.configured and model in self._models
        if selectable:
            availability = "configured_unverified"
        elif model not in self._models:
            availability = "model_not_enabled"
        elif self.credentials_required:
            availability = "credentials_missing"
        else:
            availability = "models_missing"
        return {
            "model": model,
            "connection_mode": self.connection_mode.value,
            "effort_levels": [effort.value for effort in effort_map],
            "provider_effort_map": {
                effort.value: provider_effort for effort, provider_effort in effort_map.items()
            },
            "structured_output": True,
            "credentials_required": self.credentials_required,
            "selectable": selectable,
            "availability": availability,
        }

    def validate_configuration(self, player: PlayerConfiguration) -> None:
        if not self.configured:
            raise AdapterConfigurationError(
                f"{self.provider_name} is not configured on this Lounge server."
            )
        if player.connection_mode is not self.connection_mode:
            raise AdapterConfigurationError(
                f"{self.provider_name} players must use {self.connection_mode.value} mode."
            )
        if player.provider != self.provider_name:
            raise AdapterConfigurationError(
                f"{self.provider_name} players must disclose {self.provider_name} as provider."
            )
        if player.model not in self._models:
            raise AdapterConfigurationError(
                f"{self.provider_name} model {player.model!r} is not enabled "
                "for this Lounge server."
            )
        effort_map = self._effort_map(player.model)
        if effort_map is None and player.effort is not None:
            raise AdapterConfigurationError(
                f"{self.provider_name} model {player.model!r} has no verified "
                "Lounge effort mapping; "
                "use provider default."
            )
        if effort_map is not None and player.effort not in effort_map:
            raise AdapterConfigurationError(
                f"{self.provider_name} model {player.model!r} does not support Lounge effort "
                f"{player.effort.value if player.effort else None!r}."
            )
        if player.division not in {
            AssistanceDivision.PURE_REASONING,
            AssistanceDivision.LEGAL_ASSIST,
            AssistanceDivision.TACTICAL_METADATA,
        }:
            raise AdapterConfigurationError(
                f"{self.provider_name} players support pure_reasoning, legal_assist, "
                "or tactical_metadata divisions."
            )

    async def choose_move(
        self,
        request: MoveRequest,
        player: PlayerConfiguration,
    ) -> MoveProposal:
        self.validate_configuration(player)
        response = await self._post_chat_completion(
            self._request_payload(request, player),
            timeout_seconds=max(0.1, request.move_deadline_ms / 1_000),
        )
        body = self._response_json(response)
        output_text = self._extract_output_text(body)
        try:
            output = StructuredMoveOutput.model_validate_json(output_text)
        except ValidationError as exc:
            raise AdapterError(
                f"{self.provider_name} returned a malformed structured move."
            ) from exc
        return MoveProposal(
            request_id=request.request_id,
            match_id=request.match_id,
            position_version=request.position_version,
            move=output.move,
            plan=output.plan,
            threat=output.threat,
            confidence=output.confidence,
            usage=self.normalize_usage(body.get("usage")),
        ).with_provider_observation(body.get("model"))

    def _request_payload(
        self,
        request: MoveRequest,
        player: PlayerConfiguration,
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "model": player.model,
            "messages": [
                {"role": "system", "content": SYSTEM_INSTRUCTION},
                {"role": "user", "content": move_prompt(request)},
            ],
            "stream": False,
            "max_tokens": player.settings.get("max_output_tokens", DEFAULT_OUTPUT_BUDGET),
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "chess_move_proposal",
                    "strict": True,
                    "schema": MOVE_OUTPUT_SCHEMA,
                },
            },
        }
        effort_map = self._effort_map(player.model)
        if effort_map is not None and player.effort is not None:
            payload["reasoning"] = {
                "effort": effort_map[player.effort],
                "exclude": True,
            }
        return payload

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    async def _post_chat_completion(
        self,
        payload: dict[str, object],
        *,
        timeout_seconds: float,
    ) -> httpx.Response:
        operation = f"{self.provider_name} chat-completions API"
        try:
            if self._client is not None:
                response = await self._client.post(
                    f"{self._base_url}/chat/completions",
                    headers=self._headers(),
                    json=payload,
                    timeout=timeout_seconds,
                )
            else:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        f"{self._base_url}/chat/completions",
                        headers=self._headers(),
                        json=payload,
                        timeout=timeout_seconds,
                    )
        except httpx.HTTPError as exc:
            raise provider_transport_error(operation, exc) from exc
        if not response.is_success:
            raise provider_http_error(operation, response)
        return response

    def _response_json(self, response: httpx.Response) -> dict[str, Any]:
        try:
            body = response.json()
        except ValueError as exc:
            raise AdapterError(f"{self.provider_name} returned a non-JSON response.") from exc
        if not isinstance(body, dict):
            raise AdapterError(f"{self.provider_name} returned an invalid response envelope.")
        return body

    def _extract_output_text(self, body: dict[str, Any]) -> str:
        choices = body.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise AdapterError(f"{self.provider_name} returned no structured move output.")
        choice = choices[0]
        if choice.get("finish_reason") in {"length", "content_filter"}:
            raise AdapterError(f"{self.provider_name} returned an incomplete move response.")
        message = choice.get("message")
        if not isinstance(message, dict):
            raise AdapterError(f"{self.provider_name} returned no structured move output.")
        refusal = message.get("refusal")
        if isinstance(refusal, str) and refusal:
            raise AdapterError(f"{self.provider_name} refused to provide a chess move.")
        content = message.get("content")
        if not isinstance(content, str) or not content:
            raise AdapterError(f"{self.provider_name} returned no structured move output.")
        return content

    def normalize_usage(self, usage: object) -> UsageMetrics:
        if not isinstance(usage, dict):
            return UsageMetrics()
        completion_details = usage.get("completion_tokens_details")
        reasoning_tokens = (
            completion_details.get("reasoning_tokens")
            if isinstance(completion_details, dict)
            else None
        )
        return UsageMetrics(
            input_tokens=self._nonnegative_int(usage.get("prompt_tokens")),
            output_tokens=self._nonnegative_int(usage.get("completion_tokens")),
            reasoning_tokens=self._nonnegative_int(reasoning_tokens),
            estimated_cost_usd=None,
        )

    async def healthcheck(self) -> bool:
        if not self.configured:
            return False
        try:
            if self._client is not None:
                response = await self._client.get(
                    f"{self._base_url}/models",
                    headers=self._headers(),
                    timeout=5,
                )
            else:
                async with httpx.AsyncClient() as client:
                    response = await client.get(
                        f"{self._base_url}/models",
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


class OpenRouterChatAdapter(OpenAICompatibleChatAdapter):
    adapter_id = "openrouter"
    provider_name = "OpenRouter"
    credentials_required = True
    connection_mode = ConnectionMode.DIRECT_API

    def normalize_usage(self, usage: object) -> UsageMetrics:
        metrics = super().normalize_usage(usage)
        cost = usage.get("cost") if isinstance(usage, dict) else None
        # OpenRouter reports charged credits in USD; do not infer missing prices.
        if type(cost) in {int, float} and math.isfinite(cost) and cost >= 0:
            metrics.estimated_cost_usd = cost
        return metrics

    def __init__(
        self,
        *,
        api_key: str | None = None,
        models: tuple[str, ...] | None = None,
        base_url: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(
            api_key=api_key or os.getenv("OPENROUTER_API_KEY"),
            models=(
                models
                if models is not None
                else models_from_environment("OPENROUTER_CHESS_MODELS", DEFAULT_OPENROUTER_MODELS)
            ),
            base_url=base_url or os.getenv("OPENROUTER_API_BASE") or OPENROUTER_API_BASE,
            client=client,
        )

    def _effort_map(self, model: str) -> dict[EffortLevel, str] | None:
        return OPENROUTER_EFFORT_MAP_BY_MODEL.get(model)

    def _request_payload(
        self,
        request: MoveRequest,
        player: PlayerConfiguration,
    ) -> dict[str, object]:
        payload = super()._request_payload(request, player)
        payload["provider"] = {"require_parameters": True}
        return payload


class VLLMChatAdapter(OpenAICompatibleChatAdapter):
    adapter_id = "vllm"
    provider_name = "vLLM"
    connection_mode = ConnectionMode.LOCAL

    def __init__(
        self,
        *,
        api_key: str | None = None,
        models: tuple[str, ...] | None = None,
        base_url: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(
            api_key=api_key or os.getenv("VLLM_API_KEY"),
            models=(models if models is not None else models_from_environment("VLLM_CHESS_MODELS")),
            base_url=base_url or os.getenv("VLLM_API_BASE") or VLLM_API_BASE,
            client=client,
        )
