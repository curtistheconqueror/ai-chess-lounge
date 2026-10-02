from __future__ import annotations

import asyncio

import httpx
import pytest
from lounge_api.adapters import (
    AdapterRegistry,
    RetryableAdapterError,
    provider_http_error,
)
from lounge_api.manager import GameManager
from lounge_api.models import CreateGameRequest, MatchState, OpponentKind
from lounge_api.persistence import DatabaseStore
from lounge_api.player_protocol import (
    AssistanceDivision,
    ConnectionMode,
    MoveProposal,
    MoveRequest,
    PlayerConfiguration,
)
from lounge_api.provider_reliability import (
    ProviderRecoveryRequired,
    ProviderReliabilityController,
    ProviderRetryPolicy,
)


class FakeMonotonic:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class RecoveringProviderAdapter:
    adapter_id = "openai"

    def __init__(self, failures: int) -> None:
        self.failures = failures
        self.calls = 0

    def list_models(self) -> list[str]:
        return ["provider-test"]

    def capabilities(self, model: str) -> dict[str, object]:
        return {"model": model, "credentials_required": False}

    def validate_configuration(self, player: PlayerConfiguration) -> None:
        assert player.model == "provider-test"

    async def choose_move(
        self,
        request: MoveRequest,
        player: PlayerConfiguration,
    ) -> MoveProposal:
        del player
        self.calls += 1
        if self.failures:
            self.failures -= 1
            raise RetryableAdapterError("sanitized outage", category="provider_outage")
        assert request.legal_moves
        return MoveProposal(
            request_id=request.request_id,
            match_id=request.match_id,
            position_version=request.position_version,
            move=request.legal_moves[0],
        )

    def normalize_usage(self, usage: object):
        raise AssertionError(f"Unexpected usage normalization: {usage!r}")

    async def healthcheck(self) -> bool:
        return True


def provider_player() -> PlayerConfiguration:
    return PlayerConfiguration(
        adapter_id="openai",
        display_name="Recovery Test",
        provider="Test Provider",
        model="provider-test",
        connection_mode=ConnectionMode.DIRECT_API,
        division=AssistanceDivision.LEGAL_ASSIST,
    )


def reliability_controller(*, outage_threshold: int = 3) -> ProviderReliabilityController:
    return ProviderReliabilityController(
        ProviderRetryPolicy(
            max_attempts=2,
            base_delay_ms=0,
            max_delay_ms=0,
            requests_per_minute=120,
            outage_threshold=outage_threshold,
            outage_cooldown_ms=30_000,
        )
    )


def test_provider_http_failures_classify_retryable_status_and_retry_after() -> None:
    failure = provider_http_error(
        "Provider API",
        httpx.Response(429, headers={"Retry-After": "1.5"}),
    )

    assert isinstance(failure, RetryableAdapterError)
    assert failure.category == "rate_limited"
    assert failure.retry_after_ms == 1_500
    assert "Provider API returned HTTP 429" in str(failure)

    authentication = provider_http_error("Provider API", httpx.Response(401))
    assert not isinstance(authentication, RetryableAdapterError)
    assert "HTTP 401" in str(authentication)


def test_local_rate_limit_and_circuit_breaker_are_bounded() -> None:
    clock = FakeMonotonic()
    controller = ProviderReliabilityController(
        ProviderRetryPolicy(
            max_attempts=2,
            base_delay_ms=0,
            max_delay_ms=0,
            requests_per_minute=1,
            outage_threshold=2,
            outage_cooldown_ms=5_000,
        ),
        clock=clock,
    )

    controller.before_attempt("openai", "test")
    with pytest.raises(ProviderRecoveryRequired) as limited:
        controller.before_attempt("openai", "test")
    assert limited.value.reason == "provider_rate_limited"
    assert limited.value.retry_after_ms == 60_000

    clock.now = 60.1
    controller.before_attempt("openai", "test")
    assert controller.record_failure("openai", "test") is None
    assert controller.record_failure("openai", "test") == 5_000
    with pytest.raises(ProviderRecoveryRequired) as unavailable:
        controller.before_attempt("openai", "test")
    assert unavailable.value.reason == "provider_circuit_open"
    controller.allow_manual_probe("openai", "test")
    clock.now = 120.2
    controller.before_attempt("openai", "test")


def test_transient_provider_failure_retries_inside_original_turn() -> None:
    async def run() -> None:
        adapter = RecoveringProviderAdapter(failures=1)
        manager = GameManager(
            adapters=AdapterRegistry([adapter]),
            provider_reliability=reliability_controller(),
            store=DatabaseStore("sqlite+aiosqlite:///:memory:"),
            schedule_timeouts=False,
        )
        await manager.start()
        try:
            game = await manager.create(
                CreateGameRequest(
                    opponent=OpponentKind.HUMAN,
                    white_player=provider_player(),
                    black_player=PlayerConfiguration.human("black"),
                )
            )
            snapshot = await manager.wait_for_automation(game.id, timeout=2)

            assert adapter.calls == 2
            assert snapshot.lifecycle is MatchState.RUNNING
            assert len(snapshot.moves) == 1
            assert snapshot.moves[0].player_metadata is not None
            assert snapshot.moves[0].player_metadata.attempt == 2
        finally:
            await manager.close()

    asyncio.run(run())


def test_operator_retry_recovers_paused_provider_turn_and_is_audited() -> None:
    async def run() -> None:
        adapter = RecoveringProviderAdapter(failures=2)
        manager = GameManager(
            adapters=AdapterRegistry([adapter]),
            provider_reliability=reliability_controller(outage_threshold=1),
            store=DatabaseStore("sqlite+aiosqlite:///:memory:"),
            schedule_timeouts=False,
        )
        await manager.start()
        try:
            game = await manager.create(
                CreateGameRequest(
                    opponent=OpponentKind.HUMAN,
                    white_player=provider_player(),
                    black_player=PlayerConfiguration.human("black"),
                )
            )
            paused = await manager.wait_for_automation(game.id, timeout=2)
            assert paused.lifecycle is MatchState.PAUSED
            assert paused.moves == []

            requested = await manager.retry_agent_turn(game.id)
            assert requested.lifecycle is MatchState.RUNNING
            recovered = await manager.wait_for_automation(game.id, timeout=2)
            events = await manager.events(game.id)

            assert recovered.lifecycle is MatchState.RUNNING
            assert len(recovered.moves) == 1
            assert [event.type for event in events].count("agent.retry_requested") == 1
            failure = next(event for event in events if event.type == "agent.failed")
            assert failure.payload["reason"] == "provider_retry_exhausted"
            assert failure.payload["operator_action"] == "retry_agent_turn"
            assert "sanitized outage" not in str(failure.payload)
        finally:
            await manager.close()

    asyncio.run(run())
