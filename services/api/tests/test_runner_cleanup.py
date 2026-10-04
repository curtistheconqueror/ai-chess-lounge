from __future__ import annotations

import asyncio
import threading
import time

import pytest
from fastapi import WebSocketDisconnect
from lounge_api.models import RunnerPairingCreate
from lounge_api.persistence import DatabaseStore, RunnerSessionRow
from lounge_api.remote_runner import RemoteRunnerBroker
from sqlalchemy import event, text

SECRET = b"runner-cleanup-test-secret-is-32-bytes!"


def test_socket_cancellation_drains_database_poll_cleanup(tmp_path) -> None:
    async def run() -> None:
        store = DatabaseStore(f"sqlite+aiosqlite:///{tmp_path / 'socket-cleanup.db'}")
        broker = RemoteRunnerBroker(store, secret=SECRET)
        await store.initialize()
        pairing = await broker.create_pairing(
            RunnerPairingCreate(
                display_name="Cleanup test",
                provider="Independent",
                model="cleanup-test",
            )
        )
        credentials = await broker.claim_pairing(pairing.pairing_id, pairing.pairing_code)

        receive_started = asyncio.Event()
        query_started = asyncio.Event()
        close_started = asyncio.Event()
        finish_close = asyncio.Event()
        child_tasks: list[asyncio.Task] = []
        load_calls = 0
        original_load = store.load_runner_session

        class Socket:
            async def accept(self) -> None:
                pass

            async def receive_json(self) -> object:
                child_tasks.append(asyncio.current_task())
                receive_started.set()
                await asyncio.Event().wait()
                raise WebSocketDisconnect(code=1000)

        async def hold_query_open(session_id: str):
            nonlocal load_calls
            load_calls += 1
            if load_calls != 3:
                return await original_load(session_id)

            # socket_loop authenticates twice before starting next_turn. Hold the
            # third authentication inside a real DB session until the socket task
            # is cancelled, then hold close long enough to test cleanup draining.
            session = store.sessions()
            try:
                row = await session.get(RunnerSessionRow, session_id)
                assert row is not None
                query_started.set()
                child_tasks.append(asyncio.current_task())
                await asyncio.Event().wait()
                return store._runner_session_record(row)
            finally:
                close_started.set()
                await finish_close.wait()
                await session.close()

        store.load_runner_session = hold_query_open
        connection = asyncio.create_task(broker.socket_loop(Socket(), credentials.runner_token))
        try:
            await asyncio.wait_for(receive_started.wait(), timeout=2)
            await asyncio.wait_for(query_started.wait(), timeout=2)
            assert store.engine.sync_engine.pool.checkedout() == 1

            connection.cancel()
            await asyncio.wait_for(close_started.wait(), timeout=2)
            # ASGI servers can cancel a request again while the first cancellation
            # is already unwinding. Cleanup must still finish before socket_loop exits.
            connection.cancel()
            finish_close.set()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(connection, timeout=2)

            assert all(task.done() for task in child_tasks)
            assert store.engine.sync_engine.pool.checkedout() == 0
            assert credentials.session_id not in broker._connected
        finally:
            finish_close.set()
            if not connection.done():
                connection.cancel()
                await asyncio.gather(connection, return_exceptions=True)
            await broker.close()
            await store.close()

    asyncio.run(run())


def test_testclient_disconnect_during_heartbeat_returns_database_connection(client) -> None:
    manager = client.app.state.game_manager
    store = manager.store
    broker = manager.remote_runners
    pairing = client.post(
        "/api/runner-pairings",
        json={"display_name": "Cleanup test", "provider": "Independent", "model": "test"},
    ).json()
    credentials = client.post(
        f"/api/runner-pairings/{pairing['pairing_id']}/claim",
        json={"pairing_code": pairing["pairing_code"]},
    ).json()
    heartbeat_task = None
    db_call_entered = threading.Event()
    original_touch = store.touch_runner_session
    original_heartbeat = broker.heartbeat

    async def tracked_heartbeat(token):
        nonlocal heartbeat_task
        heartbeat_task = asyncio.current_task()
        return await original_heartbeat(token)

    def pause_in_database():
        db_call_entered.set()
        time.sleep(0.3)
        return 1

    def register_function(dbapi_connection, _record):
        dbapi_connection.run_async(
            lambda connection: connection.create_function("pause_for_test", 0, pause_in_database)
        )

    # Ensure new pooled connections get the test-only SQLite function. The delay
    # happens in the driver thread, so ASGI can cancel the in-flight query.
    client.portal.call(store.engine.dispose)
    event.listen(store.engine.sync_engine, "connect", register_function)

    async def hold_heartbeat_transaction(session_id: str, *, now):
        if asyncio.current_task() is not heartbeat_task:
            return await original_touch(session_id, now=now)
        async with store.sessions.begin() as session:
            await session.execute(text("SELECT pause_for_test()"))
            return True

    store.touch_runner_session = hold_heartbeat_transaction
    broker.heartbeat = tracked_heartbeat
    try:
        with client.websocket_connect(
            "/ws/runners", headers={"Authorization": f"Bearer {credentials['runner_token']}"}
        ) as websocket:
            websocket.send_json({"type": "heartbeat"})
            assert db_call_entered.wait(timeout=2)
            assert store.engine.sync_engine.pool.checkedout() >= 1
        assert store.engine.sync_engine.pool.checkedout() == 0
        assert credentials["session_id"] not in broker._connected
    finally:
        store.touch_runner_session = original_touch
        broker.heartbeat = original_heartbeat
        event.remove(store.engine.sync_engine, "connect", register_function)
