import asyncio
import json

import pytest
from lounge_api.performance import (
    benchmark,
    fixture_database,
    http_and_spectators,
    queue_and_database,
)


@pytest.mark.parametrize(
    "options",
    [
        {"http_levels": (33,)},
        {"http_levels": (True,)},
        {"http_levels": (1,) * 5},
        {"spectator_levels": (101,)},
        {"spectator_levels": ()},
        {"backends": ()},
        {"backends": ("production",)},
        {"backends": ("sqlite", "sqlite")},
    ],
)
def test_harness_rejects_unbounded_or_unsupported_schedules(tmp_path, options):
    with pytest.raises(ValueError):
        asyncio.run(benchmark(tmp_path, **options))
    assert list(tmp_path.iterdir()) == []


def test_postgres_fixture_refuses_non_ci_access(tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)

    async def run():
        async with fixture_database(tmp_path, "postgresql"):
            pytest.fail("Guard permitted a non-CI database")

    with pytest.raises(ValueError, match="Disposable CI"):
        asyncio.run(run())


def test_real_asgi_spectator_reconnect_and_queue_cleanup(tmp_path):
    async def run():
        baseline = set(asyncio.all_tasks())
        sockets = await http_and_spectators(tmp_path, "sqlite", (1, 8), (1, 10))
        queue = await queue_and_database(tmp_path, "sqlite")
        await asyncio.sleep(0)
        assert not [t for t in asyncio.all_tasks() - baseline if not t.done()]
        return sockets, queue

    sockets, queue = asyncio.run(run())
    assert all(s["active_after_cleanup"] == 0 for s in sockets["spectators"])
    assert all(s["reconnect_verified"] for s in sockets["spectators"])
    assert queue["restart_read_verified"] and queue["pause_cancel_fencing"]
    assert queue["max_racing_leases"] == 4
    encoded = json.dumps([sockets, queue])
    assert str(tmp_path) not in encoded
    assert "sqlite+aiosqlite" not in encoded
    assert "postgresql+asyncpg" not in encoded


def test_sibling_failure_cancels_and_drains_pending_work():
    from lounge_api.performance import together

    async def run():
        ready, cleaned = asyncio.Event(), asyncio.Event()

        async def pending():
            try:
                ready.set()
                await asyncio.Event().wait()
            finally:
                cleaned.set()

        async def fail():
            await ready.wait()
            raise RuntimeError("Generated fixture failure")

        with pytest.raises(ExceptionGroup):
            await together(pending(), fail())
        assert cleaned.is_set()

    asyncio.run(run())


def test_spectator_validation_failure_still_closes_app_and_sockets(tmp_path, monkeypatch):
    from lounge_api.performance import Spectator

    original = Spectator.snapshot
    seen = {}

    async def fail_after_initial(self):
        seen[self] = seen.get(self, 0) + 1
        if seen[self] > 1:
            raise AssertionError("Injected generated validation failure")
        return await original(self)

    monkeypatch.setattr(Spectator, "snapshot", fail_after_initial)

    async def run():
        baseline = set(asyncio.all_tasks())
        with pytest.raises(ExceptionGroup):
            await http_and_spectators(tmp_path, "sqlite", (1,), (10,))
        await asyncio.sleep(0)
        assert seen and all(item.task.done() for item in seen)
        assert not [t for t in asyncio.all_tasks() - baseline if not t.done()]

    asyncio.run(run())
