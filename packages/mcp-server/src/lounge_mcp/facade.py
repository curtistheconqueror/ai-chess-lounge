from __future__ import annotations

import asyncio
from collections import OrderedDict
from dataclasses import asdict, dataclass, field
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

import httpx
from ai_chess_lounge_runner import RunnerClient, proposal_for
from ai_chess_lounge_runner.client import RunnerHTTPError, RunnerProtocolError
from ai_chess_lounge_runner.models import MoveProposal, ProtocolValueError, TurnDelivery


class LoungeError(RuntimeError):
    """Safe error text suitable for an MCP transcript."""


@dataclass
class Settings:
    base_url: str = "http://127.0.0.1:8000"
    pairing_id: str = ""
    pairing_code: str = field(default="", repr=False)
    allow_create: bool = False

    def __post_init__(self) -> None:
        url = urlsplit(self.base_url)
        if (
            url.scheme not in {"http", "https"}
            or url.hostname not in {"localhost", "127.0.0.1", "::1"}
            or url.username is not None
            or url.password is not None
            or url.query
            or url.fragment
            or url.path not in {"", "/"}
        ):
            raise ValueError(
                "Stage 5C requires a loopback Lounge URL without credentials or paths."
            )
        self.base_url = self.base_url.rstrip("/")
        if bool(self.pairing_id) != bool(self.pairing_code):
            raise ValueError("Provide both pairing ID and code, or neither for spectator access.")
        if self.pairing_id:
            self.pairing_id = identifier(self.pairing_id)


def identifier(value: str) -> str:
    try:
        return str(UUID(value))
    except (ValueError, TypeError, AttributeError):
        raise LoungeError("Expected a valid Lounge UUID.") from None


def public_game(game: dict[str, Any]) -> dict[str, Any]:
    # Spectator snapshots contain legal moves. Do not turn watch/create/resources
    # into a side channel around a pure-reasoning player's assistance division.
    fields = {
        "id",
        "lifecycle",
        "status",
        "result",
        "turn",
        "version",
        "revision",
        "generation",
        "event_sequence",
        "fen",
        "initial_fen",
        "pgn",
        "moves",
        "last_move",
        "in_check",
        "white_player",
        "black_player",
        "clock",
        "strategy_banner",
        "created_at",
        "updated_at",
    }
    return {key: value for key, value in game.items() if key in fields}


