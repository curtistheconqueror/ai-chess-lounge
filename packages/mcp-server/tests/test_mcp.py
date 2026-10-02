from __future__ import annotations

import asyncio
import json
import os
import sys
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

import httpx
import pytest
from lounge_api.main import create_app
from lounge_api.manager import GameManager
from lounge_api.persistence import DatabaseStore
from lounge_mcp.facade import LoungeFacade, Settings
from lounge_mcp.server import create_server
from mcp import Client
from mcp.client.stdio import StdioServerParameters


async def call(client: Client, name: str, **arguments):
    result = await client.call_tool(name, arguments)
    assert not result.is_error, result.content
    return result.structured_content


@asynccontextmanager
async def arena():
    with TemporaryDirectory() as directory:
        manager = GameManager(store=DatabaseStore(f"sqlite+aiosqlite:///{directory}/mcp.db"))
        app = create_app(manager)
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8000"
            ) as http:
                yield manager, http


async def paired(http, division="legal_assist", allow_create=False):
    pairing = (
        await http.post(
            "/api/runner-pairings",
            json={
                "display_name": "MCP Agent",
                "provider": "Independent",
                "model": "test",
                "division": division,
                "move_timeout_ms": 20_000,
            },
        )
    ).json()
    settings = Settings(
        pairing_id=pairing["pairing_id"],
        pairing_code=pairing["pairing_code"],
        allow_create=allow_create,
    )
    facade = LoungeFacade(settings, http_client=http)
    return Client(create_server(settings, facade=facade)), facade, pairing


def test_two_mcp_agents_complete_game_and_export():
    async def run():
        async with arena() as (manager, http), AsyncExitStack() as stack:
            white, wf, wp = await paired(http, allow_create=True)
            black, bf, bp = await paired(http)
            await stack.enter_async_context(white)
            await stack.enter_async_context(black)
            w = await call(white, "lounge_join")
            assert await call(white, "lounge_join") == w
            b = await call(black, "lounge_join")
            game = await call(
                white,
                "lounge_create_game",
                white_player_id=w["player"]["player_id"],
                black_player_id=b["player"]["player_id"],
            )
            assert "legal_moves" not in game
            secrets = [
                wp["pairing_code"],
                bp["pairing_code"],
                wf.runner().credentials.runner_token,
                wf.runner().credentials.signing_key,
                bf.runner().credentials.runner_token,
                bf.runner().credentials.signing_key,
            ]
            transcript = [w, b, game]
            for ply, (agent, move) in enumerate(
                [
                    (white, "f2f3"),
                    (black, "e7e5"),
                    (white, "g2g4"),
                    (black, "d8h4"),
                ],
                start=1,
            ):
                turn = await call(agent, "lounge_next_turn", wait_ms=1000)
                assert turn["pending"]
                assert move in turn["request"]["legal_moves"]
                # A host must be able to watch while the arbiter awaits its move.
                # Previously the writer lock blocked this until the turn timed out.
                async with asyncio.timeout(2):
                    thinking = await call(agent, "lounge_watch", game_id=game["id"])
                assert len(thinking["moves"]) == ply - 1
                assert thinking["fen"] == turn["request"]["fen"]
                receipt = await call(
                    agent,
                    "lounge_submit_move",
                    delivery_id=turn["delivery_id"],
                    move=move,
                    plan="Public plan",
                )
                assert receipt["accepted"]
                duplicate = await call(
                    agent,
                    "lounge_submit_move",
                    delivery_id=turn["delivery_id"],
                    move=move,
                    plan="Public plan",
                )
                assert duplicate["duplicate"]
                conflict = await agent.call_tool(
                    "lounge_submit_move",
                    {"delivery_id": turn["delivery_id"], "move": move, "plan": "Changed plan"},
                )
                assert conflict.is_error
                async with asyncio.timeout(10):
                    while True:
                        snapshot = await call(agent, "lounge_watch", game_id=game["id"])
                        if len(snapshot["moves"]) == ply:
                            break
                        await asyncio.sleep(0.01)
                transcript.extend([turn, receipt, duplicate, snapshot])
            assert snapshot["result"] == "0-1"
            assert snapshot["lifecycle"] == "completed"
            fen = await white.read_resource(f"lounge://games/{game['id']}/fen")
            pgn = await white.read_resource(f"lounge://games/{game['id']}/pgn")
            state = await white.read_resource(f"lounge://games/{game['id']}")
            assert fen.contents[0].text == snapshot["fen"]
            assert "Qh4#" in pgn.contents[0].text
            assert "legal_moves" not in json.loads(state.contents[0].text)
            transcript.extend([fen.model_dump(mode="json"), pgn.model_dump(mode="json")])
            transcript.extend(e.model_dump(mode="json") for e in await manager.events(game["id"]))
            assert all(secret not in json.dumps(transcript) for secret in secrets)

    asyncio.run(run())


