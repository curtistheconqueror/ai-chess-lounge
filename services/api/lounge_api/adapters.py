from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol, runtime_checkable

import chess
import httpx

from .engine import EngineFailure, StockfishService
from .player_protocol import (
    AssistanceDivision,
    ConnectionMode,
    MoveProposal,
    MoveRequest,
    PlayerConfiguration,
    UsageMetrics,
)


class AdapterError(RuntimeError):
    """A configured player adapter could not produce a move."""


class AdapterDeadlineExceeded(AdapterError):
    """The player did not answer before the authoritative move deadline."""


class AdapterConfigurationError(AdapterError):
    """A player configuration cannot be served by the selected adapter."""


class RetryableAdapterError(AdapterError):
    """An adapter failed transiently and may be retried by the runner."""

    def __init__(
        self,
        message: str,
        *,
        category: str = "transient",
        retry_after_ms: int | None = None,
    ) -> None:
        super().__init__(message)
        self.category = category
        self.retry_after_ms = retry_after_ms


RETRYABLE_PROVIDER_STATUS_CODES = frozenset({408, 409, 425, 429, 500, 502, 503, 504})


def provider_transport_error(operation: str, exc: httpx.HTTPError) -> RetryableAdapterError:
    """Build a sanitized transient error for a provider transport failure."""

    return RetryableAdapterError(
        f"{operation} request failed ({type(exc).__name__}).",
        category="transport",
    )


def provider_http_error(operation: str, response: httpx.Response) -> AdapterError:
    """Classify an HTTP failure without exposing the provider response body."""

    status_code = response.status_code
    message = f"{operation} returned HTTP {status_code}."
    if status_code not in RETRYABLE_PROVIDER_STATUS_CODES:
        return AdapterError(message)
    category = "rate_limited" if status_code == 429 else "provider_outage"
    return RetryableAdapterError(
        message,
        category=category,
        retry_after_ms=_retry_after_ms(response),
    )


def _retry_after_ms(response: httpx.Response) -> int | None:
    value = response.headers.get("Retry-After")
    if value is None:
        return None
    try:
        seconds = float(value)
    except ValueError:
        return None
    if seconds < 0:
        return None
    return min(120_000, round(seconds * 1_000))


@runtime_checkable
class PlayerAdapter(Protocol):
    adapter_id: str

    def list_models(self) -> list[str]: ...

    def capabilities(self, model: str) -> dict[str, object]: ...

    def validate_configuration(self, player: PlayerConfiguration) -> None: ...

    async def choose_move(
        self,
        request: MoveRequest,
        player: PlayerConfiguration,
    ) -> MoveProposal: ...

    def normalize_usage(self, usage: object) -> UsageMetrics: ...

    async def healthcheck(self) -> bool: ...


class AdapterRegistry:
    def __init__(self, adapters: Iterable[PlayerAdapter] = ()) -> None:
        self._adapters: dict[str, PlayerAdapter] = {}
        for adapter in adapters:
            self.register(adapter)

    def register(self, adapter: PlayerAdapter) -> None:
        if adapter.adapter_id in self._adapters:
            raise ValueError(f"Adapter {adapter.adapter_id!r} is already registered.")
        self._adapters[adapter.adapter_id] = adapter

    def get(self, adapter_id: str) -> PlayerAdapter:
        try:
            return self._adapters[adapter_id]
        except KeyError as exc:
            raise AdapterConfigurationError(
                f"Player adapter {adapter_id!r} is not installed."
            ) from exc

    def validate(self, player: PlayerConfiguration) -> None:
        if player.is_human:
            return
        self.get(player.adapter_id).validate_configuration(player)

    def catalog(self) -> list[dict[str, object]]:
        return [
            {
                "adapter_id": adapter.adapter_id,
                "models": adapter.list_models(),
                "capabilities": {
                    model: adapter.capabilities(model) for model in adapter.list_models()
                },
            }
            for adapter in self._adapters.values()
        ]


