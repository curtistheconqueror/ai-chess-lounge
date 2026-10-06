import asyncio
import json

import pytest
from lounge_api import performance_loopback as fixture


def test_real_loopback_transport_replay_reconnect_and_listener_cleanup(tmp_path):
    async def run():
        baseline = set(asyncio.all_tasks())
        result = await fixture.loopback(tmp_path, "sqlite", (1, 8), (1, 10))
        await asyncio.sleep(0)
        assert not [t for t in asyncio.all_tasks() - baseline if not t.done()]
        return result

    result = asyncio.run(asyncio.wait_for(run(), timeout=20))
    assert result["listener_closed"]
    assert all(s["idempotent_replays"] == 4 for s in result["spectators"])
    assert all(s["active_after_cleanup"] == 0 for s in result["spectators"])
    assert "127.0.0.1" not in json.dumps(result)
    assert str(tmp_path) not in json.dumps(result)


def test_loopback_validation_failure_drains_sockets_server_worker_and_lifespan(
    tmp_path, monkeypatch
):
    apps, original = [], fixture.create_app

    def capture(manager):
        app = original(manager)
        apps.append(app)
        return app

    async def fail(connection):
        raise AssertionError("Injected generated snapshot validation failure")

    monkeypatch.setattr(fixture, "create_app", capture)
    monkeypatch.setattr(fixture, "read_snapshot", fail)

    async def run():
        baseline = set(asyncio.all_tasks())
        with pytest.raises(ExceptionGroup):
            await fixture.loopback(tmp_path, "sqlite", (1,), (10,))
        await asyncio.sleep(0)
        assert apps[0].state.operations.active_websockets == 0
        assert not apps[0].state.readiness.started
        assert not [t for t in asyncio.all_tasks() - baseline if not t.done()]

    asyncio.run(asyncio.wait_for(run(), timeout=20))


def test_invalid_loopback_schedule_opens_no_fixture_resources(tmp_path):
    with pytest.raises(ValueError):
        asyncio.run(fixture.loopback(tmp_path, "sqlite", (33,), (1,)))
    assert not list(tmp_path.iterdir())
