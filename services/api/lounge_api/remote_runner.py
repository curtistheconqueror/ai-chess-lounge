from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import math
import os
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import anyio
import httpx
from fastapi import WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from .adapters import AdapterConfigurationError, AdapterDeadlineExceeded, AdapterError
from .models import (
    RunnerPairingCreate,
    RunnerPairingRecord,
    RunnerPairingResponse,
    RunnerProposalReceipt,
    RunnerProposalSubmission,
    RunnerSessionCredentials,
    RunnerSessionRecord,
    RunnerSessionStatus,
    RunnerTurnDelivery,
)
from .persistence import DatabaseStore, RunnerTrustError
from .player_protocol import (
    ConnectionMode,
    MoveProposal,
    MoveRequest,
    PlayerConfiguration,
    UsageMetrics,
)

RUNNER_PERMISSIONS = ["turn:read", "move:submit", "heartbeat"]


class RunnerPairingError(RuntimeError):
    """A one-time runner pairing could not be claimed."""


class RunnerAuthenticationError(RuntimeError):
    """A runner token is missing, invalid, expired, or revoked."""


class RunnerSubmissionError(RuntimeError):
    """A remote runner proposal is stale, invalid, or unauthorized."""


async def _shield_store_call(awaitable):
    """Finish short runner DB operations before propagating ASGI cancellation."""

    with anyio.CancelScope(shield=True):
        return await awaitable


@dataclass
class _PendingTurn:
    delivery: RunnerTurnDelivery
    session_id: str
    player_id: str
    future: asyncio.Future[MoveProposal]
    match_revision: int | None = None
    idempotency_key: str | None = None
    payload_hash: str | None = None


