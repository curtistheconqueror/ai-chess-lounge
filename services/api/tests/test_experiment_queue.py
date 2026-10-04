import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from lounge_api.adapters import AdapterRegistry, ScriptedPlayerAdapter
from lounge_api.experiment_queue import ExperimentQueue, QueueConflict
from lounge_api.experiments import ExperimentConfiguration, ExperimentService, SaveExperiment
from lounge_api.persistence import DatabaseStore
from test_experiments import configuration


async def setup(tmp_path, *, max_failures=3):
    url = f"sqlite+aiosqlite:///{tmp_path / 'queue.db'}"
    stores = [DatabaseStore(url), DatabaseStore(url)]
    for store in stores:
        await store.initialize()
    config = configuration()
    config["stops"] = {"max_failures": max_failures}
    service = ExperimentService(stores[0], AdapterRegistry([ScriptedPlayerAdapter()]))
    plan = await service.save(
        SaveExperiment(id=uuid4(), configuration=ExperimentConfiguration.model_validate(config))
    )
    queues = [ExperimentQueue(s) for s in stores]
    run_id = str(uuid4())
    await queues[0].create(plan["id"], run_id)
    return stores, queues, plan, run_id


def test_queue_persists_idempotent_jobs_and_serializes_claims(tmp_path):
    async def run():
        stores, queues, plan, run_id = await setup(tmp_path)
        now = datetime.now(UTC)
        try:
            first = await queues[0].snapshot(run_id)
            assert len(first["jobs"]) == 8
            assert await queues[1].create(plan["id"], run_id) == first
            with pytest.raises(QueueConflict):
                await queues[1].create(plan["id"], run_id, concurrency=2)
            assert await queues[1].claim(run_id, now=now) is None
            await queues[0].transition(run_id, "running", 0, now=now)
            claims = await asyncio.gather(*(q.claim(run_id, now=now) for q in queues))
            assert sum(c is not None for c in claims) == 1
            claim = next(c for c in claims if c)
            assert claim["id"] == first["jobs"][0]["id"]
            second = await queues[1].claim(run_id, now=now + timedelta(seconds=11))
            assert second["id"] == claim["id"]
            assert second["lease_token"] != claim["lease_token"]
            with pytest.raises(QueueConflict):
                await queues[0].finish(
                    claim["id"], claim["lease_token"], "1-0", now=now + timedelta(seconds=11)
                )
            await queues[1].finish(
                second["id"], second["lease_token"], "1-0", now=now + timedelta(seconds=11)
            )
            assert (await queues[0].snapshot(run_id))["jobs"][0]["result"] == "1-0"
        finally:
            for store in stores:
                await store.close()
        restarted = DatabaseStore(f"sqlite+aiosqlite:///{tmp_path / 'queue.db'}")
        try:
            assert (await ExperimentQueue(restarted).snapshot(run_id))["jobs"][0]["result"] == "1-0"
        finally:
            await restarted.close()

    asyncio.run(run())


def test_pause_cancel_revision_fence_and_original_deadline(tmp_path):
    async def run():
        stores, queues, _, run_id = await setup(tmp_path)
        now = datetime.now(UTC)
        try:
            started = await queues[0].transition(run_id, "running", 0, now=now)
            claim = await queues[0].claim(run_id, now=now)
            paused = await queues[1].transition(run_id, "paused", 1, now=now)
            with pytest.raises(QueueConflict):
                await queues[0].finish(claim["id"], claim["lease_token"], "1-0", now=now)
            assert await queues[0].claim(run_id, now=now) is None
            with pytest.raises(QueueConflict):
                await queues[0].transition(run_id, "running", 1, now=now)
            resumed = await queues[0].transition(run_id, "running", paused["revision"], now=now)
            assert resumed["deadline"] == started["deadline"]
            cancelled = await queues[1].transition(
                run_id, "cancelled", resumed["revision"], now=now
            )
            assert all(j["state"] == "cancelled" for j in cancelled["jobs"])
            with pytest.raises(QueueConflict):
                await queues[0].transition(run_id, "running", cancelled["revision"], now=now)
        finally:
            for store in stores:
                await store.close()

    asyncio.run(run())


