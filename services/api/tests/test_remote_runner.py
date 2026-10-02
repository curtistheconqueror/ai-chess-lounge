from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from lounge_api.manager import GameManager
from lounge_api.models import (
    CreateGameRequest,
    OpponentKind,
    RunnerPairingCreate,
    RunnerProposalSubmission,
)
from lounge_api.persistence import DatabaseStore
from lounge_api.player_protocol import MoveProposal, MoveRequest, UsageMetrics
from lounge_api.remote_runner import (
    RemoteRunnerBroker,
    RunnerAuthenticationError,
    RunnerPairingError,
    RunnerSubmissionError,
)

SECRET = b"stage-5a-test-secret-is-at-least-32-bytes"


class MutableClock:
    def __init__(self) -> None:
        self.current = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.current

    def advance(self, **kwargs: float) -> None:
        self.current += timedelta(**kwargs)


def pairing_request(**overrides: object) -> RunnerPairingCreate:
    return RunnerPairingCreate.model_validate(
        {
            "display_name": "Remote Test Agent",
            "provider": "Independent Runner",
            "model": "sample-bot-v1",
            "move_timeout_ms": 5_000,
            **overrides,
        }
    )


def test_pairing_is_one_time_and_secrets_are_not_stored_raw() -> None:
    async def run() -> None:
        store = DatabaseStore("sqlite+aiosqlite:///:memory:")
        broker = RemoteRunnerBroker(store, secret=SECRET)
        await store.initialize()
        try:
            pairing = await broker.create_pairing(pairing_request())
            stored_pairing = await store.load_runner_pairing(pairing.pairing_id)
            assert stored_pairing is not None
            assert stored_pairing.code_digest != pairing.pairing_code

            credentials = await broker.claim_pairing(
                pairing.pairing_id,
                pairing.pairing_code,
            )
            stored_session = await store.load_runner_session(credentials.session_id)
            assert stored_session is not None
            assert stored_session.token_digest != credentials.runner_token
            assert credentials.player.settings["runner_id"] == credentials.player.player_id
            assert credentials.permissions == ["turn:read", "move:submit", "heartbeat"]

            with pytest.raises(RunnerPairingError, match="already been claimed"):
                await broker.claim_pairing(pairing.pairing_id, pairing.pairing_code)
        finally:
            await broker.close()
            await store.close()

    asyncio.run(run())


def test_runner_token_expires_and_heartbeat_is_safe() -> None:
    async def run() -> None:
        clock = MutableClock()
        store = DatabaseStore("sqlite+aiosqlite:///:memory:")
        broker = RemoteRunnerBroker(store, secret=SECRET, clock=clock)
        await store.initialize()
        try:
            pairing = await broker.create_pairing(pairing_request(session_ttl_ms=300_000))
            credentials = await broker.claim_pairing(
                pairing.pairing_id,
                pairing.pairing_code,
            )
            status = await broker.heartbeat(credentials.runner_token)

            assert status.player_id == credentials.player.player_id
            assert status.expired is False
            assert "token" not in status.model_dump_json().lower()
            clock.advance(minutes=6)
            with pytest.raises(RunnerAuthenticationError, match="expired"):
                await broker.heartbeat(credentials.runner_token)
        finally:
            await broker.close()
            await store.close()

    asyncio.run(run())


def test_runner_session_survives_restart_with_stable_server_secret(tmp_path: Path) -> None:
    async def run() -> None:
        url = f"sqlite+aiosqlite:///{tmp_path / 'runner-restart.db'}"
        first_store = DatabaseStore(url)
        first = RemoteRunnerBroker(first_store, secret=SECRET)
        await first_store.initialize()
        pairing = await first.create_pairing(pairing_request())
        credentials = await first.claim_pairing(pairing.pairing_id, pairing.pairing_code)
        await first.close()
        await first_store.close()

        second_store = DatabaseStore(url)
        second = RemoteRunnerBroker(second_store, secret=SECRET)
        await second_store.initialize()
        try:
            restored = await second.authenticate(credentials.runner_token)
            assert restored.session_id == credentials.session_id
            assert restored.player.player_id == credentials.player.player_id
        finally:
            await second.close()
            await second_store.close()

        third_store = DatabaseStore(url)
        third = RemoteRunnerBroker(third_store, secret=b"a-different-stage-5a-secret-value!!")
        await third_store.initialize()
        try:
            with pytest.raises(RunnerAuthenticationError, match="invalid"):
                await third.authenticate(credentials.runner_token)
            assert (await third.statuses())[0].expired is True
        finally:
            await third.close()
            await third_store.close()

    asyncio.run(run())


