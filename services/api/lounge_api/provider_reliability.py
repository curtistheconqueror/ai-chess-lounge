from __future__ import annotations

import os
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass
from time import monotonic

from .adapters import AdapterError


@dataclass(frozen=True)
class ProviderRetryPolicy:
    max_attempts: int = 2
    base_delay_ms: int = 250
    max_delay_ms: int = 2_000
    requests_per_minute: int = 120
    outage_threshold: int = 3
    outage_cooldown_ms: int = 30_000

    @classmethod
    def from_environment(cls) -> ProviderRetryPolicy:
        return cls(
            max_attempts=_bounded_int("LOUNGE_PROVIDER_MAX_ATTEMPTS", 2, 1, 3),
            base_delay_ms=_bounded_int("LOUNGE_PROVIDER_RETRY_BASE_MS", 250, 0, 5_000),
            max_delay_ms=_bounded_int("LOUNGE_PROVIDER_RETRY_MAX_MS", 2_000, 0, 10_000),
            requests_per_minute=_bounded_int("LOUNGE_PROVIDER_REQUESTS_PER_MINUTE", 120, 1, 10_000),
            outage_threshold=_bounded_int("LOUNGE_PROVIDER_OUTAGE_THRESHOLD", 3, 1, 20),
            outage_cooldown_ms=_bounded_int(
                "LOUNGE_PROVIDER_OUTAGE_COOLDOWN_MS", 30_000, 1_000, 600_000
            ),
        )

    def retry_delay_ms(self, attempt: int, retry_after_ms: int | None) -> int:
        exponential = min(self.max_delay_ms, self.base_delay_ms * (2 ** (attempt - 1)))
        if retry_after_ms is None:
            return exponential
        return max(exponential, retry_after_ms)


class ProviderRecoveryRequired(AdapterError):
    """A provider turn is paused until an operator explicitly retries it."""

    def __init__(
        self,
        message: str,
        *,
        reason: str,
        category: str,
        attempts: int,
        retry_after_ms: int | None = None,
    ) -> None:
        super().__init__(message)
        self.reason = reason
        self.category = category
        self.attempts = attempts
        self.retry_after_ms = retry_after_ms


@dataclass
class _CircuitState:
    consecutive_failures: int = 0
    open_until: float = 0.0


class ProviderReliabilityController:
    """Process-local request budget and circuit breaker for provider seats."""

    def __init__(
        self,
        policy: ProviderRetryPolicy | None = None,
        *,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self.policy = policy or ProviderRetryPolicy.from_environment()
        self._clock = clock
        self._requests: defaultdict[tuple[str, str], deque[float]] = defaultdict(deque)
        self._circuits: defaultdict[tuple[str, str], _CircuitState] = defaultdict(_CircuitState)

    def before_attempt(self, adapter_id: str, model: str) -> None:
        key = (adapter_id, model)
        now = self._clock()
        circuit = self._circuits[key]
        if circuit.open_until > now:
            raise ProviderRecoveryRequired(
                "The provider circuit is temporarily open.",
                reason="provider_circuit_open",
                category="provider_outage",
                attempts=0,
                retry_after_ms=max(1, round((circuit.open_until - now) * 1_000)),
            )
        if circuit.open_until:
            circuit.open_until = 0.0

        recent = self._requests[key]
        cutoff = now - 60.0
        while recent and recent[0] <= cutoff:
            recent.popleft()
        if len(recent) >= self.policy.requests_per_minute:
            retry_after_ms = max(1, round((recent[0] + 60.0 - now) * 1_000))
            raise ProviderRecoveryRequired(
                "The Lounge provider request budget is temporarily exhausted.",
                reason="provider_rate_limited",
                category="local_rate_limit",
                attempts=0,
                retry_after_ms=retry_after_ms,
            )
        recent.append(now)

    def record_success(self, adapter_id: str, model: str) -> None:
        self._circuits[(adapter_id, model)] = _CircuitState()

    def record_failure(self, adapter_id: str, model: str) -> int | None:
        circuit = self._circuits[(adapter_id, model)]
        circuit.consecutive_failures += 1
        if circuit.consecutive_failures < self.policy.outage_threshold:
            return None
        circuit.open_until = self._clock() + self.policy.outage_cooldown_ms / 1_000
        return self.policy.outage_cooldown_ms

    def allow_manual_probe(self, adapter_id: str, model: str) -> None:
        """Permit one operator-requested probe without erasing the request budget."""

        self._circuits[(adapter_id, model)].open_until = 0.0

    def status(self, adapter_id: str, model: str) -> dict[str, object]:
        now = self._clock()
        circuit = self._circuits[(adapter_id, model)]
        retry_after_ms = (
            max(1, round((circuit.open_until - now) * 1_000)) if circuit.open_until > now else None
        )
        return {
            "state": "open" if retry_after_ms is not None else "closed",
            "consecutive_failures": circuit.consecutive_failures,
            "retry_after_ms": retry_after_ms,
        }


def _bounded_int(name: str, default: int, minimum: int, maximum: int) -> int:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    try:
        parsed = int(value)
    except ValueError:
        return default
    return max(minimum, min(maximum, parsed))
