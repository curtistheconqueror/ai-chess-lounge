import asyncio
from copy import deepcopy
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from lounge_api.adapters import AdapterRegistry, ScriptedPlayerAdapter
from lounge_api.experiment_queue import ExperimentQueue
from lounge_api.experiments import ExperimentService, SaveExperiment, parse_configuration
from lounge_api.persistence import DatabaseStore
from lounge_api.tournaments import resolve_tournament, tournament_report
from test_experiments import configuration, service


def tournament(format_name="round_robin", count=4):
    config = configuration()
    config.update(
        schema_version="2.0",
        format=format_name,
        anchor=None,
        openings=[{"name": "Start", "moves": []}],
        repetitions=1,
        color_swap=False,
    )
    first = config["entrants"][0]
    config["entrants"] = [{**deepcopy(first), "key": chr(65 + i)} for i in range(count)]
    return config


def test_legacy_configuration_hash_is_unchanged():
    plan = service().preview(parse_configuration(configuration()))
    assert (
        plan["configuration_hash"]
        == "697179e86d2bf01114006195d3052bab46bd5f318b6cfd5ee9e2fbc714f63a1b"
    )
    assert "tournament" not in plan


def test_tournament_formats_hashes_and_variant_competitors():
    config = tournament()
    plan = service().preview(parse_configuration(config))
    assert plan["game_count"] == 6
    assert len(plan["tournament"]["series"]) == 6
    assert len({frozenset((g["white"], g["black"])) for g in plan["schedule"]}) == 6
    config.update(format="gauntlet", anchor="B:default")
    gauntlet = service().preview(parse_configuration(config))
    assert gauntlet["game_count"] == 3
    assert all("B:default" in (g["white"], g["black"]) for g in gauntlet["schedule"])
    assert plan["configuration_hash"] != gauntlet["configuration_hash"]
    config = tournament(count=2)
    config["entrants"][0]["efforts"] = ["fast", "deep"]

    class EffortAdapter(ScriptedPlayerAdapter):
        def capabilities(self, model):
            return {**super().capabilities(model), "effort_levels": ["fast", "deep"]}

    effort_service = ExperimentService(
        DatabaseStore("sqlite+aiosqlite:///:memory:"), AdapterRegistry([EffortAdapter()])
    )
    variants = effort_service.preview(parse_configuration(config))
    assert variants["game_count"] == 3  # Same entrant's effort variants can compete in v2.
    assert any(
        g["white"].startswith("A:") and g["black"].startswith("A:") for g in variants["schedule"]
    )


@pytest.mark.parametrize("change", ["anchor", "extra_anchor", "field", "oversized"])
def test_invalid_tournament_rejected(change):
    config = tournament()
    if change == "anchor":
        config.update(format="gauntlet", anchor="missing")
    elif change == "extra_anchor":
        config["anchor"] = "A:default"
    elif change == "field":
        config = tournament("knockout", count=3)
    else:
        config.update(
            repetitions=20,
            color_swap=True,
            openings=[{"name": str(i), "moves": []} for i in range(16)],
        )
    with pytest.raises(ValueError):
        service().preview(parse_configuration(config))


def test_knockout_resolves_only_decisive_complete_series():
    plan = service().preview(parse_configuration(tournament("knockout")))
    assert plan["game_count"] == 3
    assert plan["schedule"][2]["white"] == "winner:s1"
    jobs = [{"number": i, "state": "queued", "result": None} for i in range(1, 4)]
    opponents, blocked, _ = resolve_tournament(plan, jobs)
    assert set(opponents) == {1, 2} and not blocked
    jobs[0].update(state="completed", result="1-0")
    jobs[1].update(state="completed", result="0-1")
    opponents, blocked, series = resolve_tournament(plan, jobs)
    assert opponents[3] == ("A:default", "D:default") and not blocked
    assert series[-1]["state"] == "pending"
    jobs[2].update(state="completed", result="0-1")
    report = tournament_report(plan, jobs, "completed")
    assert report["champion"] == "D:default"
    assert report["status"] == "completed"
    for result in ["1/2-1/2", "limited", "failed"]:
        bad = deepcopy(jobs)
        bad[0].update(state="failed" if result == "failed" else "completed", result=result)
        bad[2].update(state="queued", result=None)
        opponents, blocked, series = resolve_tournament(plan, bad)
        assert 3 in blocked and 3 not in opponents
        assert series[-1]["winner"] is None
        assert tournament_report(plan, bad, "stopped")["status"] == "unresolved"


def test_color_swapped_series_aggregates_scores_without_draw_tiebreak():
    config = tournament("knockout", 2)
    config["color_swap"] = True
    plan = service().preview(parse_configuration(config))
    jobs = [{"number": i, "state": "completed", "result": "1-0"} for i in [1, 2]]
    assert tournament_report(plan, jobs, "completed")["champion"] is None
    jobs[1]["result"] = "0-1"
    report = tournament_report(plan, jobs, "completed")
    assert report["champion"] == "A:default"
    assert report["series"][0]["score"] == [2, 0]


def test_standings_exclude_failures_and_mixed_pool_ratings():
    plan = service().preview(parse_configuration(tournament()))
    jobs = [
        {"number": g["number"], "state": "completed", "result": "limited"} for g in plan["schedule"]
    ]
    jobs[0]["result"] = "1-0"
    report = tournament_report(plan, jobs, "completed")
    rows = {r["key"]: r for r in report["standings"]}
    assert rows["A:default"]["wins"] == 1 and rows["B:default"]["losses"] == 1
    assert rows["A:default"]["rating"] == 1512 and rows["B:default"]["rating"] == 1488
    assert rows["A:default"]["no_results"] == 2
    assert sum(r["played"] for r in rows.values()) == 2
    # The read model is also robust to a manifest containing an exhibition pairing.
    mixed = deepcopy(plan)
    mixed["variants"][1]["player"]["division"] = "engine_assisted"
    mixed_rows = tournament_report(mixed, jobs, "completed")["standings"]
    assert all(r["rating"] == 1500 and r["rated_games"] == 0 for r in mixed_rows)
    assert tournament_report(plan, list(reversed(jobs)), "completed") == report