def test_pure_reasoning_and_invalid_stale_proposals_keep_server_authority():
    async def run():
        async with arena() as (_, http):
            client, facade, _ = await paired(http, division="pure_reasoning", allow_create=True)
            async with client:
                joined = await call(client, "lounge_join")
                game = await call(
                    client, "lounge_create_game", white_player_id=joined["player"]["player_id"]
                )
                turn = await call(client, "lounge_next_turn", wait_ms=1000)
                assert turn["request"]["legal_moves"] is None
                assert "legal_moves" not in await call(client, "lounge_watch", game_id=game["id"])
                wrong = await client.call_tool(
                    "lounge_submit_move", {"delivery_id": str(uuid4()), "move": "e2e4"}
                )
                assert wrong.is_error
                await http.post(f"/api/games/{game['id']}/pause")
                stale = await client.call_tool(
                    "lounge_submit_move", {"delivery_id": turn["delivery_id"], "move": "e2e4"}
                )
                assert stale.is_error
                snapshot = await call(client, "lounge_watch", game_id=game["id"])
                assert snapshot["moves"] == []
                assert snapshot["lifecycle"] == "paused"
                assert not facade.settings.pairing_code

    asyncio.run(run())


def test_illegal_move_is_not_committed():
    async def run():
        async with arena() as (_, http):
            client, _, _ = await paired(http, allow_create=True)
            async with client:
                joined = await call(client, "lounge_join")
                game = await call(
                    client, "lounge_create_game", white_player_id=joined["player"]["player_id"]
                )
                turn = await call(client, "lounge_next_turn", wait_ms=1000)
                # Legal UCI shape, illegal chess move: the authoritative manager rejects it.
                await call(
                    client, "lounge_submit_move", delivery_id=turn["delivery_id"], move="e2e5"
                )
                async with asyncio.timeout(10):
                    while True:
                        snapshot = await call(client, "lounge_watch", game_id=game["id"])
                        if snapshot["lifecycle"] == "paused":
                            break
                        await asyncio.sleep(0.01)
                assert snapshot["moves"] == []

    asyncio.run(run())


def test_discovery_permissions_validation_and_secret_safe_errors():
    async def run():
        secret = "server-response-must-not-reach-model"

        def handler(request):
            return httpx.Response(500, json={"detail": secret})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            settings = Settings(pairing_id=str(uuid4()), pairing_code=secret)
            facade = LoungeFacade(settings, http_client=http)
            async with Client(create_server(settings, facade=facade)) as client:
                tools = {tool.name: tool for tool in (await client.list_tools()).tools}
                assert "lounge_create_game" not in tools
                assert tools["lounge_watch"].annotations.read_only_hint
                assert not tools["lounge_submit_move"].annotations.read_only_hint
                assert "pairing_code" not in json.dumps(
                    [t.model_dump(mode="json") for t in tools.values()]
                )
                for name, args in [
                    ("lounge_join", {}),
                    ("lounge_join", {}),
                    ("lounge_watch", {"game_id": str(uuid4())}),
                    ("lounge_watch", {"game_id": "../../api/health"}),
                    ("lounge_next_turn", {"wait_ms": 25001}),
                ]:
                    result = await client.call_tool(name, args)
                    assert result.is_error
                    assert secret not in result.model_dump_json()
                assert secret not in repr(settings)

    asyncio.run(run())


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com",
        "http://127.0.0.1@evil.test",
        "http://localhost/api",
        "http://localhost?token=x",
    ],
)
def test_nonlocal_or_ambiguous_targets_rejected(url):
    with pytest.raises(ValueError):
        Settings(base_url=url)


def test_real_stdio_process_discovers_tools_and_resources():
    async def run():
        root = Path(__file__).resolve().parents[3]
        env = {
            "PYTHONPATH": os.pathsep.join(
                [
                    str(root / "packages/mcp-server/src"),
                    str(root / "packages/runner-sdk-python/src"),
                ]
            )
        }
        async with Client(
            StdioServerParameters(command=sys.executable, args=["-m", "lounge_mcp.server"], env=env)
        ) as client:
            names = {t.name for t in (await client.list_tools()).tools}
            assert "lounge_watch" in names
            assert "lounge_create_game" not in names
            templates = await client.list_resource_templates()
            assert len(templates.resource_templates) == 3
            result = await client.call_tool("lounge_join")
            assert result.is_error

    asyncio.run(run())
