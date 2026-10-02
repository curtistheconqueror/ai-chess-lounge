from __future__ import annotations

import asyncio
import json

import httpx
import pytest
from lounge_api.adapters import AdapterConfigurationError, AdapterError, AdapterRegistry
from lounge_api.manager import GameManager
from lounge_api.models import CreateGameRequest, OpponentKind
from lounge_api.openai_compatible_adapter import (
    OPENROUTER_FOUR_LEVEL_EFFORT_MAP,
    OpenRouterChatAdapter,
    VLLMChatAdapter,
)
from lounge_api.persistence import DatabaseStore
from lounge_api.player_protocol import (
    AssistanceDivision,
    ConnectionMode,
    EffortLevel,
    MoveRequest,
    PlayerConfiguration,
)


def player(
    adapter_id: str,
    provider: str,
    model: str,
    connection_mode: ConnectionMode,
    effort: EffortLevel | None,
    **settings,
) -> PlayerConfiguration:
    return PlayerConfiguration(
        adapter_id=adapter_id,
        display_name=f"{provider} Test Player",
        provider=provider,
        model=model,
        connection_mode=connection_mode,
        effort=effort,
        division=AssistanceDivision.LEGAL_ASSIST,
        settings=settings,
    )


def move_request(*, legal_moves: list[str] | None = None) -> MoveRequest:
    return MoveRequest(
        match_id="match-1",
        position_version=3,
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


def completion_response(*, move: str = "e2e4") -> dict[str, object]:
    return {
        "choices": [
            {
                "finish_reason": "stop",
                "message": {
                    "role": "assistant",
                    "content": json.dumps(
                        {
                            "move": move,
                            "plan": "Claim central space and develop quickly.",
                            "threat": "Black can challenge the center immediately.",
                            "confidence": 84,
                        }
                    ),
                },
            }
        ],
        "usage": {
            "prompt_tokens": 230,
            "completion_tokens": 91,
            "completion_tokens_details": {"reasoning_tokens": 37},
        },
    }


def test_openrouter_sends_strict_structured_request_and_verified_effort() -> None:
    async def run() -> None:
        captured: dict[str, object] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["path"] = request.url.path
            captured["authorization"] = request.headers.get("authorization")
            captured["payload"] = json.loads(request.content)
            return httpx.Response(200, json=completion_response())

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            adapter = OpenRouterChatAdapter(
                api_key="router-key",
                models=("openai/gpt-6.1-sol",),
                client=client,
            )
            request = move_request(legal_moves=["d2d4", "e2e4"])
            proposal = await adapter.choose_move(
                request,
                player(
                    "openrouter",
                    "OpenRouter",
                    "openai/gpt-6.1-sol",
                    ConnectionMode.DIRECT_API,
                    EffortLevel.MAXIMUM,
                    max_output_tokens=8_192,
                ),
            )

        payload = captured["payload"]
        assert isinstance(payload, dict)
        assert captured["path"] == "/api/v1/chat/completions"
        assert captured["authorization"] == "Bearer router-key"
        assert payload["provider"] == {"require_parameters": True}
        assert payload["reasoning"] == {"effort": "max", "exclude": True}
        assert payload["max_tokens"] == 8_192
        assert payload["response_format"]["type"] == "json_schema"
        assert payload["response_format"]["json_schema"]["strict"] is True
        assert "Legal moves (UCI): d2d4 e2e4" in payload["messages"][1]["content"]
        assert proposal.move == "e2e4"
        assert proposal.request_id == request.request_id
        assert proposal.usage.input_tokens == 230
        assert proposal.usage.output_tokens == 91
        assert proposal.usage.reasoning_tokens == 37

    asyncio.run(run())


def test_openrouter_effort_is_model_specific_and_unknown_models_use_default() -> None:
    adapter = OpenRouterChatAdapter(
        api_key="router-key",
        models=("openai/gpt-6-astra", "vendor/future-model"),
    )
    known = adapter.capabilities("openai/gpt-6-astra")
    unknown = adapter.capabilities("vendor/future-model")

    assert known["provider_effort_map"] == {
        effort.value: provider_effort
        for effort, provider_effort in OPENROUTER_FOUR_LEVEL_EFFORT_MAP.items()
    }
    assert unknown["selectable"] is True
    assert unknown["effort_levels"] == []
    future_player = player(
        "openrouter",
        "OpenRouter",
        "vendor/future-model",
        ConnectionMode.DIRECT_API,
        None,
    )
    payload = adapter._request_payload(move_request(legal_moves=["e2e4"]), future_player)
    assert "reasoning" not in payload
    adapter.validate_configuration(future_player)

    with pytest.raises(AdapterConfigurationError, match="provider default"):
        adapter.validate_configuration(
            future_player.model_copy(update={"effort": EffortLevel.DEEP})
        )


def test_openrouter_rejects_missing_credentials_and_sanitizes_failures() -> None:
    unconfigured = OpenRouterChatAdapter(
        api_key=None,
        models=("openai/gpt-6.1-sol",),
    )
    unconfigured._api_key = None
    with pytest.raises(AdapterConfigurationError, match="not configured"):
        unconfigured.validate_configuration(
            player(
                "openrouter",
                "OpenRouter",
                "openai/gpt-6.1-sol",
                ConnectionMode.DIRECT_API,
                EffortLevel.BALANCED,
            )
        )

    async def run_http_failure() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(
                    429,
                    json={"error": {"message": "do-not-leak-provider-detail"}},
                )
            )
        ) as client:
            adapter = OpenRouterChatAdapter(
                api_key="router-key",
                models=("openai/gpt-6.1-sol",),
                client=client,
            )
            with pytest.raises(AdapterError, match="HTTP 429") as failure:
                await adapter.choose_move(
                    move_request(legal_moves=["e2e4"]),
                    player(
                        "openrouter",
                        "OpenRouter",
                        "openai/gpt-6.1-sol",
                        ConnectionMode.DIRECT_API,
                        EffortLevel.BALANCED,
                    ),
                )
            assert "do-not-leak" not in str(failure.value)

    asyncio.run(run_http_failure())


