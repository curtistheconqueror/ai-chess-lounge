from __future__ import annotations

import asyncio
import json

import httpx
import pytest
from lounge_api.adapters import AdapterConfigurationError, AdapterError, AdapterRegistry
from lounge_api.manager import GameManager
from lounge_api.models import CreateGameRequest, OpponentKind
from lounge_api.openai_adapter import OPENAI_EFFORT_MAP, OpenAIResponsesAdapter
from lounge_api.persistence import DatabaseStore
from lounge_api.player_protocol import (
    AssistanceDivision,
    ConnectionMode,
    EffortLevel,
    MoveRequest,
    PlayerConfiguration,
)
from sqlalchemy.exc import OperationalError


def openai_player(
    *,
    effort: EffortLevel = EffortLevel.BALANCED,
    division: AssistanceDivision = AssistanceDivision.LEGAL_ASSIST,
    **settings,
) -> PlayerConfiguration:
    return PlayerConfiguration(
        adapter_id="openai",
        display_name="OpenAI Test Player",
        provider="OpenAI",
        model="gpt-test",
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


def completed_response(*, move: str = "e2e4") -> dict[str, object]:
    return {
        "id": "resp_test",
        "status": "completed",
        "output": [
            {
                "type": "message",
                "content": [
                    {
                        "type": "output_text",
                        "text": json.dumps(
                            {
                                "move": move,
                                "plan": "Claim central space and develop quickly.",
                                "threat": "Black can challenge the center immediately.",
                                "confidence": 82,
                            }
                        ),
                    }
                ],
            }
        ],
        "usage": {
            "input_tokens": 211,
            "output_tokens": 97,
            "output_tokens_details": {"reasoning_tokens": 64},
        },
    }


def test_openai_adapter_sends_non_stored_structured_request() -> None:
    async def run() -> None:
        captured: dict[str, object] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["authorization"] = request.headers.get("Authorization")
            captured["payload"] = json.loads(request.content)
            return httpx.Response(200, json=completed_response())

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            adapter = OpenAIResponsesAdapter(
                api_key="test-key",
                models=("gpt-test",),
                client=client,
            )
            assert adapter.capabilities("gpt-test")["selectable"] is True
            assert adapter.capabilities("gpt-test")["availability"] == "configured_unverified"
            request = move_request(legal_moves=["d2d4", "e2e4"])
            proposal = await adapter.choose_move(request, openai_player())

        payload = captured["payload"]
        assert isinstance(payload, dict)
        assert captured["authorization"] == "Bearer test-key"
        assert payload["model"] == "gpt-test"
        assert payload["store"] is False
        assert payload["reasoning"] == {"effort": "medium"}
        assert payload["text"]["format"]["type"] == "json_schema"
        assert payload["text"]["format"]["strict"] is True
        assert "Legal moves (UCI): d2d4 e2e4" in payload["input"]
        assert proposal.move == "e2e4"
        assert proposal.request_id == request.request_id
        assert proposal.match_id == request.match_id
        assert proposal.position_version == request.position_version
        assert proposal.usage.input_tokens == 211
        assert proposal.usage.output_tokens == 97
        assert proposal.usage.reasoning_tokens == 64
        assert proposal.usage.estimated_cost_usd is None

    asyncio.run(run())


@pytest.mark.parametrize(
    ("effort", "provider_effort"),
    list(OPENAI_EFFORT_MAP.items()),
)
def test_openai_effort_mapping_is_exact(
    effort: EffortLevel,
    provider_effort: str,
) -> None:
    adapter = OpenAIResponsesAdapter(api_key="test-key", models=("gpt-test",))
    payload = adapter._request_payload(
        move_request(legal_moves=["e2e4"]),
        openai_player(effort=effort),
    )

    assert payload["reasoning"] == {"effort": provider_effort}


def test_openai_pure_reasoning_omits_legal_move_assistance() -> None:
    adapter = OpenAIResponsesAdapter(api_key="test-key", models=("gpt-test",))
    payload = adapter._request_payload(
        move_request(legal_moves=None),
        openai_player(division=AssistanceDivision.PURE_REASONING),
    )

    assert "Legal moves (UCI)" not in payload["input"]
    assert "Assistance division: pure_reasoning" in payload["input"]


def test_openai_adapter_rejects_missing_credentials_and_unsupported_model() -> None:
    unconfigured = OpenAIResponsesAdapter(api_key=None, models=("gpt-test",))
    unconfigured._api_key = None
    with pytest.raises(AdapterConfigurationError, match="not configured"):
        unconfigured.validate_configuration(openai_player())

    configured = OpenAIResponsesAdapter(api_key="test-key", models=("another-model",))
    with pytest.raises(AdapterConfigurationError, match="not enabled"):
        configured.validate_configuration(openai_player())

    wrong_provider = openai_player().model_copy(update={"provider": "Imposter"})
    configured = OpenAIResponsesAdapter(api_key="test-key", models=("gpt-test",))
    with pytest.raises(AdapterConfigurationError, match="disclose OpenAI"):
        configured.validate_configuration(wrong_provider)

    wrong_transport = openai_player().model_copy(
        update={"connection_mode": ConnectionMode.SUBSCRIPTION_BRIDGE}
    )
    with pytest.raises(AdapterConfigurationError, match="direct_api"):
        configured.validate_configuration(wrong_transport)


def test_openai_adapter_sanitizes_provider_errors_and_malformed_output() -> None:
    async def run_error() -> None:
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(
                401,
                json={"error": {"message": "sensitive provider detail"}},
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            adapter = OpenAIResponsesAdapter(
                api_key="test-key",
                models=("gpt-test",),
                client=client,
            )
            with pytest.raises(AdapterError, match="HTTP 401") as captured:
                await adapter.choose_move(
                    move_request(legal_moves=["e2e4"]),
                    openai_player(),
                )
            assert "sensitive provider detail" not in str(captured.value)

    async def run_malformed() -> None:
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=completed_response(move="not-a-move"))

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            adapter = OpenAIResponsesAdapter(
                api_key="test-key",
                models=("gpt-test",),
                client=client,
            )
            with pytest.raises(AdapterError, match="malformed structured move"):
                await adapter.choose_move(
                    move_request(legal_moves=["e2e4"]),
                    openai_player(),
                )

    async def run_refusal() -> None:
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "status": "completed",
                    "output": [
                        {
                            "type": "message",
                            "content": [{"type": "refusal", "refusal": "cannot comply"}],
                        }
                    ],
                },
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            adapter = OpenAIResponsesAdapter(
                api_key="test-key",
                models=("gpt-test",),
                client=client,
            )
            with pytest.raises(AdapterError, match="refused"):
                await adapter.choose_move(
                    move_request(legal_moves=["e2e4"]),
                    openai_player(),
                )

    async def run_non_json() -> None:
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=b"not-json")

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            adapter = OpenAIResponsesAdapter(
                api_key="test-key",
                models=("gpt-test",),
                client=client,
            )
            with pytest.raises(AdapterError, match="non-JSON"):
                await adapter.choose_move(
                    move_request(legal_moves=["e2e4"]),
                    openai_player(),
                )

    asyncio.run(run_error())
    asyncio.run(run_malformed())
    asyncio.run(run_refusal())
    asyncio.run(run_non_json())


