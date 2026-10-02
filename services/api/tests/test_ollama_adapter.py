from __future__ import annotations

import asyncio
import json

import httpx
import pytest
from lounge_api.adapters import AdapterConfigurationError, AdapterError
from lounge_api.ollama_adapter import OllamaChatAdapter
from lounge_api.player_protocol import (
    AssistanceDivision,
    ConnectionMode,
    EffortLevel,
    MoveRequest,
    PlayerConfiguration,
)


def ollama_player(*, effort: EffortLevel | None = None, **settings) -> PlayerConfiguration:
    return PlayerConfiguration(
        adapter_id="ollama",
        display_name="Local Llama",
        provider="Ollama",
        model="llama-chess:latest",
        connection_mode=ConnectionMode.LOCAL,
        effort=effort,
        division=AssistanceDivision.LEGAL_ASSIST,
        settings=settings,
    )


def move_request() -> MoveRequest:
    return MoveRequest(
        match_id="match-ollama",
        position_version=0,
        color="white",
        fen="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        moves_uci=[],
        pgn="*",
        legal_moves=["d2d4", "e2e4"],
        remaining_ms=30_000,
        move_deadline_ms=5_000,
        division=AssistanceDivision.LEGAL_ASSIST,
    )


def test_ollama_sends_native_structured_chat_and_normalizes_usage() -> None:
    async def run() -> None:
        captured: dict[str, object] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["path"] = request.url.path
            captured["authorization"] = request.headers.get("authorization")
            captured["payload"] = json.loads(request.content)
            return httpx.Response(
                200,
                json={
                    "done": True,
                    "message": {
                        "role": "assistant",
                        "content": json.dumps(
                            {
                                "move": "e2e4",
                                "plan": "Occupy the center.",
                                "threat": "Develop with tempo.",
                                "confidence": 78,
                            }
                        ),
                        "thinking": "private reasoning never enters the public proposal",
                    },
                    "prompt_eval_count": 190,
                    "eval_count": 52,
                },
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            adapter = OllamaChatAdapter(models=("llama-chess:latest",), client=client)
            proposal = await adapter.choose_move(
                move_request(),
                ollama_player(max_output_tokens=2_048),
            )

        payload = captured["payload"]
        assert isinstance(payload, dict)
        assert captured["path"] == "/api/chat"
        assert captured["authorization"] is None
        assert payload["stream"] is False
        assert payload["options"] == {"num_predict": 2_048}
        assert payload["format"]["additionalProperties"] is False
        assert "think" not in payload
        assert proposal.move == "e2e4"
        assert proposal.plan == "Occupy the center."
        assert proposal.usage.input_tokens == 190
        assert proposal.usage.output_tokens == 52
        assert proposal.usage.reasoning_tokens is None

    asyncio.run(run())


def test_ollama_requires_explicit_models_and_provider_default_effort() -> None:
    unconfigured = OllamaChatAdapter(models=())
    assert unconfigured.list_models() == []
    assert unconfigured.configured is False
    with pytest.raises(AdapterConfigurationError, match="not configured"):
        unconfigured.validate_configuration(ollama_player())

    adapter = OllamaChatAdapter(models=("llama-chess:latest",))
    capabilities = adapter.capabilities("llama-chess:latest")
    assert capabilities["selectable"] is True
    assert capabilities["effort_levels"] == []
    assert capabilities["credentials_required"] is False
    adapter.validate_configuration(ollama_player())
    with pytest.raises(AdapterConfigurationError, match="provider-default effort"):
        adapter.validate_configuration(ollama_player(effort=EffortLevel.DEEP))


@pytest.mark.parametrize(
    ("response", "message"),
    [
        ({"done": False, "message": {}}, "incomplete move response"),
        ({"done": True, "message": {}}, "no structured move output"),
        (
            {"done": True, "message": {"content": '{"move":"invalid"}'}},
            "malformed structured move",
        ),
    ],
)
def test_ollama_rejects_incomplete_or_malformed_output(
    response: dict[str, object],
    message: str,
) -> None:
    async def run() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _: httpx.Response(200, json=response))
        ) as client:
            adapter = OllamaChatAdapter(
                models=("llama-chess:latest",),
                client=client,
            )
            with pytest.raises(AdapterError, match=message):
                await adapter.choose_move(move_request(), ollama_player())

    asyncio.run(run())


def test_ollama_healthcheck_uses_tags_endpoint() -> None:
    async def run() -> None:
        paths: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            paths.append(request.url.path)
            return httpx.Response(200, json={"models": []})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            adapter = OllamaChatAdapter(
                models=("llama-chess:latest",),
                client=client,
            )
            assert await adapter.healthcheck() is True

        assert paths == ["/api/tags"]

    asyncio.run(run())