def test_openrouter_completes_a_fenced_manager_turn_with_public_metadata() -> None:
    async def run() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _: httpx.Response(200, json=completion_response()))
        ) as client:
            adapter = OpenRouterChatAdapter(
                api_key="router-key",
                models=("openai/gpt-6.1-sol",),
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
                        white_player=player(
                            "openrouter",
                            "OpenRouter",
                            "openai/gpt-6.1-sol",
                            ConnectionMode.DIRECT_API,
                            EffortLevel.BALANCED,
                            spectator_delay_ms=0,
                        ),
                        black_player=PlayerConfiguration.human("black"),
                    )
                )
                snapshot = await manager.wait_for_automation(game.id, timeout=2)

                assert [move.uci for move in snapshot.moves] == ["e2e4"]
                metadata = snapshot.moves[0].player_metadata
                assert metadata is not None
                assert metadata.adapter_id == "openrouter"
                assert metadata.provider == "OpenRouter"
                assert metadata.model == "openai/gpt-6.1-sol"
                assert metadata.effort is EffortLevel.BALANCED
                assert metadata.usage.input_tokens == 230
                assert metadata.usage.reasoning_tokens == 37
            finally:
                await manager.close()

    asyncio.run(run())


def test_vllm_uses_local_openai_compatible_transport_without_claiming_effort() -> None:
    async def run() -> None:
        captured: dict[str, object] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["path"] = request.url.path
            captured["authorization"] = request.headers.get("authorization")
            captured["payload"] = json.loads(request.content)
            return httpx.Response(200, json=completion_response(move="d2d4"))

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            adapter = VLLMChatAdapter(models=("local/chess-model",), client=client)
            capabilities = adapter.capabilities("local/chess-model")
            proposal = await adapter.choose_move(
                move_request(legal_moves=["d2d4", "e2e4"]),
                player(
                    "vllm",
                    "vLLM",
                    "local/chess-model",
                    ConnectionMode.LOCAL,
                    None,
                ),
            )

        payload = captured["payload"]
        assert isinstance(payload, dict)
        assert captured["path"] == "/v1/chat/completions"
        assert captured["authorization"] is None
        assert "reasoning" not in payload
        assert "provider" not in payload
        assert capabilities["connection_mode"] == "local"
        assert capabilities["credentials_required"] is False
        assert capabilities["effort_levels"] == []
        assert proposal.move == "d2d4"

    asyncio.run(run())


def test_openai_compatible_healthchecks_use_models_endpoint() -> None:
    async def run() -> None:
        paths: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            paths.append(request.url.path)
            return httpx.Response(200, json={"data": []})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            openrouter = OpenRouterChatAdapter(
                api_key="router-key",
                models=("openai/gpt-6.1-sol",),
                client=client,
            )
            vllm = VLLMChatAdapter(models=("local/chess-model",), client=client)
            assert await openrouter.healthcheck() is True
            assert await vllm.healthcheck() is True

        assert paths == ["/api/v1/models", "/v1/models"]

    asyncio.run(run())