class LoungeFacade:
    """One MCP process owns one runner identity; no credentials enter tool output."""

    def __init__(self, settings: Settings, *, http_client: httpx.AsyncClient | None = None):
        self.settings = settings
        self._http = http_client or httpx.AsyncClient(timeout=35, follow_redirects=False)
        self._owns_http = http_client is None
        self._runner: RunnerClient | None = None
        self._claim_attempted = False
        self._join_lock = asyncio.Lock()
        self._turn_lock = asyncio.Lock()
        self._deliveries: OrderedDict[str, TurnDelivery] = OrderedDict()
        self._proposals: dict[str, MoveProposal] = {}

    async def close(self) -> None:
        if self._owns_http:
            await self._http.aclose()
        self._runner = None
        self.settings.pairing_code = ""
        self._deliveries.clear()
        self._proposals.clear()

    async def request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            response = await self._http.request(
                method, self.settings.base_url + path, follow_redirects=False, **kwargs
            )
            if not response.is_success:
                raise LoungeError(f"Lounge request rejected (HTTP {response.status_code}).")
            return response.json()
        except (httpx.HTTPError, ValueError):
            # Never include response bodies, auth headers, request URLs, or secrets.
            raise LoungeError("Lounge connection failed or returned an invalid response.") from None

    def runner(self) -> RunnerClient:
        if self._runner is None:
            raise LoungeError("Call lounge_join first with an operator-configured pairing.")
        return self._runner

    async def join(self) -> dict[str, Any]:
        async with self._join_lock:
            if self._runner is None:
                if self._claim_attempted:
                    raise LoungeError(
                        "Claim outcome uncertain or rejected; restart with a new pairing."
                    )
                if not self.settings.pairing_id:
                    raise LoungeError(
                        "No pairing configured. Ask the operator to configure a pairing."
                    )
                self._claim_attempted = True
                try:
                    self._runner = await RunnerClient.claim(
                        self.settings.base_url,
                        pairing_id=self.settings.pairing_id,
                        pairing_code=self.settings.pairing_code,
                        http_client=self._http,
                    )
                except (httpx.HTTPError, RunnerHTTPError, RunnerProtocolError, ValueError):
                    raise LoungeError(
                        "Pairing claim failed; request a new pairing from the operator."
                    ) from None
                finally:
                    self.settings.pairing_code = ""
            credentials = self._runner.credentials
            return {
                "session_id": credentials.session_id,
                "player": credentials.player,
                "expires_at": credentials.expires_at,
                "permissions": list(credentials.permissions),
            }

    async def next_turn(self, wait_ms: int = 0) -> dict[str, Any]:
        if type(wait_ms) is not int or not 0 <= wait_ms <= 25_000:
            raise LoungeError("wait_ms must be an integer between 0 and 25000.")
        async with self._turn_lock:
            try:
                delivery = await self.runner().next_turn(wait_ms=wait_ms)
            except (httpx.HTTPError, RunnerHTTPError, RunnerProtocolError, ValueError):
                raise LoungeError(
                    "Turn polling failed; check runner session and Lounge availability."
                ) from None
            if delivery is None:
                return {"pending": False}
            self._deliveries[delivery.delivery_id] = delivery
            self._deliveries.move_to_end(delivery.delivery_id)
            while len(self._deliveries) > 32:
                old, _ = self._deliveries.popitem(last=False)
                self._proposals.pop(old, None)
            return {"pending": True, **asdict(delivery)}

    async def heartbeat(self) -> dict[str, Any]:
        try:
            return await self.runner().heartbeat()
        except (httpx.HTTPError, RunnerHTTPError, RunnerProtocolError, ValueError):
            raise LoungeError(
                "Heartbeat failed; check runner session and Lounge availability."
            ) from None

    async def submit(
        self,
        delivery_id: str,
        move: str,
        plan: str = "",
        threat: str = "",
        confidence: int | None = None,
    ) -> dict[str, Any]:
        async with self._turn_lock:
            delivery = self._deliveries.get(delivery_id)
            if delivery is None:
                raise LoungeError("Unknown delivery. Read lounge_next_turn before submitting.")
            try:
                proposal = proposal_for(
                    delivery, move=move, plan=plan, threat=threat, confidence=confidence
                )
            except ProtocolValueError:
                raise LoungeError("Invalid move or public summary fields.") from None
            previous = self._proposals.get(delivery_id)
            if previous is not None and previous != proposal:
                raise LoungeError(
                    "This delivery already has a proposal; retry the identical payload."
                )
            # Remember before sending: an interrupted request may already be accepted.
            self._proposals[delivery_id] = proposal
            try:
                receipt = await self.runner().submit(delivery, proposal)
            except RunnerHTTPError as exc:
                raise LoungeError(
                    f"Proposal rejected (HTTP {exc.status_code}); read the game state."
                ) from None
            except (httpx.HTTPError, RunnerProtocolError, ValueError):
                raise LoungeError(
                    "Submission outcome uncertain; retry the identical payload."
                ) from None
            return {
                **asdict(receipt),
                "note": "Receipt acknowledges delivery, not a committed move. Watch game state.",
            }

    async def watch(self, game_id: str) -> dict[str, Any]:
        return public_game(await self.request("GET", f"/api/games/{identifier(game_id)}"))

    async def create_game(
        self,
        white_player_id: str | None,
        black_player_id: str | None,
        initial_time_ms: int,
        increment_ms: int,
    ) -> dict[str, Any]:
        if not self.settings.allow_create:
            raise LoungeError("Game creation is disabled by the operator.")
        if not 100 <= initial_time_ms <= 86_400_000 or not 0 <= increment_ms <= 60_000:
            raise LoungeError("Invalid clock settings.")
        ids = [identifier(value) if value else None for value in (white_player_id, black_player_id)]
        if ids[0] is not None and ids[0] == ids[1]:
            raise LoungeError("Each remote seat must have its own runner identity.")
        sessions = await self.request("GET", "/api/runner-sessions")
        players = {
            row["player_id"]: row["player"]
            for row in sessions
            if not row["expired"] and not row["revoked"]
        }
        if any(value is not None and value not in players for value in ids):
            raise LoungeError("A remote seat is unavailable; join its runner first.")
        game = await self.request(
            "POST",
            "/api/games",
            json={
                "opponent": "human",
                "white_player": players.get(ids[0]),
                "black_player": players.get(ids[1]),
                "initial_time_ms": initial_time_ms,
                "increment_ms": increment_ms,
            },
        )
        return public_game(game)