class ScriptedPlayerAdapter:
    adapter_id = "scripted"

    def list_models(self) -> list[str]:
        return ["deterministic-v1"]

    def capabilities(self, model: str) -> dict[str, object]:
        return {
            "model": model,
            "connection_mode": ConnectionMode.LOCAL.value,
            "effort_levels": [],
            "structured_output": True,
            "credentials_required": False,
        }

    def validate_configuration(self, player: PlayerConfiguration) -> None:
        if player.model != "deterministic-v1":
            raise AdapterConfigurationError("The scripted adapter supports deterministic-v1.")
        if player.division is AssistanceDivision.PURE_REASONING:
            raise AdapterConfigurationError("The scripted adapter requires legal-move assistance.")
        script = player.settings.get("moves", [])
        if not isinstance(script, list) or not all(isinstance(move, str) for move in script):
            raise AdapterConfigurationError("Scripted moves must be a list of UCI strings.")

    async def choose_move(
        self,
        request: MoveRequest,
        player: PlayerConfiguration,
    ) -> MoveProposal:
        legal_moves = request.legal_moves or []
        if not legal_moves:
            raise AdapterError("The scripted adapter requires a non-empty legal move list.")
        script = player.settings.get("moves", [])
        # The initial FEN may start with either color (experiment opening suites).
        completed = len(request.moves_uci) // 2
        move = script[completed] if completed < len(script) else sorted(legal_moves)[0]
        return MoveProposal(
            request_id=request.request_id,
            match_id=request.match_id,
            position_version=request.position_version,
            move=move,
            plan="Follow the declared deterministic test line.",
            threat="Choose the first reproducible legal continuation if the script ends.",
            confidence=100,
            usage=UsageMetrics(),
        )

    async def healthcheck(self) -> bool:
        return True

    def normalize_usage(self, usage: object) -> UsageMetrics:
        del usage
        return UsageMetrics()


class StockfishPlayerAdapter:
    adapter_id = "stockfish"

    def __init__(self, engine: StockfishService) -> None:
        self.engine = engine

    def list_models(self) -> list[str]:
        return ["Stockfish"]

    def capabilities(self, model: str) -> dict[str, object]:
        return {
            "model": model,
            "connection_mode": ConnectionMode.LOCAL.value,
            "effort_levels": ["fast", "balanced", "deep", "maximum"],
            "structured_output": True,
            "credentials_required": False,
            "available": self.engine.available,
        }

    def validate_configuration(self, player: PlayerConfiguration) -> None:
        target_elo = player.settings.get("target_elo", 1600)
        move_time_ms = player.settings.get("move_time_ms", 450)
        if not isinstance(target_elo, int) or not 800 <= target_elo <= 3200:
            raise AdapterConfigurationError("Stockfish target_elo must be between 800 and 3200.")
        if not isinstance(move_time_ms, int) or not 50 <= move_time_ms <= 10_000:
            raise AdapterConfigurationError("Stockfish move_time_ms must be between 50 and 10000.")

    async def choose_move(
        self,
        request: MoveRequest,
        player: PlayerConfiguration,
    ) -> MoveProposal:
        board = chess.Board(request.fen)
        try:
            configured_move_time = int(player.settings.get("move_time_ms", 450))
            result = await self.engine.choose_move(
                board,
                target_elo=int(player.settings.get("target_elo", 1600)),
                move_time_ms=max(1, min(configured_move_time, request.move_deadline_ms)),
                **({"full_strength": True} if player.settings.get("full_strength", False) else {}),
                **(
                    {"skill_level": player.settings["skill_level"]}
                    if "skill_level" in player.settings
                    else {}
                ),
            )
        except EngineFailure as exc:
            raise RetryableAdapterError(str(exc)) from exc
        return MoveProposal(
            request_id=request.request_id,
            match_id=request.match_id,
            position_version=request.position_version,
            move=result.uci,
            plan="Select a legal engine continuation under the disclosed strength limit.",
            threat="The opponent may challenge the engine's current principal plan.",
            confidence=None,
            usage=UsageMetrics(),
        )

    async def healthcheck(self) -> bool:
        return self.engine.available

    def normalize_usage(self, usage: object) -> UsageMetrics:
        del usage
        return UsageMetrics()