def test_signed_idempotent_proposal_completes_remote_turn() -> None:
    async def run() -> None:
        store = DatabaseStore("sqlite+aiosqlite:///:memory:")
        broker = RemoteRunnerBroker(store, secret=SECRET)
        await store.initialize()
        try:
            pairing = await broker.create_pairing(pairing_request())
            credentials = await broker.claim_pairing(
                pairing.pairing_id,
                pairing.pairing_code,
            )
            request = MoveRequest(
                match_id="match-remote-1",
                position_version=0,
                color="white",
                fen="start",
                moves_uci=[],
                pgn="*",
                legal_moves=["e2e4"],
                remaining_ms=60_000,
                move_deadline_ms=5_000,
                division=credentials.player.division,
            )
            choose_task = asyncio.create_task(broker.request_turn(request, credentials.player))
            delivery = await broker.next_turn(credentials.runner_token, wait_ms=1_000)
            assert delivery is not None
            proposal = MoveProposal(
                request_id=request.request_id,
                match_id=request.match_id,
                position_version=request.position_version,
                move="e2e4",
                plan="Claim central space.",
                usage=UsageMetrics(input_tokens=10, output_tokens=4),
            )
            idempotency_key = "remote-proposal-0001"
            submission = RunnerProposalSubmission(
                idempotency_key=idempotency_key,
                proposal=proposal,
                signature=RemoteRunnerBroker.proposal_signature(
                    credentials.signing_key,
                    delivery.delivery_id,
                    idempotency_key,
                    proposal,
                ),
            )
            accepted = await broker.submit_proposal(
                credentials.runner_token,
                delivery.delivery_id,
                submission,
            )
            duplicate = await broker.submit_proposal(
                credentials.runner_token,
                delivery.delivery_id,
                submission,
            )

            assert accepted.duplicate is False
            assert duplicate.duplicate is True
            assert await choose_task == proposal
        finally:
            await broker.close()
            await store.close()

    asyncio.run(run())


def test_proposal_rejects_bad_signature_and_wrong_turn_binding() -> None:
    async def run() -> None:
        store = DatabaseStore("sqlite+aiosqlite:///:memory:")
        broker = RemoteRunnerBroker(store, secret=SECRET)
        await store.initialize()
        choose_task: asyncio.Task[MoveProposal] | None = None
        try:
            pairing = await broker.create_pairing(pairing_request())
            credentials = await broker.claim_pairing(
                pairing.pairing_id,
                pairing.pairing_code,
            )
            request = MoveRequest(
                match_id="match-remote-2",
                position_version=4,
                color="black",
                fen="position",
                moves_uci=["e2e4"],
                pgn="1. e4 *",
                legal_moves=["e7e5"],
                remaining_ms=60_000,
                move_deadline_ms=5_000,
                division=credentials.player.division,
            )
            choose_task = asyncio.create_task(broker.request_turn(request, credentials.player))
            delivery = await broker.next_turn(credentials.runner_token, wait_ms=1_000)
            assert delivery is not None
            mismatched = MoveProposal(
                request_id=request.request_id,
                match_id=request.match_id,
                position_version=5,
                move="e7e5",
            )
            bad_signature = RunnerProposalSubmission(
                idempotency_key="remote-proposal-0002",
                proposal=mismatched,
                signature="0" * 64,
            )
            with pytest.raises(RunnerSubmissionError, match="signature"):
                await broker.submit_proposal(
                    credentials.runner_token,
                    delivery.delivery_id,
                    bad_signature,
                )

            signed_mismatch = bad_signature.model_copy(
                update={
                    "signature": RemoteRunnerBroker.proposal_signature(
                        credentials.signing_key,
                        delivery.delivery_id,
                        bad_signature.idempotency_key,
                        mismatched,
                    )
                }
            )
            with pytest.raises(RunnerSubmissionError, match="not bound"):
                await broker.submit_proposal(
                    credentials.runner_token,
                    delivery.delivery_id,
                    signed_mismatch,
                )
        finally:
            if choose_task is not None:
                choose_task.cancel()
                await asyncio.gather(choose_task, return_exceptions=True)
            await broker.close()
            await store.close()

    asyncio.run(run())


