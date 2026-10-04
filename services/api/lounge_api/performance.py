"""Bounded generated-fixture benchmarks; no live DB, provider or network target option."""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import platform
import resource
import sqlite3
import subprocess
import tempfile
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic
from uuid import uuid4

import chess
import httpx
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from . import __version__
from .adapters import AdapterRegistry, ScriptedPlayerAdapter
from .engine import EngineFailure, StockfishService
from .experiment_queue import QueueConflict
from .experiment_reports import ExperimentReports
from .experiment_worker import ExperimentWorker
from .experiments import ExperimentConfiguration, SaveExperiment
from .main import create_app
from .manager import GameManager
from .models import CreateGameRequest
from .persistence import DatabaseStore
from .player_protocol import PlayerConfiguration

MAX_SECONDS, MAX_HTTP, MAX_SPECTATORS = 60, 32, 100


def distribution(values):
    ordered = sorted(values)

    def percentile(q):
        return ordered[max(0, math.ceil(len(ordered) * q) - 1)] if ordered else None

    return {
        "samples": len(values),
        "p50_ms": percentile(0.5),
        "p95_ms": percentile(0.95),
        "max_ms": max(values) if values else None,
    }


def machine():
    def read(path):
        try:
            return Path(path).read_text().strip()
        except OSError:
            return None

    try:
        node = subprocess.run(
            ["node", "--version"], capture_output=True, text=True, timeout=2, check=True
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        node = None
    cpu = next(
        (
            line.split(":", 1)[1].strip()
            for line in (read("/proc/cpuinfo") or "").splitlines()
            if line.startswith("model name")
        ),
        platform.machine(),
    )
    mem = next(
        (
            line.split(":", 1)[1].strip()
            for line in (read("/proc/meminfo") or "").splitlines()
            if line.startswith("MemTotal:")
        ),
        None,
    )
    return {
        "os": platform.system(),
        "architecture": platform.machine(),
        "cpu": cpu,
        "logical_cpus": os.cpu_count(),
        "host_memory": mem,
        "cgroup_cpu_max": read("/sys/fs/cgroup/cpu.max"),
        "cgroup_memory_max": read("/sys/fs/cgroup/memory.max"),
        "python": platform.python_version(),
        "node": node,
        "sqlite": sqlite3.sqlite_version,
    }


def source_sha():
    if os.getenv("GITHUB_SHA"):
        return os.environ["GITHUB_SHA"]
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=Path(__file__).parent,
            capture_output=True,
            text=True,
            check=True,
            timeout=2,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def resources():
    usage = resource.getrusage(resource.RUSAGE_SELF)
    return {
        "process_peak_rss_kib": usage.ru_maxrss,
        "process_cpu_seconds": usage.ru_utime + usage.ru_stime,
        "all_reaped_children_peak_rss_kib": resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,
    }


@asynccontextmanager
async def fixture_database(root, backend):
    if backend == "sqlite":
        yield f"sqlite+aiosqlite:///{root / (uuid4().hex + '.db')}"
        return
    if backend != "postgresql":
        raise ValueError("Unsupported fixture backend.")
    if os.getenv("GITHUB_ACTIONS") != "true" or os.getenv("TEST_POSTGRES_RESTORE") != "1":
        raise ValueError("Disposable CI PostgreSQL infrastructure is required.")
    url = make_url(os.environ["TEST_POSTGRES_URL"])
    if (
        url.host not in {"127.0.0.1", "localhost"}
        or url.database != "lounge_test"
        or url.username != "lounge"
        or url.port != 5432
        or url.query
    ):
        raise ValueError("Only the declared loopback CI test service is supported.")
    admin, created = create_async_engine(url, isolation_level="AUTOCOMMIT"), False
    name = "performance_fixture_" + uuid4().hex
    try:
        async with admin.connect() as connection:
            await connection.execute(text(f'CREATE DATABASE "{name}"'))
            created = True
        yield url.set(database=name).render_as_string(hide_password=False)
    finally:
        try:
            if created:
                async with admin.connect() as connection:
                    await connection.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        finally:
            await admin.dispose()


async def together(*calls):
    # Cancel/drain siblings on failure before disposing their database or app.
    async with asyncio.TaskGroup() as group:
        tasks = [group.create_task(call) for call in calls]
    return [task.result() for task in tasks]


class Spectator:
    def __init__(self, app, game_id):
        self.app, self.game_id = app, game_id
        self.incoming, self.outgoing = asyncio.Queue(maxsize=4), asyncio.Queue(maxsize=4)
        self.task = None
        self.high_water = 0

    async def start(self):
        scope = {
            "type": "websocket",
            "asgi": {"version": "3.0"},
            "scheme": "ws",
            "path": f"/ws/games/{self.game_id}",
            "raw_path": b"",
            "root_path": "",
            "query_string": b"",
            "headers": [],
            "subprotocols": [],
            "client": ("fixture", 1),
            "server": ("fixture", 80),
        }

        async def send(message):
            await self.outgoing.put(message)
            self.high_water = max(self.high_water, self.outgoing.qsize())

        self.task = asyncio.create_task(self.app(scope, self.incoming.get, send))
        await self.incoming.put({"type": "websocket.connect"})
        assert (await self.outgoing.get())["type"] == "websocket.accept"
        return await self.snapshot()

    async def snapshot(self):
        message = await self.outgoing.get()
        assert message["type"] == "websocket.send"
        data = json.loads(message["text"])
        assert data["type"] == "snapshot"
        return data["payload"]

    async def close(self):
        if self.task is None or self.task.done():
            if self.task is not None:
                await self.task
            return
        await self.incoming.put({"type": "websocket.disconnect", "code": 1000})
        # Consume bounded output so send backpressure cannot prevent disconnect.
        while not self.task.done():
            while not self.outgoing.empty():
                self.outgoing.get_nowait()
            await asyncio.sleep(0.01)
        await self.task


async def http_and_spectators(root, backend, http_levels, spectator_levels):
    async with fixture_database(root, backend) as url:
        manager = GameManager(
            store=DatabaseStore(url),
            adapters=AdapterRegistry([ScriptedPlayerAdapter()]),
            schedule_agents=False,
            schedule_timeouts=False,
        )
        app = create_app(manager)
        result = {"backend": backend, "transport": "in_process_ASGI", "http": [], "spectators": []}
        async with app.router.lifespan_context(app):
            worker = app.state.readiness.worker
            while worker.last_success_at is None:
                await asyncio.sleep(0.01)
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://fixture"
            ) as client:
                for width in http_levels:
                    elapsed = []

                    async def request(elapsed=elapsed):
                        started = monotonic()
                        response = await client.get("/api/ready")
                        assert response.status_code == 200
                        elapsed.append((monotonic() - started) * 1000)

                    started = monotonic()
                    for _ in range(4):
                        await together(*(request() for _ in range(width)))
                    result["http"].append(
                        {
                            "concurrency": width,
                            "elapsed_seconds": monotonic() - started,
                            "status_200": len(elapsed),
                            **distribution(elapsed),
                        }
                    )
                assert await manager.store.load_recoverable_games() == []
                for count in spectator_levels:
                    game = await manager.create(CreateGameRequest(opponent="human"))
                    clients = [Spectator(app, game.id) for _ in range(count)]
                    elapsed, started = [], monotonic()
                    try:
                        snapshots = await together(*(item.start() for item in clients))
                        assert all(item["version"] == 0 for item in snapshots)
                        moves = ["e2e4", "e7e5", "g1f3", "b8c6"]
                        board = chess.Board()
                        for version, uci in enumerate(moves):
                            await manager.make_human_move(game.id, uci, version)
                            board.push_uci(uci)

                        async def observe(item, moves=moves, board=board, elapsed=elapsed):
                            last, started_observe = 0, monotonic()
                            while last < len(moves):
                                snapshot = await item.snapshot()
                                assert snapshot["version"] >= last
                                last = snapshot["version"]
                            assert snapshot["fen"] == board.fen()
                            assert [row["uci"] for row in snapshot["moves"]] == moves
                            elapsed.append((monotonic() - started_observe) * 1000)

                        await together(*(observe(item) for item in clients))
                        events = await manager.events(game.id)
                        assert [e.sequence for e in events] == list(range(1, len(events) + 1))
                        assert sum(e.type == "move.accepted" for e in events) == len(moves)
                        await together(*(item.close() for item in clients))
                        reconnect = Spectator(app, game.id)
                        clients.append(reconnect)
                        snapshot = await reconnect.start()
                        assert snapshot["version"] == 4 and snapshot["fen"] == board.fen()
                    finally:
                        outcomes = await asyncio.gather(
                            *(item.close() for item in clients), return_exceptions=True
                        )
                        errors = [e for e in outcomes if isinstance(e, BaseException)]
                        if errors:
                            raise BaseExceptionGroup("Spectator cleanup failed", errors)
                    assert app.state.operations.active_websockets == 0
                    result["spectators"].append(
                        {
                            "connections": count,
                            "accepted_moves": len(moves),
                            "elapsed_seconds": monotonic() - started,
                            "final_snapshot_wait": distribution(elapsed),
                            "channel_capacity": 4,
                            "channel_high_water": max(c.high_water for c in clients),
                            "active_after_cleanup": 0,
                            "reconnect_verified": True,
                            "protocol": "coalesced_versioned_snapshots_and_separate_durable_events",
                        }
                    )
                data = app.state.operations.snapshot()
                assert len(data["recent"]) <= 100 and len(data["http"]) <= 128
                result["retained_timing_records"] = len(data["recent"])
                result["retained_metric_keys"] = len(data["http"])
                async with manager.store.engine.connect() as connection:
                    result["database_version"] = (
                        await connection.scalar(text("SELECT version()"))
                        if backend == "postgresql"
                        else sqlite3.sqlite_version
                    )
        assert not app.state.readiness.started
        return result


