from __future__ import annotations

import asyncio
import json

import httpx
import pytest
from lounge_api.adapters import AdapterConfigurationError, AdapterError, AdapterRegistry
from lounge_api.anthropic_adapter import (
    ANTHROPIC_API_VERSION,
    ANTHROPIC_EFFORT_MAP,
    AnthropicMessagesAdapter,
)
from lounge_api.manager import GameManager
from lounge_api.models import CreateGameRequest, OpponentKind
from lounge_api.persistence import DatabaseStore
from lounge_api.player_protocol import (
    AssistanceDivision,
    ConnectionMode,
    EffortLevel,
    MoveRequest,
    PlayerConfiguration,
)


def anthropic_player(
    *,
    effort: EffortLevel = EffortLevel.BALANCED,
    division: AssistanceDivision = AssistanceDivision.LEGAL_ASSIST,
    **settings,
) -> PlayerConfiguration:
    return PlayerConfiguration(
        adapter_id="anthropic",
        display_name="Claude Test Player",
        provider="Anthropic",
        model="claude-test",
        connection_mode=ConnectionMode.DIRECT_API,
        effort=effort,
        division=division,
        settings=settings,
    )


def move_request(*, legal_moves: list[str] | None = None) -> MoveRequest:
    return MoveRequest(
        match_id="match-1",
        position_version=7,
        color="white",
        fen="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        moves_uci=[],
        pgn="*",
        legal_moves=legal_moves,
        remaining_ms=30_000,
        move_deadline_ms=5_000,
        division=(
            AssistanceDivision.PURE_REASONING
            if legal_moves is None
            else AssistanceDivision.LEGAL_ASSIST
        ),
    )


def completed_response(
    *,
    move: str = "e2e4",
    plan: str = "Claim central space and develop quickly.",
    confidence: int | None = 82,
) -> dict[str, object]:
    return {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": "claude-test",
        "stop_reason": "end_turn",
        "content": [
            {"type": "thinking", "thinking": ""},
            {
                "type": "text",
                "text": json.dumps(
                    {
                        "move": move,
                        "plan": plan,
                        "threat": "Black can challenge the center immediately.",
                        "confidence": confidence,
                    }
                ),
            },
        ],
        "usage": {"input_tokens": 211, "output_tokens": 97},
    }


def test_anthropic_adapter_sends_structured_adaptive_effort_request() -> None:
    async def run() -> None:
        captured: dict[str, object] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["path"] = request.url.path
            captured["api_key"] = request.headers.get("x-api-key")
            captured["api_version"] = request.headers.get("anthropic-version")
            captured["payload"] = json.loads(request.content)
            return httpx.Response(200, json=completed_response())

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            adapter = AnthropicMessagesAdapter(
                api_key="test-key",
                models=("claude-test",),
                client=client,
            )
            assert adapter.capabilities("claude-test")["selectable"] is True
            assert adapter.capabilities("claude-test")["availability"] == "configured_unverified"
            request = move_request(legal_moves=["d2d4", "e2e4"])
            proposal = await adapter.choose_move(request, anthropic_player())

        payload = captured["payload"]
        assert isinstance(payload, dict)
        assert captured["path"] == "/v1/messages"
        assert captured["api_key"] == "test-key"
        assert captured["api_version"] == ANTHROPIC_API_VERSION
        assert payload["model"] == "claude-test"
        assert payload["output_config"]["effort"] == "medium"
        assert payload["output_config"]["format"]["type"] == "json_schema"
        schema = payload["output_config"]["format"]["schema"]
        assert schema["additionalProperties"] is False
        assert schema["properties"]["move"]["pattern"]
        assert "maxLength" not in schema["properties"]["plan"]
        assert "minimum" not in schema["properties"]["confidence"]
        assert "thinking" not in payload
        assert "Legal moves (UCI): d2d4 e2e4" in payload["messages"][0]["content"]
        assert proposal.move == "e2e4"
        assert proposal.request_id == request.request_id
        assert proposal.match_id == request.match_id
        assert proposal.position_version == request.position_version
        assert proposal.usage.input_tokens == 211
        assert proposal.usage.output_tokens == 97
        assert proposal.usage.reasoning_tokens is None
        assert proposal.usage.estimated_cost_usd is None

    asyncio.run(run())


