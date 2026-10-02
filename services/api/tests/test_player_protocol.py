from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from lounge_api.adapters import ScriptedPlayerAdapter
from lounge_api.player_protocol import (
    PROTOCOL_VERSION,
    AssistanceDivision,
    ConnectionMode,
    MoveProposal,
    MoveRequest,
    PlayerConfiguration,
)
from pydantic import ValidationError


def scripted_player(*moves: str) -> PlayerConfiguration:
    return PlayerConfiguration(
        adapter_id="scripted",
        display_name="Deterministic Agent",
        provider="Lounge Test Harness",
        model="deterministic-v1",
        connection_mode=ConnectionMode.LOCAL,
        division=AssistanceDivision.LEGAL_ASSIST,
        settings={"moves": list(moves)},
    )


def test_protocol_round_trip_and_version_rejection() -> None:
    request = MoveRequest(
        match_id="match-1",
        position_version=0,
        color="white",
        fen="start",
        moves_uci=[],
        pgn="*",
        legal_moves=["e2e4"],
        remaining_ms=30_000,
        move_deadline_ms=5_000,
        division=AssistanceDivision.LEGAL_ASSIST,
    )
    proposal = MoveProposal(
        request_id=request.request_id,
        match_id=request.match_id,
        position_version=request.position_version,
        move="E2E4",
    )

    assert request.schema_version == PROTOCOL_VERSION
    assert MoveRequest.model_validate_json(request.model_dump_json()) == request
    assert MoveProposal.model_validate_json(proposal.model_dump_json()).move == "e2e4"
    with pytest.raises(ValidationError, match="Unsupported player protocol version"):
        MoveRequest.model_validate({**request.model_dump(), "schema_version": "99.0"})
    with pytest.raises(ValidationError, match="Unsupported player protocol version"):
        MoveProposal.model_validate({**proposal.model_dump(), "schema_version": "99.0"})


def test_player_configuration_rejects_inline_credentials() -> None:
    credential_aliases = (
        "api_key",
        "access_token",
        "refresh_token",
        "authorization",
        "private_key",
        "password",
        "cookie",
    )
    for field in credential_aliases:
        with pytest.raises(ValidationError, match="cannot contain credentials"):
            PlayerConfiguration(
                adapter_id="future-provider",
                display_name="Unsafe",
                provider="Example",
                model="example-1",
                connection_mode=ConnectionMode.DIRECT_API,
                settings={field: "must-never-live-here"},
            )

    with pytest.raises(ValidationError, match="cannot contain credentials"):
        PlayerConfiguration(
            adapter_id="stockfish",
            display_name="Unsafe nested agent",
            provider="Example",
            model="Stockfish",
            connection_mode=ConnectionMode.LOCAL,
            settings={"headers": [{"token": "do-not-store-this"}]},
        )


def test_openai_configuration_accepts_only_typed_public_settings() -> None:
    safe = PlayerConfiguration(
        adapter_id="openai",
        display_name="OpenAI Player",
        provider="OpenAI",
        model="gpt-6-luna",
        connection_mode=ConnectionMode.DIRECT_API,
        effort="balanced",
        division=AssistanceDivision.LEGAL_ASSIST,
        settings={
            "color": "white",
            "max_output_tokens": 4_096,
            "move_timeout_ms": 30_000,
            "spectator_delay_ms": 180,
        },
    )

    assert safe.settings["max_output_tokens"] == 4_096
    assert "credential" not in safe.model_dump_json().lower()
    with pytest.raises(ValidationError, match="max_output_tokens"):
        PlayerConfiguration.model_validate(
            {
                **safe.model_dump(),
                "settings": {"max_output_tokens": 100},
            }
        )
    with pytest.raises(ValidationError, match="OpenAI move_timeout_ms"):
        PlayerConfiguration.model_validate(
            {
                **safe.model_dump(),
                "settings": {"move_timeout_ms": 120_001},
            }
        )


def test_anthropic_configuration_accepts_only_typed_public_settings() -> None:
    safe = PlayerConfiguration(
        adapter_id="anthropic",
        display_name="Claude Player",
        provider="Anthropic",
        model="claude-opus-5-5",
        connection_mode=ConnectionMode.DIRECT_API,
        effort="maximum",
        division=AssistanceDivision.LEGAL_ASSIST,
        settings={
            "color": "black",
            "max_output_tokens": 16_384,
            "move_timeout_ms": 60_000,
            "spectator_delay_ms": 180,
        },
    )

    assert safe.settings["max_output_tokens"] == 16_384
    assert "credential" not in safe.model_dump_json().lower()
    with pytest.raises(ValidationError, match="Anthropic max_output_tokens"):
        PlayerConfiguration.model_validate(
            {
                **safe.model_dump(),
                "settings": {"max_output_tokens": 128_001},
            }
        )
    with pytest.raises(ValidationError, match="Anthropic move_timeout_ms"):
        PlayerConfiguration.model_validate(
            {
                **safe.model_dump(),
                "settings": {"move_timeout_ms": 120_001},
            }
        )


def test_scripted_adapter_is_deterministic_and_bound_to_request() -> None:
    async def run() -> None:
        adapter = ScriptedPlayerAdapter()
        player = scripted_player("e2e4")
        request = MoveRequest(
            match_id="match-1",
            position_version=0,
            color="white",
            fen="start",
            moves_uci=[],
            pgn="*",
            legal_moves=["d2d4", "e2e4"],
            remaining_ms=30_000,
            move_deadline_ms=5_000,
            division=AssistanceDivision.LEGAL_ASSIST,
        )

        first = await adapter.choose_move(request, player)
        second = await adapter.choose_move(request, player)

        assert first == second
        assert first.move == "e2e4"
        assert first.request_id == request.request_id
        assert first.position_version == request.position_version

    asyncio.run(run())


def test_published_json_schemas_pin_protocol_version() -> None:
    repository = Path(__file__).resolve().parents[3]
    request_schema = json.loads(
        (repository / "packages/protocol/move-request.schema.json").read_text()
    )
    proposal_schema = json.loads(
        (repository / "packages/protocol/move-proposal.schema.json").read_text()
    )

    assert request_schema["properties"]["schema_version"]["const"] == PROTOCOL_VERSION
    assert proposal_schema["properties"]["schema_version"]["const"] == PROTOCOL_VERSION
    assert "position_version" in request_schema["required"]
    assert "position_version" in proposal_schema["required"]
