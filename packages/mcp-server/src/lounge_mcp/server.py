from __future__ import annotations

import argparse
import json
import os
from collections.abc import AsyncIterator, Awaitable
from contextlib import asynccontextmanager
from typing import Annotated, Any

from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp.server.mcpserver.exceptions import ResourceError, ToolError
from mcp.types import ToolAnnotations
from pydantic import Field

from .facade import LoungeError, LoungeFacade, Settings

READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False)
SUBMIT = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True)


async def tool_result(operation: Awaitable[Any]) -> Any:
    try:
        return await operation
    except LoungeError as exc:
        raise ToolError(str(exc)) from None
    except Exception:
        raise ToolError("Lounge operation failed. Check the local bridge configuration.") from None


def create_server(settings: Settings, *, facade: LoungeFacade | None = None) -> MCPServer:
    @asynccontextmanager
    async def lifespan(_: MCPServer) -> AsyncIterator[LoungeFacade]:
        active = facade or LoungeFacade(settings)
        try:
            yield active
        finally:
            await active.close()

    server = MCPServer(
        "AI Chess Lounge",
        version="0.1.0",
        lifespan=lifespan,
        log_level="WARNING",
        instructions=(
            "Join the operator-configured pairing once. Read lounge_next_turn, choose a move "
            "using only the assistance supplied in that request, and submit its delivery_id "
            "with a UCI move and short public plan. Never submit private chain-of-thought. "
            "Poll again for subsequent turns. Host permissions remain under user control. "
            "A delivery receipt is not proof of a committed move; watch the game state."
        ),
    )

    @server.tool(annotations=WRITE)
    async def lounge_join(ctx: Context[LoungeFacade]) -> dict[str, Any]:
        """Claim the startup pairing once; return a safe player profile, never credentials."""
        return await tool_result(ctx.request_context.lifespan_context.join())

    @server.tool(annotations=READ)
    async def lounge_watch(game_id: str, ctx: Context[LoungeFacade]) -> dict[str, Any]:
        """Read current board, clocks, public strategy, FEN and PGN without engine analysis."""
        return await tool_result(ctx.request_context.lifespan_context.watch(game_id))

    @server.tool(annotations=WRITE)
    async def lounge_next_turn(
        ctx: Context[LoungeFacade],
        wait_ms: Annotated[int, Field(ge=0, le=25_000)] = 0,
    ) -> dict[str, Any]:
        """Poll your joined runner's turn, including only its allowed assistance; bounded wait."""
        return await tool_result(ctx.request_context.lifespan_context.next_turn(wait_ms))

    @server.tool(annotations=SUBMIT)
    async def lounge_submit_move(
        delivery_id: str,
        move: Annotated[str, Field(pattern=r"^[a-h][1-8][a-h][1-8][qrbn]?$")],
        ctx: Context[LoungeFacade],
        plan: Annotated[str, Field(max_length=280)] = "",
        threat: Annotated[str, Field(max_length=280)] = "",
        confidence: Annotated[int | None, Field(ge=0, le=100)] = None,
    ) -> dict[str, Any]:
        """Submit a signed proposal for a delivered turn. Retry only with identical fields."""
        return await tool_result(
            ctx.request_context.lifespan_context.submit(delivery_id, move, plan, threat, confidence)
        )

    @server.tool(annotations=SUBMIT)
    async def lounge_heartbeat(ctx: Context[LoungeFacade]) -> dict[str, Any]:
        """Refresh presence for the joined runner and return secret-free status."""
        return await tool_result(ctx.request_context.lifespan_context.heartbeat())

    if settings.allow_create:

        @server.tool(annotations=WRITE)
        async def lounge_create_game(
            ctx: Context[LoungeFacade],
            white_player_id: str | None = None,
            black_player_id: str | None = None,
            initial_time_ms: Annotated[int, Field(ge=100, le=86_400_000)] = 300_000,
            increment_ms: Annotated[int, Field(ge=0, le=60_000)] = 2_000,
        ) -> dict[str, Any]:
            """Start a game: use joined remote player IDs; null selects a human seat.

            This operator-enabled action starts clocks immediately. Use the Lounge UI
            to configure built-in provider or Stockfish seats. Creation is not retry-safe.
            """
            return await tool_result(
                ctx.request_context.lifespan_context.create_game(
                    white_player_id, black_player_id, initial_time_ms, increment_ms
                )
            )

    # Bare Context preserves SDK request state through resource argument validation.
    async def resource_game(game_id: str, ctx: Context) -> dict[str, Any]:
        try:
            return await ctx.request_context.lifespan_context.watch(game_id)
        except LoungeError as exc:
            raise ResourceError(str(exc)) from None
        except Exception:
            raise ResourceError("Lounge resource unavailable.") from None

    @server.resource("lounge://games/{game_id}", mime_type="application/json")
    async def game_state(game_id: str, ctx: Context) -> str:
        """Authoritative public game snapshot without legal-move or engine assistance."""
        return json.dumps(await resource_game(game_id, ctx))

    @server.resource("lounge://games/{game_id}/fen", mime_type="text/plain")
    async def game_fen(game_id: str, ctx: Context) -> str:
        """Current authoritative FEN."""
        return (await resource_game(game_id, ctx))["fen"]

    @server.resource("lounge://games/{game_id}/pgn", mime_type="application/x-chess-pgn")
    async def game_pgn(game_id: str, ctx: Context) -> str:
        """Current PGN for replay or export."""
        return (await resource_game(game_id, ctx))["pgn"]

    return server


def main() -> None:
    parser = argparse.ArgumentParser(description="Local stdio MCP bridge for AI Chess Lounge")
    parser.add_argument("--base-url", default=os.environ.get("LOUNGE_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--allow-create", action="store_true", help="Expose operator game creation")
    args = parser.parse_args()
    try:
        settings = Settings(
            base_url=args.base_url,
            allow_create=args.allow_create,
            pairing_id=os.environ.pop("LOUNGE_PAIRING_ID", ""),
            pairing_code=os.environ.pop("LOUNGE_PAIRING_CODE", ""),
        )
    except (ValueError, LoungeError):
        parser.error("Invalid local Lounge URL or incomplete pairing configuration.")
    create_server(settings).run(transport="stdio")


if __name__ == "__main__":
    main()
