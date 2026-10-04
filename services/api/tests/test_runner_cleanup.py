from __future__ import annotations

import asyncio

import pytest
from fastapi import WebSocketDisconnect
from lounge_api.models import RunnerPairingCreate
from lounge_api.persistence import DatabaseStore, RunnerSessionRow
from lounge_api.remote_runner import RemoteRunnerBroker

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
