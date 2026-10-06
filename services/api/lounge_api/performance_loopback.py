"""Disposable loopback transport fixture; accepts no external endpoint or application DB."""

import asyncio
import json
import socket
from contextlib import contextmanager
from time import monotonic

import chess
import httpx
import uvicorn
from websockets.asyncio.client import connect

from .adapters import AdapterRegistry, ScriptedPlayerAdapter
from .main import create_app
from .manager import GameManager
from .performance import MAX_HTTP, MAX_SPECTATORS, distribution, fixture_database, together
from .persistence import DatabaseStore


class FixtureServer(uvicorn.Server):
    @contextmanager
    def capture_signals(self):
        # The test owns its task/socket, never process-global signal handlers.
        yield


async def read_snapshot(connection):
    message = json.loads(await connection.recv())
    assert message["type"] == "snapshot"
    return message["payload"]


async def loopback(root, backend, http_levels=(1, 8, 32), spectator_levels=(1, 10, 50, 100)):
    if (
        not http_levels
        or len(http_levels) > 4
        or any(type(n) is not int or not 1 <= n <= MAX_HTTP for n in http_levels)
        or not spectator_levels
        or len(spectator_levels) > 4
        or any(type(n) is not int or not 1 <= n <= MAX_SPECTATORS for n in spectator_levels)
    ):
        raise ValueError("Loopback schedule exceeds fixture bounds")
    async with fixture_database(root, backend) as url:
        manager = GameManager(
            store=DatabaseStore(url),
            adapters=AdapterRegistry([ScriptedPlayerAdapter()]),
            schedule_agents=False,
            schedule_timeouts=False,
        )
        app = create_app(manager)
        try:
            async with app.router.lifespan_context(app):
                return await _transport(app, backend, http_levels, spectator_levels)
        finally:
            try:
                await app.state.readiness.close()
            finally:
                try:
                    await app.state.readiness.worker.close()
                finally:
                    await manager.close()


async def _transport(app, backend, http_levels, spectator_levels):
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    task, server, connections = None, None, []
    result = {
        "backend": backend,
        "transport": "loopback_TCP_no_TLS_proxy_browser",
        "http": [],
        "spectators": [],
        "max_message_bytes": 1048576,
        "client_receive_queue_high_watermark_frames": 4,
        "client_application_messages_sent": 0,
    }
    try:
        listener.bind(("127.0.0.1", 0))
        listener.listen(128)
        listener.setblocking(False)
        port = listener.getsockname()[1]
        server = FixtureServer(
            uvicorn.Config(
                app,
                lifespan="off",
                access_log=False,
                log_level="error",
                log_config=None,
                ws="websockets-sansio",
                ws_max_size=1048576,
                ws_per_message_deflate=False,
                timeout_graceful_shutdown=5,
            )
        )
        task = asyncio.create_task(server.serve(sockets=[listener]))
        while not server.started:
            if task.done():
                await task
                raise AssertionError("Fixture server did not start")
            await asyncio.sleep(0.01)
        async with httpx.AsyncClient(
            base_url=f"http://127.0.0.1:{port}",
            trust_env=False,
            timeout=5,
            limits=httpx.Limits(max_connections=32, max_keepalive_connections=32),
        ) as client:
            while True:
                response = await client.get("/api/ready")
                if response.status_code == 200:
                    break
                await asyncio.sleep(0.01)
            for width in http_levels:
                latencies = []

                async def request(latencies=latencies):
                    started = monotonic()
                    assert (await client.get("/api/ready")).status_code == 200
                    latencies.append((monotonic() - started) * 1000)

                for _ in range(4):
                    await together(*(request() for _ in range(width)))
                result["http"].append({"concurrency": width, **distribution(latencies)})
            for count in spectator_levels:
                response = await client.post("/api/games", json={"opponent": "human"})
                assert response.status_code == 201
                gid, clients = response.json()["id"], []

                async def attach(clients=clients, gid=gid):
                    ws = await connect(
                        f"ws://127.0.0.1:{port}/ws/games/{gid}",
                        proxy=None,
                        open_timeout=5,
                        close_timeout=2,
                        ping_interval=None,
                        compression=None,
                        max_size=1048576,
                        max_queue=4,
                    )
                    clients.append(ws)
                    connections.append(ws)
                    assert (await read_snapshot(ws))["version"] == 0

                await together(*(attach() for _ in range(count)))
                board, moves = chess.Board(), ["e2e4", "e7e5", "g1f3", "b8c6"]
                commit_started = None
                for version, move in enumerate(moves):
                    if version == 3:
                        commit_started = monotonic()
                    request = {"move": move, "position_version": version}
                    headers = {"Idempotency-Key": f"fixture-move-{version:04}"}
                    accepted = await client.post(
                        f"/api/games/{gid}/moves", json=request, headers=headers
                    )
                    replayed = await client.post(
                        f"/api/games/{gid}/moves", json=request, headers=headers
                    )
                    assert accepted.status_code == replayed.status_code == 200
                    assert accepted.json()["version"] == replayed.json()["version"] == version + 1
                    board.push_uci(move)
                latencies = []

                async def observe(
                    ws,
                    board=board,
                    moves=moves,
                    latencies=latencies,
                    commit_started=commit_started,
                ):
                    last = 0
                    while last < 4:
                        snapshot = await read_snapshot(ws)
                        assert snapshot["version"] >= last
                        last = snapshot["version"]
                    assert snapshot["version"] == 4
                    assert snapshot["fen"] == board.fen()
                    assert [row["uci"] for row in snapshot["moves"]] == moves
                    latencies.append((monotonic() - commit_started) * 1000)

                await together(*(observe(ws) for ws in clients))
                events = (await client.get(f"/api/games/{gid}/events")).json()
                assert [e["sequence"] for e in events] == list(range(1, len(events) + 1))
                assert sum(e["type"] == "move.accepted" for e in events) == 4
                await together(*(ws.close() for ws in clients))
                async with connect(
                    f"ws://127.0.0.1:{port}/ws/games/{gid}",
                    proxy=None,
                    open_timeout=5,
                    close_timeout=2,
                    ping_interval=None,
                    compression=None,
                    max_size=1048576,
                    max_queue=4,
                ) as ws:
                    snapshot = await read_snapshot(ws)
                    assert snapshot["version"] == 4 and snapshot["fen"] == board.fen()
                while app.state.operations.active_websockets:
                    await asyncio.sleep(0.01)
                result["spectators"].append(
                    {
                        "connections": count,
                        "accepted_moves": 4,
                        "idempotent_replays": 4,
                        "last_request_start_to_final_snapshot_read_including_replay": distribution(
                            latencies
                        ),
                        "active_after_cleanup": 0,
                        "reconnect_verified": True,
                    }
                )
    finally:
        try:
            await asyncio.gather(*(ws.close() for ws in connections), return_exceptions=True)
        finally:
            if server is not None:
                server.should_exit = True
            try:
                if task is not None:
                    try:
                        await asyncio.wait_for(asyncio.shield(task), timeout=10)
                    except TimeoutError:
                        server.force_exit = True
                        task.cancel()
                        await asyncio.gather(task, return_exceptions=True)
            finally:
                listener.close()

    assert listener.fileno() == -1 and app.state.operations.active_websockets == 0
    result["listener_closed"] = True
    return result