def test_openai_adapter_completes_a_fenced_manager_turn_with_usage_metadata() -> None:
    async def run() -> None:
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=completed_response())

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            adapter = OpenAIResponsesAdapter(
                api_key="test-key",
                models=("gpt-test",),
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
                        white_player=openai_player(spectator_delay_ms=0),
                        black_player=PlayerConfiguration.human("black"),
                    )
                )
                snapshot = await manager.wait_for_automation(game.id, timeout=2)

                assert [move.uci for move in snapshot.moves] == ["e2e4"]
                metadata = snapshot.moves[0].player_metadata
                assert metadata is not None
                assert metadata.adapter_id == "openai"
                assert metadata.provider == "OpenAI"
                assert metadata.model == "gpt-test"
                assert metadata.effort is EffortLevel.BALANCED
                assert metadata.usage.input_tokens == 211
                assert metadata.usage.reasoning_tokens == 64
            finally:
                await manager.close()

    asyncio.run(run())


def test_openai_provider_failure_pauses_without_paid_retry_loop() -> None:
    async def run() -> None:
        calls = 0

        def handler(_: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(401, json={"error": {"message": "invalid key detail"}})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            adapter = OpenAIResponsesAdapter(
                api_key="test-key",
                models=("gpt-test",),
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
                        white_player=openai_player(spectator_delay_ms=0),
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
                assert "invalid key detail" not in str(events[-2].payload)
            finally:
                await manager.close()

    asyncio.run(run())


def test_openai_success_is_not_repeated_after_persistence_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def run() -> None:
        calls = 0

        def handler(_: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(200, json=completed_response())

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            adapter = OpenAIResponsesAdapter(
                api_key="test-key",
                models=("gpt-test",),
                client=client,
            )
            manager = GameManager(
                adapters=AdapterRegistry([adapter]),
                store=DatabaseStore("sqlite+aiosqlite:///:memory:"),
                schedule_timeouts=False,
            )
            await manager.start()

            async def fail_record_move(*args, **kwargs) -> None:
                del args, kwargs
                raise OperationalError("INSERT", {}, RuntimeError("database unavailable"))

            monkeypatch.setattr(manager.store, "record_move", fail_record_move)
            try:
                game = await manager.create(
                    CreateGameRequest(
                        opponent=OpponentKind.HUMAN,
                        white_player=openai_player(spectator_delay_ms=0),
                        black_player=PlayerConfiguration.human("black"),
                    )
                )
                snapshot = await manager.wait_for_automation(game.id, timeout=2)
                await asyncio.sleep(0.6)
                events = await manager.events(game.id)

                assert calls == 1
                assert snapshot.lifecycle.value == "paused"
                assert snapshot.moves == []
                assert events[-2].payload["reason"] == "provider_turn_interrupted"
            finally:
                await manager.close()

    asyncio.run(run())
