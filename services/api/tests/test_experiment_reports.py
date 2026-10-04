import asyncio
import csv
import hashlib
import io
import json
from datetime import UTC, datetime
from uuid import uuid4
from zipfile import ZipFile

import chess.pgn
import pytest
from lounge_api.experiment_reports import (
    HASH_FIELDS,
    ExperimentReports,
    ReportConflict,
    ReportTooLarge,
    csv_bytes,
)
from lounge_api.experiments import canonical_hash
from lounge_api.manager import GameManager
from lounge_api.models import CreateGameRequest
from lounge_api.persistence import ExperimentRow, MoveRow
from lounge_api.player_protocol import PlayerConfiguration, PlayerMoveMetadata
from sqlalchemy import select
from test_experiment_metrics import make_run
from test_experiments import configuration
from test_manager import FakeEngine


async def terminal_run(tmp_path, result="0-1", schema="1.0"):
    config = configuration()
    config.update(repetitions=1, color_swap=False)
    config["openings"] = [{"name": "Black starts", "moves": ["f2f3"]}]
    if schema == "2.0":
        config.update(schema_version="2.0", format="round_robin", anchor=None)
    store, plan, queue, rid = await make_run(tmp_path, config)
    manager = GameManager(
        engine=FakeEngine(), store=store, schedule_agents=False, schedule_timeouts=False
    )
    await manager.start()
    try:
        claim = await queue.claim(rid, now=datetime.now(UTC))
        profiles = {v["key"]: v["player"] for v in plan["variants"]}
        game = await manager.create(
            CreateGameRequest(
                white_player=PlayerConfiguration.model_validate(profiles[claim["white"]]),
                black_player=PlayerConfiguration.model_validate(profiles[claim["black"]]),
            ),
            experiment_job=claim,
            initial_fen=plan["schedule"][0]["initial_fen"],
        )
        for uci in ["e7e5", "g2g4", "d8h4"] if result == "0-1" else ["e7e5"]:
            revision = game.revision
            color = "white" if game.board.turn else "black"
            player = game.player_for_color(color)
            move = game.apply_uci(
                uci,
                actor=f"scripted:{color}",
                now=datetime.now(UTC),
                player_metadata=PlayerMoveMetadata(
                    player_id=player.player_id,
                    adapter_id="scripted",
                    provider="Reference",
                    model="deterministic-v1",
                    division="legal_assist",
                    latency_ms=1,
                    plan="PRIVATE_PLAN_SENTINEL",
                    threat="PRIVATE_THREAT_SENTINEL",
                ),
            )
            await store.record_move(
                game,
                move,
                [game.event("move.accepted", {"private": "PRIVATE_EVENT_SENTINEL"})],
                expected_revision=revision,
                experiment_token=claim["lease_token"],
            )
        if result == "cancelled":
            current = await queue.snapshot(rid)
            await queue.transition(rid, "cancelled", current["revision"])
        else:
            await queue.finish(claim["id"], claim["lease_token"], result, now=datetime.now(UTC))
        return manager, plan, queue, rid
    except BaseException:
        await manager.close()
        raise


@pytest.mark.parametrize("schema", ["1.0", "2.0"])
def test_bundle_preserves_hash_games_and_private_metadata_boundary(tmp_path, schema):
    async def run():
        manager, plan, queue, rid = await terminal_run(tmp_path, schema=schema)
        try:
            before = await queue.snapshot(rid)
            data = await ExperimentReports(manager.store).bundle(rid)
            with ZipFile(io.BytesIO(data)) as archive:
                files = {name: archive.read(name) for name in archive.namelist()}
            assert set(files) == {
                "manifest.json",
                "report.json",
                "competitors.csv",
                "games.csv",
                "moves.csv",
                "games.pgn",
                "README.txt",
                "checksums.json",
            }
            checksums = json.loads(files["checksums.json"])
            assert all(
                hashlib.sha256(files[name]).hexdigest() == value
                for name, value in checksums.items()
            )
            manifest = json.loads(files["manifest.json"])
            hashed = {key: manifest[key] for key in HASH_FIELDS}
            if schema == "2.0":
                hashed["tournament"] = manifest["tournament"]
            assert (
                canonical_hash(hashed)
                == plan["configuration_hash"]
                == manifest["configuration_hash"]
            )
            report = json.loads(files["report.json"])
            assert report["run"] == before
            assert report["metrics"]["configuration_hash"] == plan["configuration_hash"]
            pgn = chess.pgn.read_game(io.StringIO(files["games.pgn"].decode()))
            assert pgn.errors == []
            assert pgn.headers["SetUp"] == "1"
            assert pgn.headers["FEN"] == plan["schedule"][0]["initial_fen"]
            assert pgn.headers["Result"] == "0-1" and pgn.end().board().is_checkmate()
            assert pgn.headers["White"] == "A:default"
            assert pgn.headers["Black"] == "B:default"
            assert pgn.headers["ExperimentHash"] == plan["configuration_hash"]
            for value in files.values():
                assert b"PRIVATE_" not in value
            moves = list(csv.DictReader(io.StringIO(files["moves.csv"].decode())))
            assert [row["uci"] for row in moves] == ["e7e5", "g2g4", "d8h4"]
            competitors = list(csv.DictReader(io.StringIO(files["competitors.csv"].decode())))
            assert all(row["reported_cost_usd"] == "" for row in competitors)
            assert await queue.snapshot(rid) == before
        finally:
            await manager.close()

    asyncio.run(run())


