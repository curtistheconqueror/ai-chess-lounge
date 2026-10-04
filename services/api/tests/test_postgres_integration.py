from __future__ import annotations

import asyncio
import os

import pytest
from lounge_api.manager import GameManager
from lounge_api.models import CreateGameRequest, OpponentKind, RunnerPairingCreate
from lounge_api.persistence import DatabaseStore, TurnLeaseUnavailable
from lounge_api.remote_runner import RemoteRunnerBroker, RunnerPairingError

POSTGRES_URL = os.getenv("TEST_POSTGRES_URL")

pytestmark = pytest.mark.skipif(
    not POSTGRES_URL,
    reason="TEST_POSTGRES_URL is required for PostgreSQL integration coverage.",
)


def test_postgres_concurrent_retry_and_turn_lease() -> None:
    async def run() -> None:
        assert POSTGRES_URL is not None
        first = GameManager(store=DatabaseStore(POSTGRES_URL), schedule_timeouts=False)
        second = GameManager(store=DatabaseStore(POSTGRES_URL), schedule_timeouts=False)
        await first.start()
        game = await first.create(CreateGameRequest(opponent=OpponentKind.HUMAN))
        await second.start()
        await second.get(game.id)
        try:
            accepted, replayed = await asyncio.gather(
                first.make_human_move(game.id, "e2e4", 0, "postgres-move-0001"),
                second.make_human_move(game.id, "e2e4", 0, "postgres-move-0001"),
            )
            events = await first.events(game.id)

            assert accepted.version == replayed.version == 1
            assert len(accepted.moves) == len(replayed.moves) == 1
            assert [event.type for event in events].count("move.accepted") == 1

            leases = await asyncio.gather(
                first.acquire_turn_lease(game.id, "runner:first", 1),
                second.acquire_turn_lease(game.id, "runner:second", 1),
                return_exceptions=True,
            )
            assert sum(not isinstance(result, Exception) for result in leases) == 1
            assert sum(isinstance(result, TurnLeaseUnavailable) for result in leases) == 1

            secret = b"postgres-stage-5a-test-secret-32-bytes"
            first_broker = RemoteRunnerBroker(first.store, secret=secret)
            second_broker = RemoteRunnerBroker(second.store, secret=secret)
            pairing = await first_broker.create_pairing(
                RunnerPairingCreate(
                    display_name="Postgres Remote",
                    provider="Test Runner",
                    model="remote-v1",
                )
            )
            claims = await asyncio.gather(
                first_broker.claim_pairing(pairing.pairing_id, pairing.pairing_code),
                second_broker.claim_pairing(pairing.pairing_id, pairing.pairing_code),
                return_exceptions=True,
            )
            assert sum(not isinstance(result, Exception) for result in claims) == 1
            assert sum(isinstance(result, RunnerPairingError) for result in claims) == 1
            await first_broker.close()
            await second_broker.close()
        finally:
            await first.close()
            await second.close()

    asyncio.run(run())


def test_postgres_runner_grant_concurrency_and_revocation() -> None:
    async def run() -> None:
        from datetime import UTC, datetime

        from lounge_api.persistence import RunnerTrustError

        assert POSTGRES_URL is not None
        first = DatabaseStore(POSTGRES_URL)
        second = DatabaseStore(POSTGRES_URL)
        await first.initialize()
        await second.initialize()
        broker = RemoteRunnerBroker(first, secret=b"postgres-stage5e-trust-secret-value")
        try:
            pairing = await broker.create_pairing(
                RunnerPairingCreate(display_name="PG trust", provider="Test", model="test")
            )
            creds = await broker.claim_pairing(pairing.pairing_id, pairing.pairing_code)
            outcomes = await asyncio.gather(
                first.reserve_runner_turn(creds.session_id, "pg-a", "white", now=datetime.now(UTC)),
                second.reserve_runner_turn(
                    creds.session_id, "pg-b", "white", now=datetime.now(UTC)
                ),
                return_exceptions=True,
            )
            assert sum(isinstance(item, dict) for item in outcomes) == 1
            assert sum(isinstance(item, RunnerTrustError) for item in outcomes) == 1
            grant = await first.runner_grant(creds.session_id)
            assert grant is not None
            await second.revoke_runner_session(creds.session_id, now=datetime.now(UTC))
            with pytest.raises(RunnerTrustError, match="revoked"):
                await first.check_runner_grant(
                    creds.session_id, str(grant["match_id"]), "white", now=datetime.now(UTC)
                )
        finally:
            await broker.close()
            await first.close()
            await second.close()

    asyncio.run(run())


def test_postgres_experiment_queue_claim_and_cancel_fences() -> None:
    from datetime import UTC, datetime
    from uuid import uuid4

    from lounge_api.adapters import AdapterRegistry, ScriptedPlayerAdapter
    from lounge_api.experiment_queue import ExperimentQueue, QueueConflict
    from lounge_api.experiments import ExperimentConfiguration, ExperimentService, SaveExperiment
    from test_experiments import configuration

    async def run():
        assert POSTGRES_URL is not None
        stores = [DatabaseStore(POSTGRES_URL), DatabaseStore(POSTGRES_URL)]
        for store in stores:
            await store.initialize()
        queues = [ExperimentQueue(store) for store in stores]
        try:
            plan = await ExperimentService(
                stores[0], AdapterRegistry([ScriptedPlayerAdapter()])
            ).save(
                SaveExperiment(
                    id=uuid4(),
                    configuration=ExperimentConfiguration.model_validate(configuration()),
                )
            )
            rid = str(uuid4())
            await queues[0].create(plan["id"], rid)
            now = datetime.now(UTC)
            await queues[0].transition(rid, "running", 0, now=now)
            claims = await asyncio.gather(*(q.claim(rid, now=now) for q in queues))
            assert sum(c is not None for c in claims) == 1
            claim = next(c for c in claims if c)
            await queues[1].transition(rid, "cancelled", 1, now=now)
            with pytest.raises(QueueConflict):
                await queues[0].finish(claim["id"], claim["lease_token"], "1-0", now=now)
            assert all(j["state"] == "cancelled" for j in (await queues[0].snapshot(rid))["jobs"])
        finally:
            for store in stores:
                await store.close()

    asyncio.run(run())
