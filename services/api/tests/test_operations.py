import asyncio
import json
from time import monotonic
from types import SimpleNamespace
from uuid import UUID

from fastapi.testclient import TestClient
from lounge_api.main import create_app
from lounge_api.manager import GameManager
from lounge_api.operations import LocalOperations, Readiness
from lounge_api.persistence import DatabaseStore
from test_manager import FakeEngine


def test_local_request_summaries_use_templates_and_never_retain_inputs(tmp_path):
    app = create_app(
        GameManager(
            engine=FakeEngine(),
            store=DatabaseStore(f"sqlite+aiosqlite:///{tmp_path / 'ops.db'}"),
            schedule_agents=False,
        )
    )
    with TestClient(app) as client:
        created = client.post("/api/games", json={"opponent": "human"})
        gid = created.json()["id"]
        response = client.get(
            f"/api/games/{gid}?private=PRIVATE_QUERY_SENTINEL",
            headers={
                "x-request-id": "PRIVATE_ID_SENTINEL",
                "authorization": "Bearer PRIVATE_HEADER_SENTINEL",
            },
        )
        UUID(response.headers["x-request-id"])
        assert response.headers["x-request-id"] != "PRIVATE_ID_SENTINEL"
        client.get("/PRIVATE_PATH_SENTINEL")
        data = app.state.operations.snapshot()
        encoded = json.dumps(data)
        assert "PRIVATE_" not in encoded and gid not in encoded
        assert "/api/games/{game_id}" in encoded
        assert "<unmatched>" in encoded or "/{path:path}" in encoded
        for _ in range(110):
            client.get("/api/health")
        assert len(app.state.operations.snapshot()["recent"]) == 100


def test_operational_cardinality_and_snapshots_are_bounded():
    ops = LocalOperations()
    for index in range(1000):
        ops.record(
            {"method": "UNTRUSTED", "route": SimpleNamespace(path=f"/template/{index}")},
            200,
            1,
            str(index),
        )
    assert len(ops.snapshot()["http"]) <= 128
    assert len(ops.snapshot()["recent"]) == 100
    data = ops.snapshot()
    data["http"][0]["count"] = -1
    assert ops.snapshot()["http"][0]["count"] > 0


def test_readiness_response_requires_started_worker_and_bounded_database_probe():
    async def run():
        gate, invoked = asyncio.Event(), 0

        async def probe():
            nonlocal invoked
            invoked += 1
            await gate.wait()
            readiness.database_ok = True
            readiness.checked_at = monotonic()

        worker_task = asyncio.create_task(gate.wait())
        worker = SimpleNamespace(closed=False, task=worker_task, last_success_at=monotonic())
        manager = SimpleNamespace(engine=SimpleNamespace(available=False))
        readiness = Readiness(manager, worker, wait_seconds=0.01)
        readiness._probe = probe
        try:
            assert not (await readiness.check())["ok"]
            assert invoked == 0
            readiness.started = True
            results = await asyncio.gather(*[readiness.check() for _ in range(12)])
            assert invoked == 1 and all(not r["ok"] for r in results)
            assert not readiness.probe.cancelled()
            gate.set()
            await readiness.probe
            # The completed worker is deliberately unavailable, even with a good DB.
            await worker_task
            assert not (await readiness.check())["checks"]["worker"]
            worker.task = asyncio.create_task(asyncio.Event().wait())
            assert (await readiness.check())["ok"]
            assert not (await readiness.check(require_engine=True))["ok"]
            worker.last_success_at = monotonic() - 6
            assert not (await readiness.check())["ok"]
        finally:
            gate.set()
            worker.task.cancel()
            await asyncio.gather(worker.task, return_exceptions=True)
            await readiness.close()
        assert not (await readiness.check())["ok"]

    asyncio.run(run())


def test_failed_probe_is_sanitized_and_http_health_remains_liveness(client, monkeypatch):
    async def fail():
        client.app.state.readiness.database_ok = False
        client.app.state.readiness.checked_at = monotonic()

    monkeypatch.setattr(client.app.state.readiness, "_probe", fail)
    response = client.get("/api/ready")
    assert response.status_code == 503
    assert response.json()["checks"]["database"] is False
    assert response.headers["cache-control"] == "no-store"
    assert client.get("/api/health").status_code == 200


def test_probe_exception_details_are_never_exposed():
    class Engine:
        def connect(self):
            raise RuntimeError("PRIVATE_CONNECTION_URL_SENTINEL")

    async def run():
        manager = SimpleNamespace(
            store=SimpleNamespace(engine=Engine()), engine=SimpleNamespace(available=True)
        )
        worker = SimpleNamespace(closed=True, task=None, last_success_at=None)
        readiness = Readiness(manager, worker)
        readiness.started = True
        try:
            data = await readiness.check()
            assert not data["ok"] and "PRIVATE_" not in json.dumps(data)
        finally:
            await readiness.close()

    asyncio.run(run())


def test_ready_and_websocket_activity_do_not_change_match_state(tmp_path):
    import httpx

    async def run():
        manager = GameManager(
            engine=FakeEngine(),
            store=DatabaseStore(f"sqlite+aiosqlite:///{tmp_path / 'ready.db'}"),
            schedule_agents=False,
        )
        app = create_app(manager)
        async with app.router.lifespan_context(app):
            worker = app.state.readiness.worker
            async with asyncio.timeout(2):
                while worker.last_success_at is None:
                    await asyncio.sleep(0.01)
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://fixture"
            ) as client:
                responses = await asyncio.gather(*[client.get("/api/ready") for _ in range(32)])
                assert all(response.status_code == 200 for response in responses)
                assert len({r.headers["x-request-id"] for r in responses}) == 32
                assert await manager.store.load_recoverable_games() == []
                assert len(app.state.operations.snapshot()["recent"]) == 32
        assert not app.state.readiness.started

    asyncio.run(run())

    app = create_app(
        GameManager(
            engine=FakeEngine(),
            store=DatabaseStore(f"sqlite+aiosqlite:///{tmp_path / 'ws.db'}"),
            schedule_agents=False,
        )
    )
    with TestClient(app) as client:
        gid = client.post("/api/games", json={"opponent": "human"}).json()["id"]
        with client.websocket_connect(f"/ws/games/{gid}") as socket:
            assert socket.receive_json()["type"] == "snapshot"
            assert app.state.operations.snapshot()["websockets"] == {"active": 1, "opened": 1}
        assert app.state.operations.snapshot()["websockets"] == {"active": 0, "opened": 1}
