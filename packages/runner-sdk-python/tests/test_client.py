from __future__ import annotations

import asyncio
import json

import httpx
import pytest
from ai_chess_lounge_runner import (
    MoveProposal,
    RunnerClient,
    RunnerCredentials,
    RunnerProtocolError,
    TurnDelivery,
    UsageMetrics,
    proposal_for,
    proposal_signature,
)

SIGNING_KEY = "c3RhZ2U1Yi1jb250cmFjdC1rZXktMzItYnl0ZXMhISE"


def delivery_payload() -> dict[str, object]:
    return {
        "delivery_id": "061b82bc-902c-449a-a957-f41c8c55ea29",
        "expires_at": "2026-10-02T12:00:30+00:00",
        "request": {
            "schema_version": "1.0",
            "request_id": "request-1",
            "match_id": "match-1",
            "position_version": 7,
            "color": "black",
            "fen": "rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2",
            "moves_uci": ["e2e4", "e7e5"],
            "pgn": "1. e4 e5",
            "legal_moves": ["g1f3", "f1c4"],
            "remaining_ms": 59_000,
            "move_deadline_ms": 30_000,
            "division": "legal_assist",
            "public_summary_required": True,
        },
    }


def credentials_payload() -> dict[str, object]:
    return {
        "session_id": "a59ca4a6-3837-466a-b6f0-bd6459c8bfc4",
        "runner_token": "lounge_rs_a59ca4a6-3837-466a-b6f0-bd6459c8bfc4.secret",
        "signing_key": SIGNING_KEY,
        "permissions": ["turn:read", "move:submit", "heartbeat"],
        "expires_at": "2026-10-02T16:00:00+00:00",
        "player": {"player_id": "player-1", "display_name": "Sample bot"},
        "websocket_path": "/ws/runners",
        "next_turn_path": "/api/runner-sessions/turns/next",
        "proposal_path_template": "/api/runner-sessions/turns/{delivery_id}/proposal",
        "heartbeat_path": "/api/runner-sessions/heartbeat",
    }


def test_signature_contract_handles_nested_keys_and_unicode() -> None:
    delivery = TurnDelivery.from_dict(delivery_payload())
    proposal = proposal_for(
        delivery,
        move="g1f3",
        plan="Développer — then castle.",
        threat="Black may play …Nc6.",
        confidence=73,
    )

    assert (
        proposal_signature(
            SIGNING_KEY,
            delivery.delivery_id,
            "delivery:061b82bc",
            proposal,
        )
        == "0c366b4cf2b8386b927598a36690bd3252db2209fc653dad6d91bd98bf607272"
    )

    cost_proposal = proposal_for(
        delivery,
        move="g1f3",
        usage=UsageMetrics(
            input_tokens=4,
            output_tokens=2,
            reasoning_tokens=1,
            estimated_cost_usd=1,
        ),
    )
    assert cost_proposal.usage.estimated_cost_usd == 1.0
    assert (
        proposal_signature(
            SIGNING_KEY,
            delivery.delivery_id,
            "delivery:061b82bc",
            cost_proposal,
        )
        == "0a8ce3185d29a1495b9b60f72e7ca80af0d9b4b32a7dbecf0e6d28be0f5b032f"
    )

    small_cost = proposal_for(
        delivery,
        move="g1f3",
        usage=UsageMetrics(estimated_cost_usd=0.0000123),
    )
    assert (
        proposal_signature(
            SIGNING_KEY,
            delivery.delivery_id,
            "delivery:061b82bc",
            small_cost,
        )
        == "fb2f657e98df90403f8c50d82960ca91e427c16f79b4e16e89d3d2b689f67ca9"
    )


def test_credentials_repr_redacts_secrets() -> None:
    credentials = RunnerCredentials.from_dict(credentials_payload())
    rendered = repr(credentials)
    assert "<redacted>" in rendered
    assert "secret" not in rendered
    assert SIGNING_KEY not in rendered


def test_claim_poll_and_submit_with_safe_idempotent_retry() -> None:
    async def run() -> None:
        calls: list[httpx.Request] = []
        submit_attempts = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal submit_attempts
            calls.append(request)
            if request.url.path.endswith("/claim"):
                assert json.loads(request.content) == {"pairing_code": "pair_secret"}
                return httpx.Response(200, json=credentials_payload())
            assert request.headers["authorization"].startswith("Bearer lounge_rs_")
            if request.url.path.endswith("/turns/next"):
                return httpx.Response(200, json=delivery_payload())
            if request.url.path.endswith("/proposal"):
                submit_attempts += 1
                if submit_attempts == 1:
                    raise httpx.ConnectError("connection reset", request=request)
                body = json.loads(request.content)
                assert body["idempotency_key"] == delivery_payload()["delivery_id"]
                assert len(body["signature"]) == 64
                return httpx.Response(
                    200,
                    json={
                        "delivery_id": delivery_payload()["delivery_id"],
                        "accepted": True,
                        "duplicate": True,
                    },
                )
            raise AssertionError(f"Unexpected request: {request.url}")

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            client = await RunnerClient.claim(
                "http://127.0.0.1:8000",
                pairing_id="pairing/with slash",
                pairing_code="pair_secret",
                http_client=http,
            )
            delivery = await client.next_turn(wait_ms=100)
            assert delivery is not None
            proposal = proposal_for(delivery, move="g1f3")
            receipt = await client.submit(delivery, proposal)

        assert receipt.accepted is True
        assert receipt.duplicate is True
        assert submit_attempts == 2
        assert calls[0].url.raw_path.endswith(b"pairing%2Fwith%20slash/claim")

    asyncio.run(run())


def test_rejects_insecure_remote_server_and_mismatched_binding() -> None:
    with pytest.raises(ValueError, match="must use HTTPS"):
        RunnerClient(
            "http://example.com",
            RunnerCredentials.from_dict(credentials_payload()),
        )

    async def run() -> None:
        delivery = TurnDelivery.from_dict(delivery_payload())
        wrong = MoveProposal(
            request_id="wrong",
            match_id=delivery.request.match_id,
            position_version=delivery.request.position_version,
            move="g1f3",
        )
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: None)) as http:
            client = RunnerClient(
                "http://localhost:8000",
                RunnerCredentials.from_dict(credentials_payload()),
                http_client=http,
            )
            with pytest.raises(RunnerProtocolError, match="not bound"):
                await client.submit(delivery, wrong)

    asyncio.run(run())
