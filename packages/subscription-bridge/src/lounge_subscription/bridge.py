from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from uuid import UUID

import httpx
from ai_chess_lounge_runner import RunnerClient
from ai_chess_lounge_runner.models import MoveProposal, TurnDelivery

from .process import BridgeError

Chooser = Callable[[TurnDelivery, float], Awaitable[MoveProposal]]
TERMINAL = {"checkmate", "stalemate", "draw", "resigned", "timeout", "aborted", "adjudicated"}


def validate_profile(player: dict[str, object], model: str) -> None:
    if (
        player.get("connection_mode") != "subscription_bridge"
        or player.get("adapter_id") != "remote_runner"
        or player.get("provider") != "OpenAI"
        or player.get("model") != model
        or player.get("division") != "open_agentic"
        or player.get("effort") is not None
    ):
        raise BridgeError(
            "Pairing must match this OpenAI subscription model and open_agentic seat."
        )


async def run_match(
    client: RunnerClient,
    choose: Chooser,
    game_status: Callable[[str], Awaitable[str]],
    *,
    max_turns: int = 300,
    max_seconds: float = 3600,
) -> int:
    """Consume one explicit next-match grant. Never answer a second match or rerun a delivery."""
    if not 1 <= max_turns <= 1000 or not 1 <= max_seconds <= 14_400:
        raise BridgeError("Match limits are outside the supported range.")
    match_id: str | None = None
    last_delivery: str | None = None
    last_proposal: MoveProposal | None = None
    last_version = -1
    count = 0
    heartbeat_at = 0.0
    try:
        async with asyncio.timeout(max_seconds):
            while count < max_turns:
                if time.monotonic() >= heartbeat_at:
                    await client.heartbeat()
                    heartbeat_at = time.monotonic() + 15
                if match_id is not None and await game_status(match_id) in TERMINAL:
                    return count
                delivery = await client.next_turn(wait_ms=1000)
                if delivery is None:
                    continue
                try:
                    candidate = str(UUID(delivery.request.match_id))
                    expiry = datetime.fromisoformat(delivery.expires_at)
                    if expiry.tzinfo is None:
                        raise ValueError("naive expiry")
                except ValueError:
                    raise BridgeError(
                        "Lounge returned an invalid match identity or expiry."
                    ) from None
                if match_id is None:
                    match_id = candidate
                if candidate != match_id:
                    raise BridgeError("One-match authorization cannot be reused for another match.")
                if delivery.delivery_id == last_delivery and last_proposal is not None:
                    # A delivery can be polled again before the arbiter consumes its receipt.
                    await client.submit(delivery, last_proposal)
                    await asyncio.sleep(0.1)
                    continue
                if delivery.request.position_version <= last_version:
                    raise BridgeError("Refusing a repeated or older board position.")
                remaining = (expiry - datetime.now(UTC)).total_seconds()
                timeout = (
                    min(
                        remaining,
                        delivery.request.move_deadline_ms / 1000,
                        delivery.request.remaining_ms / 1000,
                        120,
                    )
                    - 0.25
                )
                if timeout <= 0:
                    raise BridgeError("The delivered turn has already expired.")
                proposal = await choose(delivery, timeout)
                if datetime.now(UTC) >= expiry:
                    raise BridgeError("The provider finished after the turn expired.")
                await client.submit(delivery, proposal)
                last_delivery, last_proposal = delivery.delivery_id, proposal
                last_version = delivery.request.position_version
                count += 1
    except TimeoutError:
        raise BridgeError("The one-match authorization reached its time limit.") from None
    raise BridgeError("The one-match authorization reached its turn limit.")


async def read_game_status(http: httpx.AsyncClient, base_url: str, match_id: str) -> str:
    # Public board read, without runner or provider credentials. UUID prevents path injection.
    response = await http.get(f"{base_url}/api/games/{UUID(match_id)}")
    response.raise_for_status()
    value = response.json()
    if not isinstance(value, dict) or not isinstance(value.get("status"), str):
        raise BridgeError("Lounge returned an invalid game status.")
    return value["status"]