def configuration():
    players = [
        PlayerConfiguration(
            adapter_id="scripted",
            display_name=key,
            provider="Lounge Fixture",
            model="deterministic-v1",
            connection_mode="local",
            division="legal_assist",
            settings={"spectator_delay_ms": 0},
        )
        for key in ["A", "B"]
    ]
    return ExperimentConfiguration.model_validate(
        {
            "name": "Generated benchmark",
            "entrants": [{"key": str(i), "player": player} for i, player in enumerate(players)],
            "openings": [
                {"name": "Start", "moves": []},
                {"name": "Open", "moves": ["e2e4", "e7e5"]},
            ],
            "repetitions": 2,
            "stops": {"max_plies": 4, "max_wall_time_ms": 60000},
        }
    )


async def queue_and_database(root, backend):
    async with fixture_database(root, backend) as url:
        manager = GameManager(
            store=DatabaseStore(url),
            adapters=AdapterRegistry([ScriptedPlayerAdapter()]),
            schedule_timeouts=False,
        )
        worker = ExperimentWorker(manager)
        observer = DatabaseStore(url)
        result = {"backend": backend, "worker_processes": 1, "queue": []}
        try:
            await manager.start()
            plan = await worker.plans.save(
                SaveExperiment(id=uuid4(), configuration=configuration())
            )
            # Race eight claimants against the same DB, then verify pause/cancel fences.
            rid = str(uuid4())
            await worker.queue.create(plan["id"], rid, concurrency=4)
            initial = await worker.queue.transition(rid, "running", 0)
            from .experiment_queue import ExperimentQueue

            another = ExperimentQueue(observer)
            claims = await together(
                *[
                    (worker.queue if i % 2 else another).claim(rid, now=datetime.now(UTC))
                    for i in range(8)
                ]
            )
            leased = [claim for claim in claims if claim is not None]
            assert len(leased) == 4 and len({c["id"] for c in leased}) == 4
            paused = await another.transition(rid, "paused", initial["revision"])
            assert await worker.queue.claim(rid, now=datetime.now(UTC)) is None
            try:
                await worker.queue.finish(
                    leased[0]["id"], leased[0]["lease_token"], "limited", now=datetime.now(UTC)
                )
            except QueueConflict:
                pass
            else:
                raise AssertionError("Pause did not fence an old claim.")
            resumed = await another.transition(rid, "running", paused["revision"])
            assert resumed["deadline"] == initial["deadline"]
            await another.transition(rid, "cancelled", resumed["revision"])
            result["claimants"] = 8
            result["max_racing_leases"] = 4
            result["pause_cancel_fencing"] = True
            worker.start()
            for concurrency in [1, 4]:
                rid = str(uuid4())
                prepared = await worker.queue.create(plan["id"], rid, concurrency)
                await worker.control(rid, "running", prepared["revision"])
                started, timings, maximum = monotonic(), [], 0
                while True:
                    sampled = monotonic()
                    run = await another.snapshot(rid)
                    timings.append((monotonic() - sampled) * 1000)
                    maximum = max(maximum, sum(j["state"] == "leased" for j in run["jobs"]))
                    assert maximum <= concurrency
                    if run["state"] == "completed":
                        break
                    await asyncio.sleep(0.02)
                moves = 0
                assert len(run["jobs"]) == plan["game_count"] == 8
                assert len({j["id"] for j in run["jobs"]}) == 8
                for job in run["jobs"]:
                    game = await observer.load_game(job["id"])
                    assert game is not None and job["result"] == "limited"
                    assert len(game.moves) == game.version == 4
                    board = chess.Board(game.initial_fen)
                    for move in game.moves:
                        board.push_uci(move.uci)
                    assert board.fen() == game.board.fen()
                    events = await observer.list_events(game.id)
                    assert sum(e.type == "move.accepted" for e in events) == game.version
                    moves += game.version
                archive = await ExperimentReports(observer).bundle(rid)
                result["queue"].append(
                    {
                        "concurrency": concurrency,
                        "games": 8,
                        "accepted_moves": moves,
                        "elapsed_seconds": monotonic() - started,
                        "observed_max_leases": maximum,
                        "snapshot_latency": distribution(timings),
                        "bundle_bytes": len(archive),
                        "persisted_move_event_alignment": True,
                        "results": "limited_no_result_not_draw",
                    }
                )
            result["configuration_hash"] = plan["configuration_hash"]
        finally:
            try:
                await worker.close()
            finally:
                try:
                    await manager.close()
                finally:
                    await observer.close()
        reopened = DatabaseStore(url)
        try:
            assert (await reopened.load_game(run["jobs"][0]["id"])).version == 4
            result["restart_read_verified"] = True
        finally:
            await reopened.close()
        return result


