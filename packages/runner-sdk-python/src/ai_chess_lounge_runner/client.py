from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import inspect
import json
import math
import re
from collections.abc import Awaitable, Callable
from decimal import Decimal
from typing import Any
from urllib.parse import quote, urlsplit

import httpx

from .models import (
    MoveProposal,
    ProposalReceipt,
    ProtocolValueError,
    RunnerCredentials,
    TurnDelivery,
)

MoveHandler = Callable[[TurnDelivery], MoveProposal | Awaitable[MoveProposal]]
_IDEMPOTENCY_KEY = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")


class RunnerProtocolError(RuntimeError):
    """The Lounge returned a malformed or incompatible runner message."""


class RunnerHTTPError(RuntimeError):
    """A Lounge runner endpoint rejected the request."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(f"Lounge runner request failed ({status_code}): {detail}")
        self.status_code = status_code
        self.detail = detail


def _normalize_base_url(base_url: str) -> str:
    parsed = urlsplit(base_url)
    hostname = (parsed.hostname or "").casefold()
    if (
        parsed.scheme not in {"http", "https"}
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(
            "base_url must be an HTTP(S) server URL without credentials or query data."
        )
    loopback = hostname in {"localhost", "127.0.0.1", "::1"}
    if parsed.scheme != "https" and not loopback:
        raise ValueError("Non-loopback Lounge servers must use HTTPS.")
    return base_url.rstrip("/")


def proposal_signature(
    signing_key: str,
    delivery_id: str,
    idempotency_key: str,
    proposal: MoveProposal,
) -> str:
    """Sign exactly the canonical payload accepted by the Stage 5A server."""

    try:
        padded = (signing_key + "=" * (-len(signing_key) % 4)).encode("ascii")
        key = base64.b64decode(padded, altchars=b"-_", validate=True)
    except (UnicodeEncodeError, ValueError, TypeError) as exc:
        raise RunnerProtocolError("The runner signing key is not valid base64url.") from exc
    if len(key) != 32:
        raise RunnerProtocolError("The runner signing key must decode to 32 bytes.")
    encoded = _canonical_json(proposal.to_dict())
    payload = f"{delivery_id}\n{idempotency_key}\n{encoded}".encode()
    return hmac.new(key, payload, hashlib.sha256).hexdigest()


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
            raise RunnerProtocolError("Canonical proposal numbers must be finite.")
        encoded = format(Decimal(str(value)), "f")
        if "." in encoded:
            encoded = encoded.rstrip("0").rstrip(".")
        return "0" if encoded in {"", "-0"} else encoded
    if isinstance(value, list):
        return f"[{','.join(_canonical_json(item) for item in value)}]"
    if isinstance(value, dict):
        members = (
            f"{json.dumps(str(key), ensure_ascii=True)}:{_canonical_json(value[key])}"
            for key in sorted(value)
        )
        return f"{{{','.join(members)}}}"
    raise RunnerProtocolError(f"Unsupported canonical proposal value: {type(value).__name__}.")


class RunnerClient:
    """Async HTTP runner client with bound proposals and idempotent submission retries."""

    def __init__(
        self,
        base_url: str,
        credentials: RunnerCredentials,
        *,
        http_client: httpx.AsyncClient | None = None,
        _owns_http_client: bool | None = None,
    ) -> None:
        self.base_url = _normalize_base_url(base_url)
        self.credentials = credentials
        self._http = http_client or httpx.AsyncClient(timeout=35.0, follow_redirects=False)
        self._owns_http = http_client is None if _owns_http_client is None else _owns_http_client

    @classmethod
    async def claim(
        cls,
        base_url: str,
        *,
        pairing_id: str,
        pairing_code: str,
        http_client: httpx.AsyncClient | None = None,
    ) -> RunnerClient:
        normalized = _normalize_base_url(base_url)
        owns_client = http_client is None
        client = http_client or httpx.AsyncClient(timeout=35.0, follow_redirects=False)
        try:
            response = await client.post(
                f"{normalized}/api/runner-pairings/{quote(pairing_id, safe='')}/claim",
                json={"pairing_code": pairing_code},
                follow_redirects=False,
            )
            payload = cls._response_json(response)
            credentials = RunnerCredentials.from_dict(payload)
        except Exception:
            if owns_client:
                await client.aclose()
            raise
        return cls(
            normalized,
            credentials,
            http_client=client,
            _owns_http_client=owns_client,
        )

    async def __aenter__(self) -> RunnerClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    async def close(self) -> None:
        if self._owns_http:
            await self._http.aclose()

    async def heartbeat(self) -> dict[str, Any]:
        response = await self._http.post(
            self._url(self.credentials.heartbeat_path),
            headers=self._headers(),
            follow_redirects=False,
        )
        payload = self._response_json(response)
        if not isinstance(payload, dict):
            raise RunnerProtocolError("The heartbeat response must be a JSON object.")
        return payload

    async def next_turn(self, *, wait_ms: int = 25_000) -> TurnDelivery | None:
        if not 0 <= wait_ms <= 25_000:
            raise ValueError("wait_ms must be between 0 and 25000.")
        response = await self._http.get(
            self._url(self.credentials.next_turn_path),
            params={"wait_ms": wait_ms},
            headers=self._headers(),
            timeout=max(5.0, wait_ms / 1_000 + 5.0),
            follow_redirects=False,
        )
        if response.status_code == 204:
            return None
        try:
            return TurnDelivery.from_dict(self._response_json(response))
        except ProtocolValueError as exc:
            raise RunnerProtocolError(str(exc)) from exc

    async def submit(
        self,
        delivery: TurnDelivery,
        proposal: MoveProposal,
        *,
        idempotency_key: str | None = None,
        transport_retries: int = 1,
    ) -> ProposalReceipt:
        self._validate_binding(delivery, proposal)
        if type(transport_retries) is not int or not 0 <= transport_retries <= 3:
            raise ValueError("transport_retries must be between 0 and 3.")
        key = idempotency_key or delivery.delivery_id
        if not _IDEMPOTENCY_KEY.fullmatch(key):
            raise ValueError("idempotency_key must be 8-128 safe ASCII characters.")
        body = {
            "idempotency_key": key,
            "proposal": proposal.to_dict(),
            "signature": proposal_signature(
                self.credentials.signing_key,
                delivery.delivery_id,
                key,
                proposal,
            ),
        }
        path = self.credentials.proposal_path_template.replace(
            "{delivery_id}", quote(delivery.delivery_id, safe="")
        )
        response: httpx.Response | None = None
        for attempt in range(transport_retries + 1):
            try:
                response = await self._http.post(
                    self._url(path),
                    headers=self._headers(),
                    json=body,
                    follow_redirects=False,
                )
                break
            except httpx.TransportError:
                if attempt >= transport_retries:
                    raise
                await asyncio.sleep(0)
        if response is None:  # pragma: no cover - defensive; the loop always returns or raises.
            raise RunnerProtocolError("The proposal request did not produce a response.")
        try:
            return ProposalReceipt.from_dict(self._response_json(response))
        except ProtocolValueError as exc:
            raise RunnerProtocolError(str(exc)) from exc

    async def run(
        self,
        handler: MoveHandler,
        *,
        wait_ms: int = 25_000,
        stop_event: asyncio.Event | None = None,
    ) -> None:
        """Poll and answer turns until cancelled or an optional stop event is set."""

        while stop_event is None or not stop_event.is_set():
            delivery = await self.next_turn(wait_ms=wait_ms)
            if delivery is None:
                continue
            result = handler(delivery)
            proposal = await result if inspect.isawaitable(result) else result
            if not isinstance(proposal, MoveProposal):
                raise RunnerProtocolError("The move handler must return MoveProposal.")
            await self.submit(delivery, proposal)

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.credentials.runner_token}"}

    def _url(self, path: str) -> str:
        if not path.startswith("/"):
            raise RunnerProtocolError("Runner endpoint paths must start with '/'.")
        return f"{self.base_url}{path}"

    @staticmethod
    def _validate_binding(delivery: TurnDelivery, proposal: MoveProposal) -> None:
        request = delivery.request
        if (
            proposal.request_id != request.request_id
            or proposal.match_id != request.match_id
            or proposal.position_version != request.position_version
        ):
            raise RunnerProtocolError("The proposal is not bound to the delivered turn.")

    @staticmethod
    def _response_json(response: httpx.Response) -> object:
        if not response.is_success:
            detail = response.reason_phrase or "request rejected"
            try:
                body = response.json()
            except ValueError:
                body = None
            if isinstance(body, dict) and isinstance(body.get("detail"), str):
                detail = body["detail"]
            raise RunnerHTTPError(response.status_code, detail)
        try:
            return response.json()
        except ValueError as exc:
            raise RunnerProtocolError("The Lounge returned a non-JSON response.") from exc
