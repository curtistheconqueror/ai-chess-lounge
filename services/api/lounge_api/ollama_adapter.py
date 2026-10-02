from __future__ import annotations

import os
from typing import Any

import httpx
from pydantic import ValidationError

from .adapter_prompt import SYSTEM_INSTRUCTION, move_prompt
from .adapters import AdapterConfigurationError, AdapterError
from .openai_compatible_adapter import DEFAULT_OUTPUT_BUDGET, models_from_environment
from .player_protocol import (
    AssistanceDivision,
    ConnectionMode,
    MoveProposal,
    MoveRequest,
    PlayerConfiguration,
    UsageMetrics,
)
from .structured_move import MOVE_OUTPUT_SCHEMA, StructuredMoveOutput

OLLAMA_API_BASE = "http://127.0.0.1:11434"


class OllamaChatAdapter:
    adapter_id = "ollama"

    def __init__(
        self,
        *,
        models: tuple[str, ...] | None = None,
        base_url: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._models = (
            models if models is not None else models_from_environment("OLLAMA_CHESS_MODELS")
        )
        self._base_url = (base_url or os.getenv("OLLAMA_API_BASE") or OLLAMA_API_BASE).rstrip("/")
        self._client = client

    @property
    def configured(self) -> bool:
        return bool(self._models)

    def list_models(self) -> list[str]:
        return list(self._models)

    def capabilities(self, model: str) -> dict[str, object]:
        selectable = self.configured and model in self._models
        return {
            "model": model,
            "connection_mode": ConnectionMode.LOCAL.value,
            "effort_levels": [],
            "provider_effort_map": {},
            "structured_output": True,
            "credentials_required": False,
            "selectable": selectable,
            "availability": "configured_unverified" if selectable else "model_not_enabled",
        }

    def validate_configuration(self, player: PlayerConfiguration) -> None:
        if not self.configured:
            raise AdapterConfigurationError(
                "Ollama is not configured with any models on this Lounge server."
            )
        if player.connection_mode is not ConnectionMode.LOCAL:
            raise AdapterConfigurationError("Ollama players must use local mode.")
        if player.provider != "Ollama":
            raise AdapterConfigurationError("Ollama players must disclose Ollama as provider.")
        if player.model not in self._models:
            raise AdapterConfigurationError(
                f"Ollama model {player.model!r} is not enabled for this Lounge server."
            )
        if player.effort is not None:
            raise AdapterConfigurationError(
                "Ollama models currently use provider-default effort in the Lounge."
            )
        if player.division not in {
            AssistanceDivision.PURE_REASONING,
            AssistanceDivision.LEGAL_ASSIST,
            AssistanceDivision.TACTICAL_METADATA,
        }:
            raise AdapterConfigurationError(
                "Ollama players support pure_reasoning, legal_assist, "
                "or tactical_metadata divisions."
            )

    async def choose_move(
        self,
        request: MoveRequest,
        player: PlayerConfiguration,
    ) -> MoveProposal:
        self.validate_configuration(player)
        response = await self._post_chat(
            self._request_payload(request, player),
            timeout_seconds=max(0.1, request.move_deadline_ms / 1_000),
        )
        body = self._response_json(response)
        if body.get("done") is not True:
            raise AdapterError("Ollama returned an incomplete move response.")
        message = body.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str) or not content:
            raise AdapterError("Ollama returned no structured move output.")
        try:
            output = StructuredMoveOutput.model_validate_json(content)
        except ValidationError as exc:
            raise AdapterError("Ollama returned a malformed structured move.") from exc
        return MoveProposal(
            request_id=request.request_id,
            match_id=request.match_id,
            position_version=request.position_version,
            move=output.move,
            plan=output.plan,
            threat=output.threat,
            confidence=output.confidence,
            usage=self.normalize_usage(body),
        )

    @staticmethod
    def _request_payload(
        request: MoveRequest,
        player: PlayerConfiguration,
    ) -> dict[str, object]:
        return {
            "model": player.model,
            "messages": [
                {"role": "system", "content": SYSTEM_INSTRUCTION},
                {"role": "user", "content": move_prompt(request)},
            ],
            "stream": False,
            "format": MOVE_OUTPUT_SCHEMA,
            "options": {
                "num_predict": player.settings.get("max_output_tokens", DEFAULT_OUTPUT_BUDGET)
            },
        }

    async def _post_chat(
        self,
        payload: dict[str, object],
        *,
        timeout_seconds: float,
    ) -> httpx.Response:
        try:
            if self._client is not None:
                response = await self._client.post(
                    f"{self._base_url}/api/chat",
                    json=payload,
                    timeout=timeout_seconds,
                )
            else:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        f"{self._base_url}/api/chat",
                        json=payload,
                        timeout=timeout_seconds,
                    )
        except httpx.HTTPError as exc:
            raise AdapterError(f"Ollama chat request failed ({type(exc).__name__}).") from exc
        if not response.is_success:
            raise AdapterError(f"Ollama chat API returned HTTP {response.status_code}.")
        return response

    @staticmethod
    def _response_json(response: httpx.Response) -> dict[str, Any]:
        try:
            body = response.json()
        except ValueError as exc:
            raise AdapterError("Ollama returned a non-JSON response.") from exc
        if not isinstance(body, dict):
            raise AdapterError("Ollama returned an invalid response envelope.")
        return body

    def normalize_usage(self, usage: object) -> UsageMetrics:
        if not isinstance(usage, dict):
            return UsageMetrics()
        return UsageMetrics(
            input_tokens=self._nonnegative_int(usage.get("prompt_eval_count")),
            output_tokens=self._nonnegative_int(usage.get("eval_count")),
            reasoning_tokens=None,
            estimated_cost_usd=None,
        )

    async def healthcheck(self) -> bool:
        if not self.configured:
            return False
        try:
            if self._client is not None:
                response = await self._client.get(f"{self._base_url}/api/tags", timeout=5)
            else:
                async with httpx.AsyncClient() as client:
                    response = await client.get(f"{self._base_url}/api/tags", timeout=5)
        except httpx.HTTPError:
            return False
        return response.is_success

    @staticmethod
    def _nonnegative_int(value: object) -> int | None:
        if type(value) is int and value >= 0:
            return value
        return None
