from __future__ import annotations

import argparse
import asyncio
import getpass

from .client import RunnerClient, RunnerHTTPError
from .models import TurnDelivery, proposal_for


def choose_first_legal(delivery: TurnDelivery):
    legal_moves = delivery.request.legal_moves
    if not legal_moves:
        raise RuntimeError("The sample bot requires a Legal Assist seat with legal_moves enabled.")
    return proposal_for(
        delivery,
        move=legal_moves[0],
        plan="Play the first deterministic legal move from the disclosed move list.",
        threat="This sample demonstrates transport, not chess strength.",
        confidence=25,
    )


async def _run(args: argparse.Namespace) -> None:
    pairing_code = getpass.getpass("One-time pairing code: ")
    client = await RunnerClient.claim(
        args.base_url,
        pairing_id=args.pairing_id,
        pairing_code=pairing_code,
    )
    display_name = client.credentials.player.get("display_name", "remote runner")
    print(f"Paired {display_name}; waiting for turns. Press Ctrl+C to stop.")
    async with client:
        try:
            await client.run(choose_first_legal)
        except RunnerHTTPError as exc:
            if exc.status_code not in {401, 403}:
                raise
            # Revoked, expired or replaced: the authorization is over, not the program.
            print(f"Runner session ended ({exc.status_code}). Pair again for the next match.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the deterministic Lounge sample bot.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--pairing-id", required=True)
    args = parser.parse_args()
    try:
        asyncio.run(_run(args))
    except KeyboardInterrupt:
        print("Stopped.")


if __name__ == "__main__":
    main()
