from __future__ import annotations

import asyncio
import json

import httpx
import pytest
from lounge_api.adapters import AdapterConfigurationError, AdapterError, AdapterRegistry
from lounge_api.gemini_adapter import (
    GEMINI_FOUR_LEVEL_EFFORT_MAP,
    GEMINI_THREE_LEVEL_EFFORT_MAP,
    GeminiInteractionsAdapter,
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


def gemini_player(
    *,
    model: str = "gemini-3.8-flash",
    effort: EffortLevel = EffortLevel.BALANCED,
    division: AssistanceDivision = AssistanceDivision.LEGAL_ASSIST,
    **settings,
) -> PlayerConfiguration:
    return PlayerConfiguration(
        adapter_id="google",
        display_name="Gemini Test Player",
        provider="Google",
        model=model,
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
        "id": "interaction-test",
        "status": "completed",
        "steps": [
            {
                "type": "model_output",
                "content": [
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
                    }
                ],
            }
        ],
        "usage": {
            "total_input_tokens": 211,
            "total_output_tokens": 97,
            "total_thought_tokens": 43,
        },
    }


def test_gemini_adapter_sends_non_stored_structured_interaction() -> None:
    async def run() -> None:
        captured: dict[str, object] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["path"] = request.url.path
            captured["api_key"] = request.headers.get("x-goog-api-key")
            captured["payload"] = json.loads(request.content)
            return httpx.Response(200, json=completed_response())

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            adapter = GeminiInteractionsAdapter(
                api_key="test-key",
                models=("gemini-3.8-flash",),
                client=client,
            )
            capabilities = adapter.capabilities("gemini-3.8-flash")
            assert capabilities["selectable"] is True
            assert capabilities["availability"] == "configured_unverified"
            assert capabilities["effort_levels"] == ["fast", "balanced", "deep"]
            request = move_request(legal_moves=["d2d4", "e2e4"])
            proposal = await adapter.choose_move(request, gemini_player())

        payload = captured["payload"]
        assert isinstance(payload, dict)
        assert captured["path"] == "/v1beta/interactions"
        assert captured["api_key"] == "test-key"
        assert payload["model"] == "gemini-3.8-flash"
        assert payload["store"] is False
        generation_config = payload["generation_config"]
        assert generation_config["thinking_level"] == "medium"
        assert generation_config["thinking_summaries"] == "none"
        response_format = payload["response_format"]
        assert response_format["mime_type"] == "application/json"
        schema = response_format["schema"]
        assert schema["additionalProperties"] is False
        assert "pattern" not in schema["properties"]["move"]
        assert "maxLength" not in schema["properties"]["plan"]
        assert schema["properties"]["confidence"]["minimum"] == 0
        assert schema["properties"]["confidence"]["maximum"] == 100
        assert "Legal moves (UCI): d2d4 e2e4" in payload["input"]
        assert proposal.move == "e2e4"
        assert proposal.request_id == request.request_id
        assert proposal.match_id == request.match_id
        assert proposal.position_version == request.position_version
        assert proposal.usage.input_tokens == 211
        assert proposal.usage.output_tokens == 97
        assert proposal.usage.reasoning_tokens == 43
        assert proposal.usage.estimated_cost_usd is None

    asyncio.run(run())


@pytest.mark.parametrize(
    ("model", "effort_map"),
    [
        ("gemini-3.8-flash", GEMINI_THREE_LEVEL_EFFORT_MAP),
        ("gemini-3.5-flash", GEMINI_FOUR_LEVEL_EFFORT_MAP),
        ("gemini-3.1-flash-lite", GEMINI_FOUR_LEVEL_EFFORT_MAP),
    ],
)
def test_gemini_effort_mapping_is_model_specific(
    model: str,
    effort_map: dict[EffortLevel, str],
) -> None:
    adapter = GeminiInteractionsAdapter(api_key="test-key", models=(model,))
    assert adapter.capabilities(model)["provider_effort_map"] == {
        effort.value: provider_effort for effort, provider_effort in effort_map.items()
    }
    for effort, provider_effort in effort_map.items():
        payload = adapter._request_payload(
            move_request(legal_moves=["e2e4"]),
            gemini_player(model=model, effort=effort),
        )
        assert payload["generation_config"]["thinking_level"] == provider_effort


def test_gemini_pure_reasoning_omits_legal_move_assistance() -> None:
    adapter = GeminiInteractionsAdapter(
        api_key="test-key",
        models=("gemini-3.8-flash",),
    )
    payload = adapter._request_payload(
        move_request(legal_moves=None),
        gemini_player(division=AssistanceDivision.PURE_REASONING),
    )

    assert "Legal moves (UCI)" not in payload["input"]
    assert "Assistance division: pure_reasoning" in payload["input"]