@pytest.mark.parametrize("result", ["limited", "failed", "cancelled"])
def test_no_result_pgn_never_invents_a_chess_result(tmp_path, result):
    async def run():
        manager, _, _, rid = await terminal_run(tmp_path, result)
        try:
            with ZipFile(io.BytesIO(await ExperimentReports(manager.store).bundle(rid))) as archive:
                pgn = chess.pgn.read_game(io.StringIO(archive.read("games.pgn").decode()))
                report = json.loads(archive.read("report.json"))
            assert pgn.headers["Result"] == "*"
            assert len(list(pgn.mainline_moves())) == 1
            assert all(
                row["games"]["chess_completed"] == 0 for row in report["metrics"]["competitors"]
            )
        finally:
            await manager.close()

    asyncio.run(run())


def test_csv_formula_prefixes_do_not_change_numeric_or_json_values():
    values = ["=1+1", " \t@SUM(A1)", "\x00+1", "\r\n-1", "ordinary", None, 0, -0.5]
    output = csv_bytes(["value"], [{"value": value} for value in values])
    rows = list(csv.DictReader(io.StringIO(output.decode())))
    assert [r["value"] for r in rows] == ["'" + v for v in values[:4]] + [
        "ordinary",
        "",
        "0",
        "-0.5",
    ]
    assert values[0] == "=1+1"


def test_changed_snapshot_rejects_instead_of_exporting_mixed_versions(tmp_path, monkeypatch):
    async def run():
        manager, _, _, rid = await terminal_run(tmp_path)
        try:
            reports = ExperimentReports(manager.store)
            original = reports.markers
            calls = 0

            async def changed(ids):
                nonlocal calls
                calls += 1
                markers = await original(ids)
                return markers if calls == 1 else []

            monkeypatch.setattr(reports, "markers", changed)
            with pytest.raises(ReportConflict, match="changed"):
                await reports.bundle(rid)
        finally:
            await manager.close()

    asyncio.run(run())


@pytest.mark.parametrize("limit", ["MAX_EXPORT_MOVES", "MAX_EXPORT_BYTES"])
def test_export_limits_fail_explicitly_without_truncation(tmp_path, monkeypatch, limit):
    import lounge_api.experiment_reports as module

    async def run():
        manager, _, _, rid = await terminal_run(tmp_path)
        try:
            monkeypatch.setattr(module, limit, 1)
            with pytest.raises(ReportTooLarge):
                await ExperimentReports(manager.store).bundle(rid)
        finally:
            await manager.close()

    asyncio.run(run())


def test_bundle_http_requires_terminal_run_and_handles_unplayed_jobs(client):
    rid, eid = str(uuid4()), str(uuid4())
    assert client.get(f"/api/experiment-runs/{rid}/bundle").status_code == 404
    assert client.get("/api/experiment-runs/not-a-uuid/bundle").status_code == 422
    assert (
        client.post(
            "/api/experiments", json={"id": eid, "configuration": configuration()}
        ).status_code
        == 201
    )
    assert client.post(f"/api/experiments/{eid}/runs", json={"id": rid}).status_code == 201
    assert client.get(f"/api/experiment-runs/{rid}/bundle").status_code == 409
    cancelled = client.post(
        f"/api/experiment-runs/{rid}/control", json={"target": "cancelled", "expected_revision": 0}
    )
    assert cancelled.status_code == 200
    response = client.get(f"/api/experiment-runs/{rid}/bundle")
    assert response.status_code == 200 and response.headers["content-type"] == "application/zip"
    assert response.headers["cache-control"] == "no-store"
    with ZipFile(io.BytesIO(response.content)) as archive:
        assert archive.read("games.pgn") == b""
        assert len(list(csv.DictReader(io.StringIO(archive.read("games.csv").decode())))) == 8
        assert all(
            not row["has_game"] for row in json.loads(archive.read("report.json"))["run"]["jobs"]
        )


@pytest.mark.parametrize("corruption", ["manifest", "position", "uci"])
def test_inconsistent_saved_content_is_not_packaged(tmp_path, corruption):
    async def run():
        manager, plan, _, rid = await terminal_run(tmp_path)
        try:
            async with manager.store.sessions.begin() as session:
                if corruption == "manifest":
                    row = await session.get(ExperimentRow, plan["id"])
                    row.document = {**row.document, "game_count": 100}
                else:
                    row = await session.scalar(select(MoveRow).order_by(MoveRow.id))
                    if corruption == "uci":
                        row.uci = "bogus"
                    else:
                        row.fen = chess.STARTING_FEN
            with pytest.raises(ReportConflict):
                await ExperimentReports(manager.store).bundle(rid)
        finally:
            await manager.close()

    asyncio.run(run())