def test_webhook_requires_operator_allowlist() -> None:
    async def run() -> None:
        store = DatabaseStore("sqlite+aiosqlite:///:memory:")
        broker = RemoteRunnerBroker(store, secret=SECRET, webhook_hosts=set())
        await store.initialize()
        try:
            with pytest.raises(ValueError, match="operator-allowlisted"):
                await broker.create_pairing(
                    pairing_request(webhook_url="https://runner.example/turn")
                )
            with pytest.raises(ValueError, match="operator-allowlisted"):
                await broker.create_pairing(
                    pairing_request(webhook_url="http://127.0.0.1/internal")
                )
        finally:
            await broker.close()
            await store.close()

    asyncio.run(run())


def test_allowlisted_webhook_receives_signed_turn_without_runner_token() -> None:
    async def run() -> None:
        received: list[httpx.Request] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            received.append(request)
            return httpx.Response(202)

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        store = DatabaseStore("sqlite+aiosqlite:///:memory:")
        broker = RemoteRunnerBroker(
            store,
            secret=SECRET,
            webhook_hosts={"runner.example"},
            http_client=client,
        )
        await store.initialize()
        choose_task: asyncio.Task[MoveProposal] | None = None
        try:
            pairing = await broker.create_pairing(
                pairing_request(webhook_url="https://runner.example/turn")
            )
            credentials = await broker.claim_pairing(
                pairing.pairing_id,
                pairing.pairing_code,
            )
            request = MoveRequest(
                match_id="match-webhook-1",
                position_version=0,
                color="white",
                fen="start",
                moves_uci=[],
                pgn="*",
                legal_moves=["d2d4"],
                remaining_ms=60_000,
                move_deadline_ms=5_000,
                division=credentials.player.division,
            )
            choose_task = asyncio.create_task(broker.request_turn(request, credentials.player))
            delivery = await broker.next_turn(credentials.runner_token, wait_ms=1_000)
            assert delivery is not None
            for _ in range(20):
                if received:
                    break
                await asyncio.sleep(0)
            assert len(received) == 1
            webhook = received[0]
            assert webhook.url == "https://runner.example/turn"
            assert webhook.headers["x-lounge-delivery-id"] == delivery.delivery_id
            assert len(webhook.headers["x-lounge-signature"]) == 64
            assert credentials.runner_token not in webhook.content.decode()
            assert credentials.signing_key not in webhook.content.decode()
        finally:
            if choose_task is not None:
                choose_task.cancel()
                await asyncio.gather(choose_task, return_exceptions=True)
            await broker.close()
            await client.aclose()
            await store.close()

    asyncio.run(run())


def test_manager_accepts_remote_runner_move_through_authoritative_lease() -> None:
    async def run() -> None:
        store = DatabaseStore("sqlite+aiosqlite:///:memory:")
        broker = RemoteRunnerBroker(store, secret=SECRET)
        manager = GameManager(
            store=store,
            remote_runners=broker,
            schedule_timeouts=False,
        )
        await manager.start()
        try:
            pairing = await broker.create_pairing(pairing_request())
            credentials = await broker.claim_pairing(
                pairing.pairing_id,
                pairing.pairing_code,
            )
            game = await manager.create(
                CreateGameRequest(
                    opponent=OpponentKind.HUMAN,
                    black_player=credentials.player,
                )
            )
            human_move = asyncio.create_task(manager.make_human_move(game.id, "e2e4", 0))
            delivery = await broker.next_turn(credentials.runner_token, wait_ms=1_000)
            assert delivery is not None
            assert delivery.request.match_id == game.id
            assert delivery.request.position_version == 1
            proposal = MoveProposal(
                request_id=delivery.request.request_id,
                match_id=game.id,
                position_version=1,
                move="e7e5",
                plan="Answer in the center.",
                threat="White can pressure f7.",
                confidence=82,
            )
            key = "manager-remote-0001"
            await broker.submit_proposal(
                credentials.runner_token,
                delivery.delivery_id,
                RunnerProposalSubmission(
                    idempotency_key=key,
                    proposal=proposal,
                    signature=RemoteRunnerBroker.proposal_signature(
                        credentials.signing_key,
                        delivery.delivery_id,
                        key,
                        proposal,
                    ),
                ),
            )
            snapshot = await human_move
            events = await manager.events(game.id)

            assert [move.uci for move in snapshot.moves] == ["e2e4", "e7e5"]
            assert snapshot.moves[-1].actor == "remote_runner:black"
            assert snapshot.moves[-1].player_metadata is not None
            assert snapshot.moves[-1].player_metadata.plan == "Answer in the center."
            serialized = " ".join(event.model_dump_json() for event in events)
            assert credentials.runner_token not in serialized
            assert credentials.signing_key not in serialized
        finally:
            await manager.close()

    asyncio.run(run())