def test_gemini_adapter_rejects_unsafe_or_unsupported_configuration() -> None:
    unconfigured = GeminiInteractionsAdapter(api_key=None, models=("gemini-3.8-flash",))
    unconfigured._api_key = None
    with pytest.raises(AdapterConfigurationError, match="not configured"):
        unconfigured.validate_configuration(gemini_player())

    configured = GeminiInteractionsAdapter(api_key="test-key", models=("another-model",))
    with pytest.raises(AdapterConfigurationError, match="not enabled"):
        configured.validate_configuration(gemini_player())

    configured = GeminiInteractionsAdapter(
        api_key="test-key",
        models=("gemini-3.8-flash",),
    )
    with pytest.raises(AdapterConfigurationError, match="does not support"):
        configured.validate_configuration(gemini_player(effort=EffortLevel.MAXIMUM))

    unknown = GeminiInteractionsAdapter(api_key="test-key", models=("gemini-future",))
    unknown_capabilities = unknown.capabilities("gemini-future")
    assert unknown_capabilities["selectable"] is False
    assert unknown_capabilities["effort_levels"] == []
    assert unknown_capabilities["availability"] == "unsupported_capabilities"
    with pytest.raises(AdapterConfigurationError, match="verified Lounge thinking-level mapping"):
        unknown.validate_configuration(gemini_player(model="gemini-future"))

    wrong_provider = gemini_player().model_copy(update={"provider": "Imposter"})
    with pytest.raises(AdapterConfigurationError, match="disclose Google"):
        configured.validate_configuration(wrong_provider)

    wrong_transport = gemini_player().model_copy(
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
            {"status": "failed", "error": {"message": "sensitive provider detail"}},
            "failed to provide",
        ),
        ({"status": "in_progress", "steps": []}, "incomplete move response"),
        (
            {"status": "completed", "steps": [{"type": "model_output", "content": []}]},
            "no structured move output",
        ),
    ],
)
def test_gemini_adapter_rejects_non_move_responses_without_leaking_details(
    response: dict[str, object],
    message: str,
) -> None:
    async def run() -> None:
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=response)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            adapter = GeminiInteractionsAdapter(
                api_key="test-key",
                models=("gemini-3.8-flash",),
                client=client,
            )
            with pytest.raises(AdapterError, match=message) as captured:
                await adapter.choose_move(
                    move_request(legal_moves=["e2e4"]),
                    gemini_player(),
                )
            assert "sensitive provider detail" not in str(captured.value)

    asyncio.run(run())


def test_gemini_adapter_sanitizes_http_and_non_json_errors() -> None:
    async def run_error(response: httpx.Response, message: str) -> None:
        def handler(_: httpx.Request) -> httpx.Response:
            return response

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            adapter = GeminiInteractionsAdapter(
                api_key="test-key",
                models=("gemini-3.8-flash",),
                client=client,
            )
            with pytest.raises(AdapterError, match=message) as captured:
                await adapter.choose_move(
                    move_request(legal_moves=["e2e4"]),
                    gemini_player(),
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


def test_gemini_adapter_healthcheck_uses_the_models_endpoint() -> None:
    async def run() -> None:
        observed: dict[str, str | None] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            observed["path"] = request.url.path
            observed["api_key"] = request.headers.get("x-goog-api-key")
            return httpx.Response(200, json={"name": "models/gemini-3.8-flash"})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            adapter = GeminiInteractionsAdapter(
                api_key="test-key",
                models=("gemini-3.8-flash",),
                client=client,
            )
            assert await adapter.healthcheck() is True

        assert observed == {
            "path": "/v1beta/models/gemini-3.8-flash",
            "api_key": "test-key",
        }

    asyncio.run(run())


def test_gemini_adapter_completes_a_fenced_manager_turn() -> None:
    async def run() -> None:
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=completed_response())

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            adapter = GeminiInteractionsAdapter(
                api_key="test-key",
                models=("gemini-3.8-flash",),
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
                        white_player=gemini_player(spectator_delay_ms=0),
                        black_player=PlayerConfiguration.human("black"),
                    )
                )
                snapshot = await manager.wait_for_automation(game.id, timeout=2)

                assert [move.uci for move in snapshot.moves] == ["e2e4"]
                metadata = snapshot.moves[0].player_metadata
                assert metadata is not None
                assert metadata.adapter_id == "google"
                assert metadata.provider == "Google"
                assert metadata.model == "gemini-3.8-flash"
                assert metadata.effort is EffortLevel.BALANCED
                assert metadata.usage.input_tokens == 211
                assert metadata.usage.reasoning_tokens == 43
            finally:
                await manager.close()

    asyncio.run(run())


def test_gemini_provider_failure_pauses_without_paid_retry_loop() -> None:
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
            adapter = GeminiInteractionsAdapter(
                api_key="test-key",
                models=("gemini-3.8-flash",),
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
                        white_player=gemini_player(spectator_delay_ms=0),
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