def test_knockout_queue_waits_for_winners_and_blocks_unresolved_descendants(tmp_path):
    async def run():
        store = DatabaseStore(f"sqlite+aiosqlite:///{tmp_path / 'bracket.db'}")
        plans = ExperimentService(store, AdapterRegistry([ScriptedPlayerAdapter()]))
        queue = ExperimentQueue(store)
        try:
            for tied in [False, True]:
                plan = await plans.save(
                    SaveExperiment(
                        id=uuid4(), configuration=parse_configuration(tournament("knockout"))
                    )
                )
                rid = str(uuid4())
                await queue.create(plan["id"], rid, concurrency=4)
                await queue.transition(rid, "running", 0)
                first = await queue.claim(rid, now=datetime.now(UTC))
                second = await queue.claim(rid, now=datetime.now(UTC))
                assert first["number"] == 1 and second["number"] == 2
                assert await queue.claim(rid, now=datetime.now(UTC)) is None
                await queue.finish(
                    first["id"],
                    first["lease_token"],
                    "1/2-1/2" if tied else "1-0",
                    now=datetime.now(UTC),
                )
                await queue.finish(
                    second["id"], second["lease_token"], "0-1", now=datetime.now(UTC)
                )
                finals = await asyncio.gather(
                    queue.claim(rid, now=datetime.now(UTC)),
                    queue.claim(rid, now=datetime.now(UTC)),
                )
                assert sum(item is not None for item in finals) == (0 if tied else 1)
                final = next((item for item in finals if item), None)
                if tied:
                    assert final is None
                    snapshot = await queue.snapshot(rid)
                    assert snapshot["state"] == "stopped"
                    assert snapshot["jobs"][2]["state"] == "blocked"
                    assert snapshot["report"]["champion"] is None
                else:
                    assert (final["white"], final["black"]) == ("A:default", "D:default")
                    await queue.finish(
                        final["id"], final["lease_token"], "0-1", now=datetime.now(UTC)
                    )
                    assert (await queue.snapshot(rid))["report"]["champion"] == "D:default"
        finally:
            await store.close()

    asyncio.run(run())


def test_v2_preview_save_and_run_api(client):
    config = tournament("gauntlet")
    config["anchor"] = "A:default"
    preview = client.post("/api/experiments/preview", json=config)
    assert preview.status_code == 200
    assert preview.json()["game_count"] == 3
    eid = str(uuid4())
    saved = client.post("/api/experiments", json={"id": eid, "configuration": config})
    assert saved.status_code == 201
    assert saved.json()["configuration"]["schema_version"] == "2.0"
    batch = client.post(f"/api/experiments/{eid}/runs", json={"id": str(uuid4())})
    assert batch.status_code == 201
    assert batch.json()["report"]["format"] == "gauntlet"
    assert all(r["rated_games"] == 0 for r in batch.json()["report"]["standings"])


def test_knockout_worker_creates_final_with_actual_winners(tmp_path):
    from lounge_api.experiment_worker import ExperimentWorker
    from lounge_api.manager import GameManager
    from test_manager import FakeEngine

    class MateAdapter(ScriptedPlayerAdapter):
        async def choose_move(self, request, player):
            script = ["f2f3", "g2g4"] if request.color == "white" else ["e7e5", "d8h4"]
            return await super().choose_move(
                request,
                player.model_copy(update={"settings": {**player.settings, "moves": script}}),
            )

    async def run():
        manager = GameManager(
            engine=FakeEngine(),
            store=DatabaseStore(f"sqlite+aiosqlite:///{tmp_path / 'play-bracket.db'}"),
            adapters=AdapterRegistry([MateAdapter()]),
            schedule_timeouts=False,
        )
        await manager.start()
        worker = ExperimentWorker(manager)
        try:
            plan = await worker.plans.save(
                SaveExperiment(
                    id=uuid4(), configuration=parse_configuration(tournament("knockout"))
                )
            )
            rid = str(uuid4())
            await worker.queue.create(plan["id"], rid, concurrency=2)
            await worker.control(rid, "running", 0)
            worker.start()

            async def completed():
                while (await worker.queue.snapshot(rid))["state"] != "completed":
                    await asyncio.sleep(0.03)

            await asyncio.wait_for(completed(), 5)
            snapshot = await worker.queue.snapshot(rid)
            assert snapshot["report"]["champion"] == "D:default"
            assert len({j["id"] for j in snapshot["jobs"]}) == 3
            assert all(j["result"] == "0-1" for j in snapshot["jobs"])
            final = await manager.snapshot(snapshot["jobs"][2]["id"])
            assert final.white_player.player_id == "B"
            assert final.black_player.player_id == "D"
            assert len(final.moves) == 4
            assert sum(r["played"] for r in snapshot["report"]["standings"]) == 6
        finally:
            await worker.close()
            await manager.close()

    asyncio.run(run())


def test_round_robin_draw_is_completed_and_rated():
    plan = service().preview(parse_configuration(tournament(count=2)))
    report = tournament_report(
        plan, [{"number": 1, "state": "completed", "result": "1/2-1/2"}], "completed"
    )
    assert report["status"] == "completed"
    assert report["series"][0]["state"] == "completed"
    assert all(
        r["draws"] == 1 and r["rated_games"] == 1 and r["points"] == 0.5 and r["rating"] == 1500
        for r in report["standings"]
    )