async def engine_workload():
    playing, analysis = StockfishService(), StockfishService()
    if not playing.available:
        return {"status": "skipped", "reason": "Stockfish unavailable; no fake engine evidence"}
    board, original = chess.Board(), chess.Board().fen()
    elapsed = []
    try:
        started = monotonic()
        for engine in [playing, analysis]:
            await engine._ensure_started()
            engine._engine.configure({"Threads": 1, "Hash": 16})
        startup_ms = (monotonic() - started) * 1000

        async def play():
            started = monotonic()
            move = await playing.choose_move(board, target_elo=1600, move_time_ms=30)
            assert chess.Move.from_uci(move.uci) in board.legal_moves
            elapsed.append((monotonic() - started) * 1000)

        async def analyse():
            value = await analysis.analyse_position(board, analysis_time_ms=30)
            assert chess.Move.from_uci(value.best_move) in board.legal_moves

        await together(*[play() for _ in range(4)], *[analyse() for _ in range(4)])
        assert board.fen() == original and playing._lock is not analysis._lock
        stopped = playing._engine
        stopped.close()
        await asyncio.to_thread(stopped.returncode.result, 5)
        try:
            await playing.choose_move(board, target_elo=1600, move_time_ms=30)
        except EngineFailure:
            pass
        else:
            raise AssertionError("Terminated engine did not surface failure")
        assert playing._engine is None
        await playing._ensure_started()
        playing._engine.configure({"Threads": 1, "Hash": 16})
        recovered = await playing.choose_move(board, target_elo=1600, move_time_ms=30)
        assert chess.Move.from_uci(recovered.uci) in board.legal_moves
        assert playing._engine is not stopped and board.fen() == original
        return {
            "status": "measured",
            "engine_version": playing._version,
            "processes": 2,
            "threads_per_process": 1,
            "hash_mib_per_process": 16,
            "move_time_ms": 30,
            "target_elo_requested": 1600,
            "analysis_samples": 4,
            "player_latency": distribution(elapsed),
            "startup_ms": startup_ms,
            "position_unchanged": True,
            "terminated_process_reaped": True,
            "failure_surfaced_then_explicit_service_restart_verified": True,
            "isolation": "separate_serialized_engine_services_not_a_capacity_SLA",
        }
    finally:
        outcomes = await asyncio.gather(playing.close(), analysis.close(), return_exceptions=True)
        errors = [e for e in outcomes if isinstance(e, BaseException)]
        if errors:
            raise BaseExceptionGroup("Engine cleanup failed", errors)


