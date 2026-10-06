import asyncio
import json
from datetime import UTC, datetime
from math import log, sqrt
from uuid import uuid4

import pytest
from lounge_api.adapters import AdapterRegistry, ScriptedPlayerAdapter
from lounge_api.experiment_metrics import ExperimentMetrics, effort_response, opening_bound
from lounge_api.experiment_queue import ExperimentQueue
from lounge_api.experiments import ExperimentService, SaveExperiment, parse_configuration
from lounge_api.persistence import DatabaseStore
from test_experiments import configuration
from test_tournaments import tournament


async def make_run(tmp_path, config, adapters=None, *, database_url=None):
    store = DatabaseStore(database_url or f"sqlite+aiosqlite:///{tmp_path / str(uuid4())}.db")
    plans = ExperimentService(store, adapters or AdapterRegistry([ScriptedPlayerAdapter()]))
    plan = await plans.save(SaveExperiment(id=uuid4(), configuration=parse_configuration(config)))
    queue = ExperimentQueue(store)
    rid = str(uuid4())
    await queue.create(plan["id"], rid)
    await queue.transition(rid, "running", 0)
    return store, plan, queue, rid


async def settle(queue, rid, first_result="1-0"):
    count = 0
    while claim := await queue.claim(rid, now=datetime.now(UTC)):
        await queue.finish(
            claim["id"],
            claim["lease_token"],
            first_result if count == 0 else "1-0",
            now=datetime.now(UTC),
        )
        count += 1


def test_conditional_bound_is_conservative_and_does_not_claim_certainty():
    assert opening_bound([]) is None and opening_bound([1]) is None
    assert opening_bound([0, 1])["low"] == 0
    result = opening_bound([1] * 16)
    assert result["low"] == pytest.approx(1 - sqrt(log(40) / 32))
    assert result["high"] == 1 and result["low"] < 1


def test_completed_scores_group_repetitions_and_colors_by_opening(tmp_path):
    async def run():
        reports = []
        for repetitions in [1, 3]:
            config = configuration()
            config["repetitions"] = repetitions
            store, plan, queue, rid = await make_run(tmp_path, config)
            try:
                await settle(queue, rid)
                report = await ExperimentMetrics(store).get(rid)
                assert report["configuration_hash"] == plan["configuration_hash"]
                reports.append(report)
                for row in report["competitors"]:
                    assert row["strength"]["score_rate"] == 0.5
                    assert row["strength"]["opening_blocks"] == 2
                    assert row["strength"]["interval"] is not None
                    assert row["efficiency"]["usage"]["estimated_cost_usd"]["total"] is None
                    assert row["efficiency"]["latency_ms"]["mean"] is None
                    assert row["games"]["chess_completed"] == 4 * repetitions
            finally:
                await store.close()
        assert (
            reports[0]["competitors"][0]["strength"]["interval"]
            == reports[1]["competitors"][0]["strength"]["interval"]
        )

    asyncio.run(run())


@pytest.mark.parametrize(
    "condition", ["same_fen", "failure", "limited", "pending", "mixed", "knockout"]
)
def test_confidence_is_suppressed_when_conditions_do_not_support_it(tmp_path, condition):
    async def run():
        config = configuration()
        config["repetitions"] = 1
        if condition == "same_fen":
            config["openings"][1]["moves"] = []
        elif condition == "mixed":
            config["entrants"][1]["player"]["division"] = "engine_assisted"
        elif condition == "knockout":
            config.update(schema_version="2.0", format="knockout", anchor=None)
        store, _, queue, rid = await make_run(tmp_path, config)
        try:
            if condition != "pending":
                await settle(
                    queue, rid, {"failure": "failed", "limited": "limited"}.get(condition, "1-0")
                )
            report = await ExperimentMetrics(store).get(rid)
            for row in report["competitors"]:
                assert row["strength"]["interval"] is None
                assert row["strength"]["interval_unavailable_reason"]
                if condition in {"failure", "limited"}:
                    assert row["games"]["chess_completed"] == 3
                    assert row["games"]["failed" if condition == "failure" else "limited"] == 1
        finally:
            await store.close()

    asyncio.run(run())


def test_paired_effort_delta_requires_matching_complete_conditions():
    rows = {"a": {"key": "a", "entrant": "A"}, "b": {"key": "b", "entrant": "A"}}
    cohorts = {"a": {}, "b": {}}
    for opening in ["fen1", "fen2"]:
        cohorts["a"][("opponent", opening, 1, 0)] = [0]
        cohorts["b"][("opponent", opening, 1, 0)] = [1]
    report = effort_response(rows, cohorts, False, False)[0]
    assert report["score_delta"] == 1 and report["matched_blocks"] == 2
    assert report["interval"]["high"] == 1
    assert report["interval"]["low"] == pytest.approx(1 - 2 * sqrt(log(40) / 4))
    cohorts["b"][("opponent", "fen2", 1, 0)] = [None]
    report = effort_response(rows, cohorts, False, False)[0]
    assert report["score_delta"] is None and report["interval"] is None
    cohorts["b"][("different", "fen3", 1, 1)] = [1]
    assert effort_response(rows, cohorts, False, False)[0]["interval"] is None