def test_failure_stop_cancels_pending_and_late_results(tmp_path):
    async def run():
        stores, queues, _, run_id = await setup(tmp_path, max_failures=1)
        now = datetime.now(UTC)
        try:
            await queues[0].transition(run_id, "running", 0, now=now)
            claim = await queues[0].claim(run_id, now=now)
            await queues[0].finish(claim["id"], claim["lease_token"], "failed", now=now)
            stopped = await queues[1].snapshot(run_id)
            assert stopped["state"] == "stopped"
            assert stopped["jobs"][0]["state"] == "failed"
            assert all(j["state"] == "cancelled" for j in stopped["jobs"][1:])
            assert await queues[1].claim(run_id, now=now) is None
        finally:
            for store in stores:
                await store.close()

    asyncio.run(run())


def test_complete_every_job_and_expired_resume_rejected(tmp_path):
    async def run():
        stores, queues, plan, run_id = await setup(tmp_path)
        now = datetime.now(UTC)
        try:
            await queues[0].transition(run_id, "running", 0, now=now)
            for _ in range(8):
                claim = await queues[0].claim(run_id, now=now)
                await queues[0].finish(claim["id"], claim["lease_token"], "1/2-1/2", now=now)
            assert (await queues[1].snapshot(run_id))["state"] == "completed"
            other = str(uuid4())
            await queues[1].create(plan["id"], other)
            await queues[0].transition(other, "running", 0, now=now)
            await queues[0].transition(other, "paused", 1, now=now)
            with pytest.raises(QueueConflict):
                await queues[1].transition(other, "running", 2, now=now + timedelta(hours=2))
        finally:
            for store in stores:
                await store.close()

    asyncio.run(run())


def test_worker_completes_bounded_batch_with_real_match_ids(tmp_path):
    from lounge_api.experiment_worker import ExperimentWorker
    from lounge_api.manager import GameManager
    from test_manager import FakeEngine

    async def run():
        store = DatabaseStore(f"sqlite+aiosqlite:///{tmp_path / 'worker.db'}")
        manager = GameManager(engine=FakeEngine(), store=store, schedule_timeouts=False)
        await manager.start()
        worker = ExperimentWorker(manager)
        try:
            config = configuration()
            config["repetitions"] = 1
            config["stops"] = {"max_plies": 4}
            plan = await worker.plans.save(
                SaveExperiment(
                    id=uuid4(), configuration=ExperimentConfiguration.model_validate(config)
                )
            )
            run_id = str(uuid4())
            batch = await worker.queue.create(plan["id"], run_id, concurrency=2)
            await worker.control(run_id, "running", 0)
            worker.start()

            async def completed():
                while True:
                    state = await worker.queue.snapshot(run_id)
                    if state["state"] == "completed":
                        return state
                    await asyncio.sleep(0.05)

            done = await asyncio.wait_for(completed(), 10)
            assert len(done["jobs"]) == 4
            assert {j["id"] for j in done["jobs"]} == {j["id"] for j in batch["jobs"]}
            for job in done["jobs"]:
                game = await manager.snapshot(job["id"])
                assert game.lifecycle.value == "aborted"
                assert len(game.moves) == 4
                assert job["result"] == "limited"
            assert (await manager.snapshot(done["jobs"][2]["id"])).initial_fen != chess.STARTING_FEN
        finally:
            await worker.close()
            await manager.close()

    import chess

    asyncio.run(run())