@pytest.mark.parametrize(
    ("effort", "provider_effort"),
    list(ANTHROPIC_EFFORT_MAP.items()),
)
def test_anthropic_effort_mapping_is_exact(
    effort: EffortLevel,
    provider_effort: str,
) -> None:
    adapter = AnthropicMessagesAdapter(api_key="test-key", models=("claude-test",))
    payload = adapter._request_payload(
        move_request(legal_moves=["e2e4"]),
        anthropic_player(effort=effort),
    )

    assert payload["output_config"]["effort"] == provider_effort


def test_anthropic_pure_reasoning_omits_legal_move_assistance() -> None:
    adapter = AnthropicMessagesAdapter(api_key="test-key", models=("claude-test",))
    payload = adapter._request_payload(
        move_request(legal_moves=None),
        anthropic_player(division=AssistanceDivision.PURE_REASONING),
    )
    content = payload["messages"][0]["content"]

    assert "Legal moves (UCI)" not in content
    assert "Assistance division: pure_reasoning" in content


def test_anthropic_adapter_rejects_unsafe_or_unsupported_configuration() -> None:
    unconfigured = AnthropicMessagesAdapter(api_key=None, models=("claude-test",))
    unconfigured._api_key = None
    with pytest.raises(AdapterConfigurationError, match="not configured"):
        unconfigured.validate_configuration(anthropic_player())

    configured = AnthropicMessagesAdapter(api_key="test-key", models=("another-model",))
    with pytest.raises(AdapterConfigurationError, match="not enabled"):
        configured.validate_configuration(anthropic_player())

    wrong_provider = anthropic_player().model_copy(update={"provider": "Imposter"})
    configured = AnthropicMessagesAdapter(api_key="test-key", models=("claude-test",))
    with pytest.raises(AdapterConfigurationError, match="disclose Anthropic"):
        configured.validate_configuration(wrong_provider)

    wrong_transport = anthropic_player().model_copy(
        update={"connection_mode": ConnectionMode.SUBSCRIPTION_BRIDGE}
    )
    with pytest.raises(AdapterConfigurationError, match="direct_api"):
        configured.validate_configuration(wrong_transport)


@pytest.mark.parametrize(
    ("response", "message"),
    [
        (completed_response(move="not-a-move"), "malformed structured move"),
        (completed_response(plan="x" * 281), "malformed structured move"),
        (completed_response(confidence=101), "malformed structured move"),
        (
            {
                "stop_reason": "refusal",
                "stop_details": {"reason": "sensitive provider detail"},
                "content": [],
            },
            "refused",
        ),
        (
            {"stop_reason": "max_tokens", "content": []},
            "incomplete move response",
        ),
        (
            {"stop_reason": "end_turn", "content": [{"type": "thinking"}]},
            "no structured move output",
        ),
    ],
)
def test_anthropic_adapter_rejects_non_move_responses_without_leaking_details(
    response: dict[str, object],
    message: str,
) -> None:
    async def run() -> None:
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=response)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            adapter = AnthropicMessagesAdapter(
                api_key="test-key",
                models=("claude-test",),
                client=client,
            )
            with pytest.raises(AdapterError, match=message) as captured:
                await adapter.choose_move(
                    move_request(legal_moves=["e2e4"]),
                    anthropic_player(),
                )
            assert "sensitive provider detail" not in str(captured.value)

    asyncio.run(run())