def test_accepted_telemetry_has_coverage_and_correct_black_opening_attribution(tmp_path):
    from lounge_api.manager import GameManager
    from lounge_api.models import CreateGameRequest
    from lounge_api.player_protocol import PlayerConfiguration, PlayerMoveMetadata, UsageMetrics
    from test_manager import FakeEngine

    class EffortAdapter(ScriptedPlayerAdapter):
        def capabilities(self, model):
            return {**super().capabilities(model), "effort_levels": ["fast", "deep"]}

    async def run():
        config = tournament(count=2)
        config["openings"] = [{"name": "Black starts", "moves": ["e2e4"]}]
        config["entrants"][0]["efforts"] = ["fast", "deep"]
        adapters = AdapterRegistry([EffortAdapter()])
        store, plan, queue, rid = await make_run(tmp_path, config, adapters)
        manager = GameManager(
            engine=FakeEngine(),
            store=store,
            adapters=adapters,
            schedule_agents=False,
            schedule_timeouts=False,
        )
        await manager.start()
        try:
            claim = await queue.claim(rid, now=datetime.now(UTC))
            assert (claim["white"], claim["black"]) == ("A:fast", "A:deep")
            profiles = {v["key"]: v["player"] for v in plan["variants"]}
            game = await manager.create(
                CreateGameRequest(
                    white_player=PlayerConfiguration.model_validate(profiles[claim["white"]]),
                    black_player=PlayerConfiguration.model_validate(profiles[claim["black"]]),
                ),
                experiment_job=claim,
                initial_fen=plan["schedule"][0]["initial_fen"],
            )
            for color, uci, latency, usage, effort in [
                ("black", "e7e5", 120, UsageMetrics(), "deep"),
                (
                    "white",
                    "g1f3",
                    200,
                    UsageMetrics(input_tokens=0, output_tokens=5, estimated_cost_usd=0),
                    "fast",
                ),
            ]:
                before = game.revision
                move = game.apply_uci(
                    uci,
                    actor=f"scripted:{color}",
                    now=datetime.now(UTC),
                    player_metadata=PlayerMoveMetadata(
                        player_id="A",
                        adapter_id="scripted",
                        provider="Reference",
                        model="deterministic-v1",
                        effort=effort,
                        division="legal_assist",
                        latency_ms=latency,
                        usage=usage,
                        attempt=2,
                        plan="private-test-sentinel",
                        threat="private-test-sentinel",
                    ),
                )
                await store.record_move(
                    game,
                    move,
                    [game.event("move.accepted", {})],
                    expected_revision=before,
                    experiment_token=claim["lease_token"],
                )
            await manager._pause_for_invalid_proposal(
                game, game.revision, game.black_player, "illegal_move"
            )
            report = await ExperimentMetrics(store).get(rid)
            assert "private-test-sentinel" not in json.dumps(report)
            rows = {r["key"]: r for r in report["competitors"]}
            fast, deep = rows["A:fast"], rows["A:deep"]
            assert fast["efficiency"]["latency_ms"]["mean"] == 200
            assert deep["efficiency"]["latency_ms"]["p95"] == 120
            assert fast["efficiency"]["usage"]["estimated_cost_usd"] == {
                "total": 0,
                "observed_moves": 1,
                "missing_moves": 0,
            }
            assert deep["efficiency"]["usage"]["estimated_cost_usd"] == {
                "total": None,
                "observed_moves": 0,
                "missing_moves": 1,
            }
            assert fast["efficiency"]["retries_observed"] == 1
            assert deep["reliability"]["illegal_move_events"] == 1
            assert fast["reliability"]["agent_failure_events"] == 0
        finally:
            await manager.close()

    asyncio.run(run())


def test_metrics_endpoint_is_read_only_and_reports_missing_run(client):
    assert client.get(f"/api/experiment-runs/{uuid4()}/metrics").status_code == 404
    eid, rid = str(uuid4()), str(uuid4())
    saved = client.post("/api/experiments", json={"id": eid, "configuration": configuration()})
    assert saved.status_code == 201
    created = client.post(f"/api/experiments/{eid}/runs", json={"id": rid}).json()
    metrics = client.get(f"/api/experiment-runs/{rid}/metrics")
    assert metrics.status_code == 200
    assert metrics.json()["run_state"] == "ready"
    assert client.get(f"/api/experiment-runs/{rid}").json() == created
    assert all(row["games"]["started"] == 0 for row in metrics.json()["competitors"])