def test_run_api_requires_explicit_start_and_keeps_no_auto_execution(client):
    plan = client.post(
        "/api/experiments", json={"id": str(uuid4()), "configuration": configuration()}
    ).json()
    run_id = str(uuid4())
    response = client.post(f"/api/experiments/{plan['id']}/runs", json={"id": run_id})
    assert response.status_code == 201
    assert response.json()["state"] == "ready"
    assert all(j["state"] == "queued" for j in response.json()["jobs"])
    cancelled = client.post(
        f"/api/experiment-runs/{run_id}/control",
        json={"target": "cancelled", "expected_revision": 0},
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["state"] == "cancelled"
    assert (
        client.post(
            f"/api/experiment-runs/{run_id}/control",
            json={"target": "running", "expected_revision": 0},
        ).status_code
        == 409
    )


def test_global_capacity_is_shared_across_runs(tmp_path):
    async def run():
        stores, queues, plan, first_id = await setup(tmp_path)
        now = datetime.now(UTC)
        try:
            ids = [first_id] + [str(uuid4()) for _ in range(5)]
            for rid in ids[1:]:
                await queues[0].create(plan["id"], rid)
            for rid in ids:
                await queues[0].transition(rid, "running", 0, now=now)
            claims = await asyncio.gather(
                *(queues[i % 2].claim(rid, now=now) for i, rid in enumerate(ids))
            )
            assert sum(c is not None for c in claims) == 4
            first = next(c for c in claims if c)
            await queues[0].finish(first["id"], first["lease_token"], "1-0", now=now)
            pending = ids[next(i for i, c in enumerate(claims) if c is None)]
            assert await queues[1].claim(pending, now=now) is not None
        finally:
            for store in stores:
                await store.close()

    asyncio.run(run())


def test_cross_worker_cancellation_fences_delayed_move(tmp_path):
    from lounge_api.experiment_worker import ExperimentWorker
    from lounge_api.manager import GameManager
    from test_manager import FakeEngine

    async def run():
        entered, release = asyncio.Event(), asyncio.Event()

        class SlowAdapter(ScriptedPlayerAdapter):
            async def choose_move(self, request, player):
                entered.set()
                await release.wait()
                return await super().choose_move(request, player)

        url = f"sqlite+aiosqlite:///{tmp_path / 'cancel.db'}"
        managers = [
            GameManager(
                engine=FakeEngine(),
                store=DatabaseStore(url),
                adapters=AdapterRegistry([SlowAdapter()]),
                schedule_timeouts=False,
            )
            for _ in range(2)
        ]
        for manager in managers:
            await manager.start()
        workers = [ExperimentWorker(m) for m in managers]
        try:
            plan = await workers[0].plans.save(
                SaveExperiment(
                    id=uuid4(),
                    configuration=ExperimentConfiguration.model_validate(configuration()),
                )
            )
            rid = str(uuid4())
            await workers[0].queue.create(plan["id"], rid)
            await workers[0].control(rid, "running", 0)
            workers[0].start()
            await asyncio.wait_for(entered.wait(), 3)
            before = await workers[1].queue.snapshot(rid)
            await workers[1].control(rid, "cancelled", before["revision"])
            release.set()
            await asyncio.sleep(0.1)
            game = await managers[1].snapshot(before["jobs"][0]["id"])
            assert game.moves == [] and game.lifecycle.value == "aborted"
            assert all(
                j["state"] == "cancelled" for j in (await workers[0].queue.snapshot(rid))["jobs"]
            )
        finally:
            release.set()
            for worker in workers:
                await worker.close()
            for manager in managers:
                await manager.close()

    asyncio.run(run())


def test_pause_resume_and_restart_reuses_original_match(tmp_path):
    from lounge_api.experiment_worker import ExperimentWorker
    from lounge_api.manager import GameManager
    from lounge_api.persistence import ExperimentJobRow
    from sqlalchemy import update
    from test_manager import FakeEngine

    async def run():
        url = f"sqlite+aiosqlite:///{tmp_path / 'restart.db'}"

        def manager():
            return GameManager(
                engine=FakeEngine(), store=DatabaseStore(url), schedule_timeouts=False
            )

        first = manager()
        await first.start()
        worker = ExperimentWorker(first)
        config = configuration()
        config.update(
            openings=[{"name": "Start", "moves": []}],
            repetitions=1,
            color_swap=False,
            stops={"max_plies": 8},
        )
        for entrant in config["entrants"]:
            entrant["player"]["settings"]["spectator_delay_ms"] = 200
        plan = await worker.plans.save(
            SaveExperiment(id=uuid4(), configuration=ExperimentConfiguration.model_validate(config))
        )
        rid = str(uuid4())
        original = await worker.queue.create(plan["id"], rid)
        started = await worker.control(rid, "running", 0)
        worker.start()
        job_id = original["jobs"][0]["id"]

        async def moved():
            while True:
                try:
                    game = await first.snapshot(job_id)
                    if game.moves:
                        return game
                except Exception:
                    pass
                await asyncio.sleep(0.02)

        await asyncio.wait_for(moved(), 3)
        paused = await worker.control(rid, "paused", started["revision"])
        game = await first.snapshot(job_id)
        assert game.lifecycle.value == "paused"
        ply = len(game.moves)
        await worker.close()
        await worker.control(rid, "running", paused["revision"])
        await first.close()
        second = manager()
        await second.start()
        worker2 = ExperimentWorker(second)
        try:
            async with second.store.sessions.begin() as session:
                await session.execute(
                    update(ExperimentJobRow)
                    .where(ExperimentJobRow.id == job_id)
                    .values(lease_expires_at=datetime.now(UTC) - timedelta(seconds=1))
                )
            worker2.start()

            async def done():
                while (await worker2.queue.snapshot(rid))["state"] != "completed":
                    await asyncio.sleep(0.05)

            await asyncio.wait_for(done(), 6)
            final = await second.snapshot(job_id)
            assert len(final.moves) == 8 and len(final.moves) >= ply
            assert (await worker2.queue.snapshot(rid))["deadline"] == started["deadline"]
            assert final.generation == 0
        finally:
            await worker2.close()
            await second.close()

    asyncio.run(run())


def test_provider_batch_requires_specific_authorization(tmp_path):
    from lounge_api.experiment_worker import ExperimentWorker
    from lounge_api.manager import GameManager
    from test_manager import FakeEngine

    class Provider(ScriptedPlayerAdapter):
        adapter_id = "openai"

        def capabilities(self, model):
            return {**super().capabilities(model), "connection_mode": "direct_api"}

    async def run():
        manager = GameManager(
            engine=FakeEngine(),
            store=DatabaseStore(f"sqlite+aiosqlite:///{tmp_path / 'auth.db'}"),
            adapters=AdapterRegistry([Provider()]),
            schedule_agents=False,
            schedule_timeouts=False,
        )
        await manager.start()
        worker = ExperimentWorker(manager)
        try:
            config = configuration()
            for entrant in config["entrants"]:
                entrant["player"].update(
                    adapter_id="openai",
                    provider="OpenAI",
                    connection_mode="direct_api",
                    settings={},
                )
            plan = await worker.plans.save(
                SaveExperiment(
                    id=uuid4(), configuration=ExperimentConfiguration.model_validate(config)
                )
            )
            rid = str(uuid4())
            await worker.queue.create(plan["id"], rid)
            with pytest.raises(ValueError, match="authorization"):
                await worker.control(rid, "running", 0)
            assert (await worker.queue.snapshot(rid))["state"] == "ready"
            assert (await worker.control(rid, "running", 0, allow_provider_calls=True))[
                "state"
            ] == "running"
            assert manager.games == {}  # Authorization alone does not bypass dispatch.
        finally:
            await worker.close()
            await manager.close()

    asyncio.run(run())


def test_run_deadline_stops_held_turn_without_late_move(tmp_path):
    from lounge_api.experiment_worker import ExperimentWorker
    from lounge_api.manager import GameManager
    from test_manager import FakeEngine

    async def run():
        entered = asyncio.Event()

        class Held(ScriptedPlayerAdapter):
            async def choose_move(self, request, player):
                entered.set()
                await asyncio.Event().wait()

        manager = GameManager(
            engine=FakeEngine(),
            store=DatabaseStore(f"sqlite+aiosqlite:///{tmp_path / 'deadline.db'}"),
            adapters=AdapterRegistry([Held()]),
            schedule_timeouts=False,
        )
        await manager.start()
        worker = ExperimentWorker(manager)
        try:
            config = configuration()
            config["stops"] = {"max_wall_time_ms": 1000}
            plan = await worker.plans.save(
                SaveExperiment(
                    id=uuid4(), configuration=ExperimentConfiguration.model_validate(config)
                )
            )
            rid = str(uuid4())
            original = await worker.queue.create(plan["id"], rid)
            await worker.control(rid, "running", 0)
            worker.start()
            await asyncio.wait_for(entered.wait(), 2)

            async def stopped():
                while True:
                    batch = await worker.queue.snapshot(rid)
                    game = await manager.snapshot(original["jobs"][0]["id"])
                    if batch["state"] == "stopped" and game.lifecycle.value == "aborted":
                        return game
                    await asyncio.sleep(0.05)

            game = await asyncio.wait_for(stopped(), 3)
            assert game.moves == []
            with pytest.raises(ValueError):
                await manager.reset(game.id)
            with pytest.raises(ValueError):
                await manager.adjudicate(game.id, "1-0")
        finally:
            await worker.close()
            await manager.close()

    asyncio.run(run())


def test_scripted_black_to_move_opening_uses_correct_script_offset(tmp_path):
    from lounge_api.experiment_worker import ExperimentWorker
    from lounge_api.manager import GameManager
    from test_manager import FakeEngine

    async def run():
        manager = GameManager(
            engine=FakeEngine(),
            store=DatabaseStore(f"sqlite+aiosqlite:///{tmp_path / 'black.db'}"),
            schedule_timeouts=False,
        )
        await manager.start()
        worker = ExperimentWorker(manager)
        try:
            config = configuration()
            config.update(
                openings=[{"name": "After e4", "moves": ["e2e4"]}],
                color_swap=False,
                repetitions=1,
                stops={"max_plies": 4},
            )
            config["entrants"][0]["player"]["settings"]["moves"] = ["g1f3", "f1c4"]
            config["entrants"][1]["player"]["settings"]["moves"] = ["e7e5", "b8c6"]
            plan = await worker.plans.save(
                SaveExperiment(
                    id=uuid4(), configuration=ExperimentConfiguration.model_validate(config)
                )
            )
            rid = str(uuid4())
            initial = await worker.queue.create(plan["id"], rid)
            await worker.control(rid, "running", 0)
            worker.start()

            async def done():
                while (await worker.queue.snapshot(rid))["state"] != "completed":
                    await asyncio.sleep(0.05)

            await asyncio.wait_for(done(), 5)
            game = await manager.snapshot(initial["jobs"][0]["id"])
            assert [m.uci for m in game.moves] == ["e7e5", "g1f3", "b8c6", "f1c4"]
        finally:
            await worker.close()
            await manager.close()

    asyncio.run(run())


@pytest.mark.parametrize("provider_failure", [False, True])
def test_reclaimed_uncertain_or_failed_turn_never_redispatches(tmp_path, provider_failure):
    from lounge_api.adapters import AdapterError
    from lounge_api.experiment_worker import ExperimentWorker
    from lounge_api.manager import GameManager
    from lounge_api.models import CreateGameRequest
    from lounge_api.persistence import ExperimentJobRow
    from lounge_api.player_protocol import PlayerConfiguration
    from sqlalchemy import update
    from test_manager import FakeEngine

    async def run():
        calls = []
        entered = asyncio.Event()

        class Interrupted(ScriptedPlayerAdapter):
            async def choose_move(self, request, player):
                calls.append(request.match_id)
                entered.set()
                if provider_failure:
                    raise AdapterError("simulated provider failure")
                await asyncio.Event().wait()

        url = f"sqlite+aiosqlite:///{tmp_path / 'uncertain.db'}"

        def make_manager():
            return GameManager(
                engine=FakeEngine(),
                store=DatabaseStore(url),
                adapters=AdapterRegistry([Interrupted()]),
                schedule_timeouts=False,
            )

        first = make_manager()
        await first.start()
        worker = ExperimentWorker(first)
        config = configuration()
        config.update(
            openings=[{"name": "Start", "moves": []}],
            repetitions=1,
            color_swap=False,
            stops={"max_failures": 1},
        )
        plan = await worker.plans.save(
            SaveExperiment(id=uuid4(), configuration=ExperimentConfiguration.model_validate(config))
        )
        rid = str(uuid4())
        await worker.queue.create(plan["id"], rid)
        await worker.control(rid, "running", 0)
        claim = await worker.queue.claim(rid, now=datetime.now(UTC))
        variants = {v["key"]: v["player"] for v in plan["variants"]}
        item = plan["schedule"][0]
        await first.create(
            CreateGameRequest(
                white_player=PlayerConfiguration.model_validate(variants[item["white"]]),
                black_player=PlayerConfiguration.model_validate(variants[item["black"]]),
            ),
            experiment_job=claim,
        )
        await asyncio.wait_for(entered.wait(), 3)
        if provider_failure:

            async def paused():
                while (await first.snapshot(claim["id"])).lifecycle.value != "paused":
                    await asyncio.sleep(0.02)

            await asyncio.wait_for(paused(), 3)
        await first.close()  # No queue completion: simulate crash before bookkeeping.
        second = make_manager()
        await second.start()
        worker2 = ExperimentWorker(second)
        try:
            async with second.store.sessions.begin() as session:
                await session.execute(
                    update(ExperimentJobRow)
                    .where(ExperimentJobRow.id == claim["id"])
                    .values(lease_expires_at=datetime.now(UTC) - timedelta(seconds=1))
                )
            worker2.start()

            async def settled():
                while (await worker2.queue.snapshot(rid))["state"] != "stopped":
                    await asyncio.sleep(0.02)

            await asyncio.wait_for(settled(), 3)
            assert calls == [claim["id"]]
            result = await worker2.queue.snapshot(rid)
            assert result["jobs"][0]["result"] == "failed"
            assert (await second.snapshot(claim["id"])).moves == []
        finally:
            await worker2.close()
            await second.close()

    asyncio.run(run())


def test_move_commit_requires_exact_current_experiment_claim(tmp_path):
    from copy import deepcopy

    from lounge_api.manager import GameManager
    from lounge_api.models import CreateGameRequest
    from lounge_api.persistence import ConcurrentGameUpdate, ExperimentJobRow
    from lounge_api.player_protocol import PlayerConfiguration
    from sqlalchemy import update
    from test_manager import FakeEngine

    async def run():
        stores, queues, plan, rid = await setup(tmp_path)
        manager = GameManager(
            engine=FakeEngine(), store=stores[0], schedule_agents=False, schedule_timeouts=False
        )
        try:
            await manager.start()
            await queues[0].transition(rid, "running", 0)
            old = await queues[0].claim(rid, now=datetime.now(UTC))
            variants = {v["key"]: v["player"] for v in plan["variants"]}
            item = plan["schedule"][0]
            game = await manager.create(
                CreateGameRequest(
                    white_player=PlayerConfiguration.model_validate(variants[item["white"]]),
                    black_player=PlayerConfiguration.model_validate(variants[item["black"]]),
                ),
                experiment_job=old,
            )
            tentative = deepcopy(game)
            move = tentative.apply_uci("e2e4", actor="scripted:white", now=datetime.now(UTC))
            async with stores[1].sessions.begin() as session:
                await session.execute(
                    update(ExperimentJobRow)
                    .where(ExperimentJobRow.id == old["id"])
                    .values(lease_expires_at=datetime.now(UTC) - timedelta(seconds=1))
                )
            new = await queues[1].claim(rid, now=datetime.now(UTC))
            assert new["id"] == old["id"]
            for token in [None, old["lease_token"]]:
                with pytest.raises(ConcurrentGameUpdate):
                    await stores[0].record_move(
                        tentative, move, [], expected_revision=game.revision, experiment_token=token
                    )
            assert (await stores[0].load_game(game.id)).moves == []
            await stores[0].record_move(
                tentative,
                move,
                [],
                expected_revision=game.revision,
                experiment_token=new["lease_token"],
            )
            assert len((await stores[0].load_game(game.id)).moves) == 1
        finally:
            await manager.close()
            await stores[1].close()

    asyncio.run(run())