class RemoteRunnerBroker:
    """Pair remote agents and relay fenced turn requests without provider credentials."""

    def __init__(
        self,
        store: DatabaseStore,
        *,
        secret: bytes | None = None,
        clock: Callable[[], datetime] | None = None,
        webhook_hosts: set[str] | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        configured_secret = os.getenv("LOUNGE_RUNNER_SECRET")
        self._secret = secret or (
            configured_secret.encode("utf-8") if configured_secret else secrets.token_bytes(32)
        )
        if len(self._secret) < 32:
            raise ValueError("LOUNGE_RUNNER_SECRET must contain at least 32 bytes.")
        configured_hosts = {
            host.strip().casefold()
            for host in os.getenv("LOUNGE_RUNNER_WEBHOOK_HOSTS", "").split(",")
            if host.strip()
        }
        self._webhook_hosts = (
            {host.casefold() for host in webhook_hosts}
            if webhook_hosts is not None
            else configured_hosts
        )
        self.store = store
        self._clock = clock or (lambda: datetime.now(UTC))
        self._turn_changed = asyncio.Event()
        self._pending: dict[str, _PendingTurn] = {}
        self._completed: dict[str, tuple[str, str, str, datetime]] = {}
        self._connected: set[str] = set()
        self._http_client = http_client
        self._owns_http_client = http_client is None

    async def close(self) -> None:
        if self._owns_http_client and self._http_client is not None:
            await self._http_client.aclose()
        self._http_client = None
        for pending in self._pending.values():
            if not pending.future.done():
                pending.future.cancel()
        self._pending.clear()

    async def create_pairing(self, request: RunnerPairingCreate) -> RunnerPairingResponse:
        webhook_url = self._validate_webhook_url(request.webhook_url)
        now = self._clock()
        pairing_id = str(uuid4())
        pairing_code = f"pair_{secrets.token_urlsafe(18)}"
        player_id = str(uuid4())
        player = PlayerConfiguration(
            player_id=player_id,
            adapter_id="remote_runner",
            display_name=request.display_name,
            comparison=request.comparison,
            provider=request.provider,
            model=request.model,
            connection_mode=request.connection_mode,
            effort=request.effort,
            division=request.division,
            settings={
                "runner_id": player_id,
                "move_timeout_ms": request.move_timeout_ms,
                "max_turns": request.max_turns,
                "match_ttl_ms": request.match_ttl_ms,
            },
        )
        expires_at = now + timedelta(milliseconds=request.pairing_ttl_ms)
        await self.store.create_runner_pairing(
            RunnerPairingRecord(
                pairing_id=pairing_id,
                code_digest=self._digest("pairing", pairing_code),
                player=player,
                session_ttl_ms=request.session_ttl_ms,
                webhook_url=webhook_url,
                created_at=now.isoformat(),
                expires_at=expires_at.isoformat(),
            )
        )
        return RunnerPairingResponse(
            pairing_id=pairing_id,
            pairing_code=pairing_code,
            expires_at=expires_at.isoformat(),
            player=player,
        )

    async def claim_pairing(
        self,
        pairing_id: str,
        pairing_code: str,
    ) -> RunnerSessionCredentials:
        now = self._clock()
        pairing = await self.store.load_runner_pairing(pairing_id)
        supplied_digest = self._digest("pairing", pairing_code)
        if pairing is None or not hmac.compare_digest(pairing.code_digest, supplied_digest):
            raise RunnerPairingError("The pairing code is invalid.")
        if pairing.claimed_at is not None:
            raise RunnerPairingError("The pairing code has already been claimed.")
        if datetime.fromisoformat(pairing.expires_at) <= now:
            raise RunnerPairingError("The pairing code has expired.")

        session_id = str(uuid4())
        runner_token = f"lounge_rs_{session_id}.{secrets.token_urlsafe(32)}"
        expires_at = now + timedelta(milliseconds=pairing.session_ttl_ms)
        session = RunnerSessionRecord(
            session_id=session_id,
            pairing_id=pairing_id,
            player=pairing.player,
            token_digest=self._digest("token", runner_token),
            issuer_digest=self._issuer_digest(),
            permissions=RUNNER_PERMISSIONS,
            webhook_url=pairing.webhook_url,
            created_at=now.isoformat(),
            expires_at=expires_at.isoformat(),
            last_heartbeat_at=now.isoformat(),
        )
        claimed = await self.store.claim_runner_pairing(
            pairing_id,
            supplied_digest,
            session,
            now=now,
        )
        if not claimed:
            raise RunnerPairingError("The pairing code is no longer available.")
        return RunnerSessionCredentials(
            session_id=session_id,
            runner_token=runner_token,
            signing_key=self._signing_key(session_id),
            permissions=RUNNER_PERMISSIONS,
            expires_at=expires_at.isoformat(),
            player=pairing.player,
        )

    async def authenticate(self, runner_token: str) -> RunnerSessionRecord:
        session_id = self._session_id_from_token(runner_token)
        session = await _shield_store_call(self.store.load_runner_session(session_id))
        if (
            session is None
            or not hmac.compare_digest(session.issuer_digest, self._issuer_digest())
            or not hmac.compare_digest(
                session.token_digest,
                self._digest("token", runner_token),
            )
        ):
            raise RunnerAuthenticationError("The runner token is invalid.")
        now = self._clock()
        if session.revoked_at is not None:
            raise RunnerAuthenticationError("The runner session has been revoked.")
        if datetime.fromisoformat(session.expires_at) <= now:
            raise RunnerAuthenticationError("The runner session has expired.")
        return session

    async def heartbeat(self, runner_token: str) -> RunnerSessionStatus:
        session = await self.authenticate(runner_token)
        now = self._clock()
        if not await _shield_store_call(
            self.store.touch_runner_session(session.session_id, now=now)
        ):
            raise RunnerAuthenticationError("The runner session is no longer active.")
        session = session.model_copy(update={"last_heartbeat_at": now.isoformat()})
        return self._status(session, now=now)

    async def statuses(self) -> list[RunnerSessionStatus]:
        now = self._clock()
        return [
            self._status(session, now=now).model_copy(
                update={"match_grant": await self.store.runner_grant(session.session_id)}
            )
            for session in await self.store.list_runner_sessions()
        ]

    async def revoke(self, session_id: str) -> None:
        if not await self.store.revoke_runner_session(session_id, now=self._clock()):
            raise RunnerPairingError("The runner session does not exist.")
        self._turn_changed.set()
        for pending in list(self._pending.values()):
            if pending.session_id == session_id and not pending.future.done():
                pending.future.set_exception(AdapterError("The runner session was revoked."))

    async def _check_delivery(self, session_id: str, delivery: RunnerTurnDelivery) -> None:
        if delivery.delivery_id not in self._pending:
            raise RunnerAuthenticationError("The turn delivery is no longer active.")
        try:
            await _shield_store_call(
                self.store.check_runner_grant(
                    session_id,
                    delivery.request.match_id,
                    delivery.request.color,
                    now=self._clock(),
                    position_version=delivery.request.position_version,
                    match_revision=self._pending[delivery.delivery_id].match_revision,
                )
            )
        except RunnerTrustError as exc:
            raise RunnerAuthenticationError(str(exc)) from exc

    async def validate_new_match(
        self,
        player: PlayerConfiguration,
        *,
        match_id: str | None = None,
        generation: int = 0,
        color: str | None = None,
    ) -> None:
        session = await self.store.load_active_runner_session_for_player(
            player.player_id, now=self._clock()
        )
        if (
            session is None
            or session.player != player
            or not hmac.compare_digest(session.issuer_digest, self._issuer_digest())
        ):
            raise AdapterConfigurationError("Pair an active runner with this exact profile first.")
        grant = await self.store.runner_grant(session.session_id)
        if grant is not None and (
            grant["match_id"] != match_id
            or grant["generation"] != generation
            or grant["color"] != color
            or datetime.fromisoformat(grant["expires_at"]) <= self._clock()
            or grant["turns_dispatched"] >= grant["max_turns"]
        ):
            raise AdapterConfigurationError(
                "Pair a new runner, or return an authorized runner to its original match and seat."
            )

    async def request_turn(
        self,
        request: MoveRequest,
        player: PlayerConfiguration,
    ) -> MoveProposal:
        now = self._clock()
        session = await self.store.load_active_runner_session_for_player(
            player.player_id,
            now=now,
        )
        if session is None:
            raise AdapterError("The paired remote runner is offline or its session expired.")
        if session.player != player:
            raise AdapterError("The match player profile does not match the paired runner profile.")
        if not hmac.compare_digest(session.issuer_digest, self._issuer_digest()):
            raise AdapterError("The paired remote runner session is no longer valid.")
        if any(
            p.session_id == session.session_id and not p.future.done()
            for p in self._pending.values()
        ):
            raise AdapterError("The runner already has an active turn.")
        try:
            grant = await self.store.reserve_runner_turn(
                session.session_id,
                request.match_id,
                request.color,
                now=now,
                position_version=request.position_version,
                match_revision=request._match_revision,
            )
        except RunnerTrustError as exc:
            raise AdapterError(str(exc)) from exc
        deadline = min(
            now + timedelta(milliseconds=request.move_deadline_ms),
            datetime.fromisoformat(str(grant["expires_at"])),
        )
        delivery = RunnerTurnDelivery(
            delivery_id=str(uuid4()),
            expires_at=deadline.isoformat(),
            request=request,
        )
        loop = asyncio.get_running_loop()
        pending = _PendingTurn(
            delivery=delivery,
            session_id=session.session_id,
            player_id=player.player_id,
            future=loop.create_future(),
            match_revision=grant["match_revision"],
        )
        self._pending[delivery.delivery_id] = pending
        self._turn_changed.set()
        if session.webhook_url is not None:
            asyncio.create_task(self._send_webhook(session, delivery))
        try:
            async with asyncio.timeout(max(0, (deadline - now).total_seconds())):
                return await pending.future
        except TimeoutError as exc:
            raise AdapterDeadlineExceeded(
                "The remote runner did not answer before the move deadline."
            ) from exc
        finally:
            self._pending.pop(delivery.delivery_id, None)
            self._prune_completed(now=self._clock())

    async def next_turn(
        self,
        runner_token: str,
        *,
        wait_ms: int,
    ) -> RunnerTurnDelivery | None:
        session = await self.authenticate(runner_token)
        await _shield_store_call(
            self.store.touch_runner_session(session.session_id, now=self._clock())
        )
        # Pending is the source of truth, not a consumed transport queue. A lost
        # response/reconnect gets the identical delivery with its original deadline.
        end = asyncio.get_running_loop().time() + wait_ms / 1_000
        while True:
            self._turn_changed.clear()
            for pending in list(self._pending.values()):
                if (
                    pending.session_id == session.session_id
                    and not pending.future.done()
                    and datetime.fromisoformat(pending.delivery.expires_at) > self._clock()
                ):
                    await self._check_delivery(session.session_id, pending.delivery)
                    return pending.delivery
            remaining = end - asyncio.get_running_loop().time()
            if remaining <= 0:
                return None
            try:
                await asyncio.wait_for(self._turn_changed.wait(), min(1.0, remaining))
            except TimeoutError:
                pass
            await self.authenticate(runner_token)

    async def submit_proposal(
        self,
        runner_token: str,
        delivery_id: str,
        submission: RunnerProposalSubmission,
    ) -> RunnerProposalReceipt:
        session = await self.authenticate(runner_token)
        now = self._clock()
        await _shield_store_call(self.store.touch_runner_session(session.session_id, now=now))
        canonical = self._proposal_payload(
            delivery_id,
            submission.idempotency_key,
            submission.proposal,
        )
        payload_hash = hashlib.sha256(canonical).hexdigest()
        completed = self._completed.get(delivery_id)
        if completed is not None:
            completed_session, key, digest, _ = completed
            if (
                completed_session == session.session_id
                and key == submission.idempotency_key
                and hmac.compare_digest(digest, payload_hash)
            ):
                return RunnerProposalReceipt(delivery_id=delivery_id, duplicate=True)
            raise RunnerSubmissionError("The delivery already has a different proposal.")

        pending = self._pending.get(delivery_id)
        if pending is None:
            raise RunnerSubmissionError("The turn delivery is unknown or no longer active.")
        if pending.session_id != session.session_id:
            raise RunnerSubmissionError("The runner session is not authorized for this delivery.")
        if datetime.fromisoformat(pending.delivery.expires_at) <= now:
            raise RunnerSubmissionError("The turn delivery has expired.")
        await self._check_delivery(session.session_id, pending.delivery)
        if pending.future.done():
            raise RunnerSubmissionError("The turn delivery is no longer active.")
        expected_signature = self.proposal_signature(
            self._signing_key(session.session_id),
            delivery_id,
            submission.idempotency_key,
            submission.proposal,
        )
        if not hmac.compare_digest(expected_signature, submission.signature):
            raise RunnerSubmissionError("The proposal signature is invalid.")
        request = pending.delivery.request
        proposal = submission.proposal
        if (
            proposal.request_id != request.request_id
            or proposal.match_id != request.match_id
            or proposal.position_version != request.position_version
        ):
            raise RunnerSubmissionError("The proposal is not bound to the active turn request.")
        if pending.idempotency_key is not None:
            if pending.idempotency_key == submission.idempotency_key and hmac.compare_digest(
                pending.payload_hash or "", payload_hash
            ):
                return RunnerProposalReceipt(delivery_id=delivery_id, duplicate=True)
            raise RunnerSubmissionError("The delivery already has a different proposal.")

        pending.idempotency_key = submission.idempotency_key
        pending.payload_hash = payload_hash
        self._completed[delivery_id] = (
            session.session_id,
            submission.idempotency_key,
            payload_hash,
            now,
        )
        if not pending.future.done():
            pending.future.set_result(proposal)
        return RunnerProposalReceipt(delivery_id=delivery_id)

    async def socket_loop(self, websocket: WebSocket, runner_token: str) -> None:
        session = await self.authenticate(runner_token)
        await websocket.accept()
        self._connected.add(session.session_id)
        last_delivery_id = None
        try:
            await _shield_store_call(
                self.store.touch_runner_session(session.session_id, now=self._clock())
            )
            while True:
                await self.authenticate(runner_token)
                receive_task = asyncio.create_task(websocket.receive_json())
                delivery_task = asyncio.create_task(self.next_turn(runner_token, wait_ms=1_000))
                tasks = {receive_task, delivery_task}
                try:
                    done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                finally:
                    # ASGI servers can cancel an asyncio task more than once while
                    # shutdown is unwinding. An AnyIO shield does not mask direct
                    # Task.cancel() calls, so keep the gather shielded and drain it
                    # even if another cancellation arrives during cleanup.
                    with anyio.CancelScope(shield=True):
                        await self._cancel_and_drain(tasks)
                if receive_task in done:
                    message = receive_task.result()
                    await self._handle_socket_message(websocket, runner_token, message)
                if delivery_task in done:
                    delivery = delivery_task.result()
                    if delivery is not None and delivery.delivery_id != last_delivery_id:
                        last_delivery_id = delivery.delivery_id
                        await self._check_delivery(session.session_id, delivery)
                        await websocket.send_json(
                            {
                                "type": "turn.requested",
                                "payload": delivery.model_dump(mode="json"),
                            }
                        )
                if delivery_task in done and delivery_task.result() is not None:
                    await asyncio.sleep(0.05)
        except WebSocketDisconnect:
            return
        finally:
            self._connected.discard(session.session_id)

    @staticmethod
    async def _cancel_and_drain(tasks: set[asyncio.Task]) -> None:
        for task in tasks:
            if not task.done():
                task.cancel()
        cleanup = asyncio.gather(*tasks, return_exceptions=True)
        cancelled_during_cleanup = False
        while not cleanup.done():
            try:
                await asyncio.shield(cleanup)
            except asyncio.CancelledError:
                cancelled_during_cleanup = True
        # Consume gather's result so exceptions raised by either child are observed.
        cleanup.result()
        if cancelled_during_cleanup:
            raise asyncio.CancelledError

    async def _handle_socket_message(
        self,
        websocket: WebSocket,
        runner_token: str,
        message: object,
    ) -> None:
        if not isinstance(message, dict):
            await websocket.send_json({"type": "error", "detail": "Invalid runner message."})
            return
        message_type = message.get("type")
        if message_type == "heartbeat":
            status = await self.heartbeat(runner_token)
            await websocket.send_json(
                {"type": "heartbeat.ack", "payload": status.model_dump(mode="json")}
            )
            return
        if message_type == "turn.proposed":
            try:
                delivery_id = str(message.get("delivery_id", ""))
                submission = RunnerProposalSubmission.model_validate(message.get("payload"))
                receipt = await self.submit_proposal(runner_token, delivery_id, submission)
            except (ValidationError, RunnerSubmissionError) as exc:
                await websocket.send_json({"type": "error", "detail": str(exc)})
                return
            await websocket.send_json(
                {"type": "turn.accepted", "payload": receipt.model_dump(mode="json")}
            )
            return
        await websocket.send_json({"type": "error", "detail": "Unsupported runner message."})

    async def _send_webhook(
        self,
        session: RunnerSessionRecord,
        delivery: RunnerTurnDelivery,
    ) -> None:
        if session.webhook_url is None:
            return
        try:
            await self._check_delivery(session.session_id, delivery)
        except RunnerAuthenticationError:
            return
        body = {
            "type": "turn.requested",
            "payload": delivery.model_dump(mode="json"),
        }
        encoded = json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
        signature = hmac.new(
            self._decode_signing_key(self._signing_key(session.session_id)),
            encoded,
            hashlib.sha256,
        ).hexdigest()
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=5.0, follow_redirects=False)
        try:
            await self._http_client.post(
                session.webhook_url,
                json=body,
                headers={
                    "X-Lounge-Delivery-Id": delivery.delivery_id,
                    "X-Lounge-Signature": signature,
                },
            )
        except httpx.HTTPError:
            # The same delivery remains available over WebSocket and authenticated
            # long-poll, so callback failure never causes an unsafe second turn.
            return

    def _status(
        self,
        session: RunnerSessionRecord,
        *,
        now: datetime,
    ) -> RunnerSessionStatus:
        return RunnerSessionStatus(
            session_id=session.session_id,
            player=session.player,
            player_id=session.player.player_id,
            display_name=session.player.display_name,
            provider=session.player.provider,
            model=session.player.model,
            permissions=session.permissions,
            transport="webhook" if session.webhook_url else "websocket_or_http",
            connected=session.session_id in self._connected,
            created_at=session.created_at,
            expires_at=session.expires_at,
            last_heartbeat_at=session.last_heartbeat_at,
            expired=(
                datetime.fromisoformat(session.expires_at) <= now
                or not hmac.compare_digest(session.issuer_digest, self._issuer_digest())
            ),
            revoked=session.revoked_at is not None,
        )

    def _validate_webhook_url(self, webhook_url: str | None) -> str | None:
        if webhook_url is None:
            return None
        parsed = urlsplit(webhook_url)
        hostname = (parsed.hostname or "").casefold()
        if (
            parsed.scheme != "https"
            or not hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
            or parsed.port not in {None, 443}
            or hostname not in self._webhook_hosts
        ):
            raise ValueError("Runner webhook URLs must use HTTPS on an operator-allowlisted host.")
        return webhook_url

    def _digest(self, purpose: str, value: str) -> str:
        return hmac.new(
            self._secret,
            f"{purpose}:{value}".encode(),
            hashlib.sha256,
        ).hexdigest()

    def _signing_key(self, session_id: str) -> str:
        raw = hmac.new(
            self._secret,
            f"signing:{session_id}".encode(),
            hashlib.sha256,
        ).digest()
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

    def _issuer_digest(self) -> str:
        return self._digest("issuer", "stage5a")

    @staticmethod
    def _decode_signing_key(signing_key: str) -> bytes:
        return base64.urlsafe_b64decode(signing_key + "=" * (-len(signing_key) % 4))

    @classmethod
    def proposal_signature(
        cls,
        signing_key: str,
        delivery_id: str,
        idempotency_key: str,
        proposal: MoveProposal,
    ) -> str:
        return hmac.new(
            cls._decode_signing_key(signing_key),
            cls._proposal_payload(delivery_id, idempotency_key, proposal),
            hashlib.sha256,
        ).hexdigest()

    @staticmethod
    def _proposal_payload(
        delivery_id: str,
        idempotency_key: str,
        proposal: MoveProposal,
    ) -> bytes:
        encoded = RemoteRunnerBroker._canonical_json(proposal.model_dump(mode="json"))
        return f"{delivery_id}\n{idempotency_key}\n{encoded}".encode()

    @staticmethod
    def _canonical_json(value: object) -> str:
        if value is None:
            return "null"
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, str):
            return json.dumps(value, ensure_ascii=True, separators=(",", ":"))
        if isinstance(value, int):
            return str(value)
        if isinstance(value, float):
            if not math.isfinite(value):
                raise ValueError("Canonical proposal numbers must be finite.")
            encoded = format(Decimal(str(value)), "f")
            if "." in encoded:
                encoded = encoded.rstrip("0").rstrip(".")
            return "0" if encoded in {"", "-0"} else encoded
        if isinstance(value, list):
            return f"[{','.join(RemoteRunnerBroker._canonical_json(item) for item in value)}]"
        if isinstance(value, dict):
            members = (
                f"{json.dumps(str(key), ensure_ascii=True)}:"
                f"{RemoteRunnerBroker._canonical_json(value[key])}"
                for key in sorted(value)
            )
            return f"{{{','.join(members)}}}"
        raise TypeError(f"Unsupported canonical proposal value: {type(value).__name__}.")

    @staticmethod
    def _session_id_from_token(runner_token: str) -> str:
        prefix = "lounge_rs_"
        if not runner_token.startswith(prefix) or "." not in runner_token:
            raise RunnerAuthenticationError("The runner token is invalid.")
        session_id = runner_token[len(prefix) :].split(".", 1)[0]
        try:
            UUID(session_id)
        except ValueError as exc:
            raise RunnerAuthenticationError("The runner token is invalid.") from exc
        return session_id

    def _prune_completed(self, *, now: datetime) -> None:
        cutoff = now - timedelta(minutes=5)
        self._completed = {
            delivery_id: record
            for delivery_id, record in self._completed.items()
            if record[3] > cutoff
        }


