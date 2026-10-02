from __future__ import annotations

import argparse
import asyncio
import getpass
import json
from uuid import UUID

import httpx
from ai_chess_lounge_runner import RunnerClient
from ai_chess_lounge_runner.models import TurnDelivery

from .bridge import read_game_status, run_match, validate_profile
from .codex import CodexProvider
from .process import BridgeError


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Local one-match subscription CLI bridge")
    commands = result.add_subparsers(dest="command", required=True)
    for name in ("doctor", "run"):
        command = commands.add_parser(name)
        command.add_argument("--provider", choices=["codex"], default="codex")
        command.add_argument("--model", required=True, help="Exact model ID available to your CLI")
        command.add_argument("--codex-executable", default="codex")
        if name == "run":
            command.add_argument("--base-url", default="http://127.0.0.1:8000")
            command.add_argument("--pairing-id", required=True, type=UUID)
            command.add_argument(
                "--authorize-next-match",
                action="store_true",
                required=True,
                help="Authorize this paired seat for its next match only",
            )
            command.add_argument("--max-turns", type=int, default=300)
            command.add_argument("--max-seconds", type=int, default=3600)
    return result


async def execute(args: argparse.Namespace) -> None:
    provider = CodexProvider(args.model, args.codex_executable)
    readiness = await provider.doctor()
    print(json.dumps(readiness), flush=True)
    if args.command == "doctor":
        return
    if not readiness["subscription_login"]:
        raise BridgeError(
            "Run codex login locally with ChatGPT, then retry. No API fallback is used."
        )
    if not 1 <= args.max_turns <= 1000 or not 1 <= args.max_seconds <= 14_400:
        raise BridgeError("Use 1–1000 turns and 1–14400 seconds.")
    code = getpass.getpass("One-time Lounge pairing code (hidden): ")
    client = await RunnerClient.claim(
        args.base_url, pairing_id=str(args.pairing_id), pairing_code=code
    )
    del code
    async with client, httpx.AsyncClient(timeout=10, follow_redirects=False) as public_http:
        validate_profile(client.credentials.player, args.model)
        print(
            "Paired. Select this seat in the Lounge and start one match. Ctrl-C stops the bridge.",
            flush=True,
        )

        async def choose(delivery: TurnDelivery, timeout: float):
            return await provider.choose_move(delivery, timeout=timeout)

        async def status(match_id: str) -> str:
            return await read_game_status(public_http, client.base_url, match_id)

        count = await run_match(
            client, choose, status, max_turns=args.max_turns, max_seconds=args.max_seconds
        )
        print(f"Match finished. Submitted {count} moves; authorization is now consumed.")


def main() -> None:
    args = parser().parse_args()
    try:
        asyncio.run(execute(args))
    except KeyboardInterrupt:
        print("Bridge stopped. Revoke its runner session in the Lounge when finished.")
    except BridgeError as exc:
        raise SystemExit(str(exc)) from None
    except Exception:
        # HTTP errors and CLI diagnostics can contain secrets or private provider output.
        raise SystemExit(
            "Bridge failed. Check the Lounge connection and local CLI setup."
        ) from None


if __name__ == "__main__":
    main()