async def benchmark(
    root,
    *,
    backends=("sqlite",),
    http_levels=(1, 8, 32),
    spectator_levels=(1, 10, 50, 100),
    include_engine=False,
):
    if (
        not http_levels
        or len(http_levels) > 4
        or any(type(n) is not int or not 1 <= n <= MAX_HTTP for n in http_levels)
    ):
        raise ValueError("HTTP concurrency must be 1–32.")
    if (
        not spectator_levels
        or len(spectator_levels) > 4
        or any(type(n) is not int or not 1 <= n <= MAX_SPECTATORS for n in spectator_levels)
    ):
        raise ValueError("Spectators must be 1–100.")
    if (
        not backends
        or len(backends) > 2
        or len(set(backends)) != len(backends)
        or any(b not in {"sqlite", "postgresql"} for b in backends)
    ):
        raise ValueError("At most one run per supported backend.")
    report = {
        "schema_version": "1.0",
        "scope": "generated_fixture_not_production_capacity",
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "version": __version__,
        "source_sha": source_sha(),
        "resource_interpretation": (
            "Linux peak RSS is cumulative, not current memory or leak proof; "
            "child RSS includes all reaped children."
        ),
        "hardware": machine(),
        "limits": {
            "scenario_seconds": MAX_SECONDS,
            "http_concurrency": MAX_HTTP,
            "spectators": MAX_SPECTATORS,
            "global_leases": 4,
        },
        "resources_before": resources(),
        "scenarios": [],
    }
    for backend in backends:
        for name, call in [
            (
                "http_spectators",
                lambda backend=backend: http_and_spectators(
                    root, backend, http_levels, spectator_levels
                ),
            ),
            ("queue_database", lambda backend=backend: queue_and_database(root, backend)),
        ]:
            async with asyncio.timeout(MAX_SECONDS):
                value = await call()
            report["scenarios"].append({"name": name, "status": "measured", **value})
    if include_engine:
        async with asyncio.timeout(MAX_SECONDS):
            report["scenarios"].append({"name": "engine", **await engine_workload()})
    report["resources_after"] = resources()
    report["interpretation"] = (
        "In-process/fixture results; network, hosted topology, RPO/RTO and SLA unestablished."
    )
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--postgres-ci", action="store_true")
    parser.add_argument("--engine", action="store_true")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="lounge-performance-") as directory:
        result = asyncio.run(
            benchmark(
                Path(directory),
                backends=("sqlite", "postgresql") if args.postgres_ci else ("sqlite",),
                include_engine=args.engine,
            )
        )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