class RemoteRunnerAdapter:
    adapter_id = "remote_runner"

    def __init__(self, broker: RemoteRunnerBroker) -> None:
        self.broker = broker

    def list_models(self) -> list[str]:
        return ["paired-runner"]

    def capabilities(self, model: str) -> dict[str, object]:
        return {
            "model": model,
            "connection_mode": ConnectionMode.REMOTE_RUNNER.value,
            "connection_modes": [
                ConnectionMode.REMOTE_RUNNER.value,
                ConnectionMode.SUBSCRIPTION_BRIDGE.value,
            ],
            "effort_levels": [],
            "structured_output": True,
            "credentials_required": False,
            "pairing_required": True,
            "transports": ["websocket", "https_webhook", "http_long_poll"],
        }

    def validate_configuration(self, player: PlayerConfiguration) -> None:
        if player.connection_mode not in {
            ConnectionMode.REMOTE_RUNNER,
            ConnectionMode.SUBSCRIPTION_BRIDGE,
        }:
            raise AdapterConfigurationError(
                "Remote runner players must use remote_runner or subscription_bridge mode."
            )
        if player.settings.get("runner_id") != player.player_id:
            raise AdapterConfigurationError("The runner_id must match the paired player_id.")
        if player.connection_mode is ConnectionMode.SUBSCRIPTION_BRIDGE:
            if player.provider != "OpenAI":
                raise AdapterConfigurationError(
                    "Codex subscription bridge players must disclose OpenAI."
                )
            if player.effort is not None:
                raise AdapterConfigurationError(
                    "Subscription bridge players use provider-default effort."
                )
            if player.division.value != "open_agentic":
                raise AdapterConfigurationError(
                    "Subscription bridge players require the open_agentic division."
                )

    async def choose_move(
        self,
        request: MoveRequest,
        player: PlayerConfiguration,
    ) -> MoveProposal:
        return await self.broker.request_turn(request, player)

    def normalize_usage(self, usage: object) -> UsageMetrics:
        if isinstance(usage, UsageMetrics):
            return usage
        return UsageMetrics()

    async def healthcheck(self) -> bool:
        return True


def bearer_token(authorization: str | None) -> str:
    if authorization is None or not authorization.startswith("Bearer "):
        raise RunnerAuthenticationError("A runner bearer token is required.")
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise RunnerAuthenticationError("A runner bearer token is required.")
    return token