def test_anthropic_adapter_sanitizes_http_and_non_json_errors() -> None:
    async def run_error(response: httpx.Response, message: str) -> None:
        def handler(_: httpx.Request) -> httpx.Response:
            return response

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            adapter = AnthropicMessagesAdapter(
                api_key="test-key",
                models=("claude-test",),
                client=client,
            )
            with pytest.raises(AdapterError, match=message) as captured:
                await adapter.choose_move(
                    move_request(legal_moves=["e2e4"]),
                    anthropic_player(),
                )
            assert "sensitive provider detail" not in str(captured.value)

    asyncio.run(
        run_error(
            httpx.Response(
                401,
                json={"error": {"message": "sensitive provider detail"}},
            ),
            "HTTP 401",
        )
    )
    asyncio.run(run_error(httpx.Response(200, content=b"not-json"), "non-JSON"))


def test_anthropic_adapter_healthcheck_uses_the_models_endpoint() -> None:
    async def run() -> None:
        observed: dict[str, str | None] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            observed["path"] = request.url.path
            observed["api_key"] = request.headers.get("x-api-key")
            return httpx.Response(200, json={"id": "claude-test"})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            adapter = AnthropicMessagesAdapter(
                api_key="test-key",
                models=("claude-test",),
                client=client,
            )
            assert await adapter.healthcheck() is True

        assert observed == {
            "path": "/v1/models/claude-test",
            "api_key": "test-key",
        }

    asyncio.run(run())


def test_anthropic_adapter_completes_a_fenced_manager_turn() -> None:
    async def run() -> None:
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=completed_response())

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            adapter = AnthropicMessagesAdapter(
                api_key="test-key",
                models=("claude-test",),
                client=client,
            )
            manager = GameManager(
                adapters=AdapterRegistry([adapter]),
                store=DatabaseStore("sqlite+aiosqlite:///:memory:"),
                schedule_timeouts=False,
            )
            await manager.start()
            try:
                game = await manager.create(
                    CreateGameRequest(
                        opponent=OpponentKind.HUMAN,
                        white_player=anthropic_player(spectator_delay_ms=0),
                        black_player=PlayerConfiguration.human("black"),
                    )
                )
                snapshot = await manager.wait_for_automation(game.id, timeout=2)

                assert [move.uci for move in snapshot.moves] == ["e2e4"]
                metadata = snapshot.moves[0].player_metadata
                assert metadata is not None
                assert metadata.adapter_id == "anthropic"
                assert metadata.provider == "Anthropic"
                assert metadata.model == "claude-test"
                assert metadata.effort is EffortLevel.BALANCED
                assert metadata.usage.input_tokens == 211
                assert metadata.usage.reasoning_tokens is None
            finally:
                await manager.close()

    asyncio.run(run())


def test_anthropic_provider_failure_pauses_without_paid_retry_loop() -> None:
    async def run() -> None:
        calls = 0

        def handler(_: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(
                429,
                json={"error": {"message": "sensitive rate limit detail"}},
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            adapter = AnthropicMessagesAdapter(
                api_key="test-key",
                models=("claude-test",),
                client=client,
            )
            manager = GameManager(
                adapters=AdapterRegistry([adapter]),
                store=DatabaseStore("sqlite+aiosqlite:///:memory:"),
                schedule_timeouts=False,
            )
            await manager.start()
            try:
                game = await manager.create(
                    CreateGameRequest(
                        opponent=OpponentKind.HUMAN,
                        white_player=anthropic_player(spectator_delay_ms=0),
                        black_player=PlayerConfiguration.human("black"),
                    )
                )
                snapshot = await manager.wait_for_automation(game.id, timeout=2)
                await asyncio.sleep(0.6)
                events = await manager.events(game.id)

                assert calls == 1
                assert snapshot.lifecycle.value == "paused"
                assert snapshot.moves == []
                assert events[-2].type == "agent.failed"
                assert events[-2].payload["reason"] == "adapter_error"
                assert "sensitive rate limit detail" not in str(events[-2].payload)
            finally:
                await manager.close()

    asyncio.run(run())
