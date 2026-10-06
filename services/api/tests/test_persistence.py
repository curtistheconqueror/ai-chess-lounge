from __future__ import annotations

import asyncio
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from lounge_api.domain import StalePosition
from lounge_api.manager import GameManager
from lounge_api.models import CreateGameRequest, GameStatus, MatchState, OpponentKind
from lounge_api.persistence import DatabaseStore, MatchRow, TurnLeaseUnavailable
from sqlalchemy import update


def database_url(path: Path) -> str:
    return f"sqlite+aiosqlite:///{path}"


class MutableClock:
    def __init__(self) -> None:
        self.current = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.current

    def advance(self, **kwargs: float) -> None:
        self.current += timedelta(**kwargs)


def test_player_and_runner_migrations_upgrade_and_downgrade(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repository = Path(__file__).resolve().parents[3]
    database_path = tmp_path / "migration.db"
    monkeypatch.setenv("DATABASE_URL", database_url(database_path))
    config = Config(str(repository / "alembic.ini"))
    config.set_main_option(
        "script_location",
        str(repository / "services" / "api" / "migrations"),
    )

    def columns(table: str) -> set[str]:
        with sqlite3.connect(database_path) as connection:
            return {
                str(row[1])
                for row in connection.execute(f'PRAGMA table_info("{table}")').fetchall()
            }

    def tables() -> set[str]:
        with sqlite3.connect(database_path) as connection:
            return {
                str(row[0])
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }

    command.upgrade(config, "0003_concurrency_guards")
    assert "white_player" not in columns("matches")
    assert "player_metadata" not in columns("moves")

    command.upgrade(config, "0004_player_seats")
    assert {"white_player", "black_player"}.issubset(columns("matches"))
    assert "player_metadata" in columns("moves")

    command.upgrade(config, "0005_remote_runners")
    assert {"runner_pairings", "runner_sessions"}.issubset(tables())
    assert {"player_id", "token_digest", "issuer_digest", "last_heartbeat_at"}.issubset(
        columns("runner_sessions")
    )

    command.upgrade(config, "0006_runner_trust")
    assert {"runner_match_grants", "runner_audit_events"}.issubset(tables())
    assert {"generation", "color", "max_turns", "turns_dispatched"}.issubset(
        columns("runner_match_grants")
    )
    command.upgrade(config, "0007_human_draws")
    assert "draw_reason" in columns("matches")
    command.upgrade(config, "0008_seat_history")
    assert "seat_history" in columns("matches")
    command.upgrade(config, "0009_consultations")
    assert "consultations" in columns("matches")
    command.upgrade(config, "0010_experiments")
    assert {"id", "request_hash", "document"}.issubset(columns("experiments"))
    command.upgrade(config, "0011_experiment_queue")
    assert {"experiment_jobs", "experiment_runs", "experiment_dispatch_lock"}.issubset(tables())
    # A real pre-comparison match survives upgrade/downgrade without invented identity.
    old_fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "INSERT INTO matches (id,lifecycle,opponent,stockfish_elo,engine_move_time_ms,"
            "initial_fen,current_fen,position_version,revision,generation,event_sequence,"
            "created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "legacy-upgrade",
                "running",
                "human",
                1600,
                450,
                old_fen,
                old_fen,
                0,
                0,
                0,
                0,
                "2026-10-01T00:00:00+00:00",
                "2026-10-01T00:00:00+00:00",
            ),
        )
    command.upgrade(config, "0012_comparison_games")
    assert {"match_id", "generation", "identity", "outcome"}.issubset(columns("comparison_games"))
    with sqlite3.connect(database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM comparison_games").fetchone()[0] == 0
        assert (
            connection.execute(
                "SELECT current_fen FROM matches WHERE id='legacy-upgrade'"
            ).fetchone()[0]
            == old_fen
        )
    command.downgrade(config, "0011_experiment_queue")
    assert "comparison_games" not in tables()
    with sqlite3.connect(database_path) as connection:
        assert (
            connection.execute(
                "SELECT current_fen FROM matches WHERE id='legacy-upgrade'"
            ).fetchone()[0]
            == old_fen
        )
    command.downgrade(config, "0010_experiments")
    assert "experiment_jobs" not in tables()
    command.downgrade(config, "0009_consultations")
    assert "experiments" not in tables()
    command.downgrade(config, "0008_seat_history")
    assert "consultations" not in columns("matches")
    command.downgrade(config, "0007_human_draws")
    assert "seat_history" not in columns("matches")
    command.downgrade(config, "0006_runner_trust")
    assert "draw_reason" not in columns("matches")
    command.downgrade(config, "0005_remote_runners")
    assert "runner_match_grants" not in tables()
    assert "runner_audit_events" not in tables()

    command.downgrade(config, "0004_player_seats")
    assert "runner_pairings" not in tables()
    assert "runner_sessions" not in tables()

    command.downgrade(config, "0003_concurrency_guards")
    assert "white_player" not in columns("matches")
    assert "black_player" not in columns("matches")
    assert "player_metadata" not in columns("moves")


def test_match_survives_manager_restart(tmp_path: Path) -> None:
    async def run() -> None:
        url = database_url(tmp_path / "restart.db")
        first = GameManager(store=DatabaseStore(url))
        await first.start()
        game = await first.create(CreateGameRequest(opponent=OpponentKind.HUMAN))
        moved = await first.make_human_move(game.id, "e2e4", 0)
        await first.close()

        second = GameManager(store=DatabaseStore(url))
        await second.start()
        try:
            restored = await second.get(game.id)
            assert restored.snapshot().fen == moved.fen
            assert restored.snapshot().pgn == moved.pgn
            assert restored.snapshot().moves[0].san == "e4"
            assert restored.lifecycle is MatchState.RUNNING
        finally:
            await second.close()

    asyncio.run(run())


def test_legacy_match_without_seat_documents_restores_original_mapping() -> None:
    async def run() -> None:
        store = DatabaseStore("sqlite+aiosqlite:///:memory:")
        manager = GameManager(store=store, schedule_timeouts=False)
        await manager.start()
        try:
            game = await manager.create(CreateGameRequest(opponent=OpponentKind.STOCKFISH))
            async with store.sessions.begin() as session:
                await session.execute(
                    update(MatchRow)
                    .where(MatchRow.id == game.id)
                    .values(white_player=None, black_player=None)
                )

            restored = await store.load_game(game.id)
            assert restored is not None
            assert restored.white_player is not None
            assert restored.black_player is not None
            assert restored.white_player.adapter_id == "human"
            assert restored.black_player.adapter_id == "stockfish"
            assert restored.black_player.settings["target_elo"] == 1600
        finally:
            await manager.close()

    asyncio.run(run())


def test_reset_keeps_append_only_history(tmp_path: Path) -> None:
    async def run() -> None:
        manager = GameManager(store=DatabaseStore(database_url(tmp_path / "events.db")))
        await manager.start()
        try:
            game = await manager.create(CreateGameRequest(opponent=OpponentKind.HUMAN))
            await manager.make_human_move(game.id, "e2e4", 0)
            reset = await manager.reset(game.id)
            events = await manager.events(game.id)

            assert reset.moves == []
            assert reset.generation == 1
            assert [event.type for event in events] == [
                "match.created",
                "match.started",
                "move.accepted",
                "match.reset",
            ]
        finally:
            await manager.close()

    asyncio.run(run())


def test_database_compare_and_swap_rejects_second_writer(tmp_path: Path) -> None:
    async def run() -> None:
        url = database_url(tmp_path / "concurrency.db")
        first = GameManager(store=DatabaseStore(url))
        await first.start()
        game = await first.create(CreateGameRequest(opponent=OpponentKind.HUMAN))

        second = GameManager(store=DatabaseStore(url))
        await second.start()
        await second.get(game.id)
        try:
            await first.make_human_move(game.id, "e2e4", 0)
            with pytest.raises(StalePosition):
                await second.make_human_move(game.id, "d2d4", 0)
            refreshed = await second.get(game.id)
            assert refreshed.version == 1
            assert refreshed.moves[0].uci == "e2e4"
        finally:
            await first.close()
            await second.close()

    asyncio.run(run())


def test_clock_and_move_times_survive_restart(tmp_path: Path) -> None:
    async def run() -> None:
        clock = MutableClock()
        url = database_url(tmp_path / "clock-restart.db")
        first = GameManager(
            store=DatabaseStore(url),
            clock=clock,
            schedule_timeouts=False,
        )
        await first.start()
        game = await first.create(
            CreateGameRequest(
                opponent=OpponentKind.HUMAN,
                initial_time_ms=10_000,
                increment_ms=1_000,
            )
        )
        clock.advance(seconds=2)
        moved = await first.make_human_move(game.id, "e2e4", 0)
        await first.close()

        second = GameManager(
            store=DatabaseStore(url),
            clock=clock,
            schedule_timeouts=False,
        )
        await second.start()
        try:
            restored = await second.snapshot(game.id)
            assert restored.clock.white_remaining_ms == 9_000
            assert restored.clock.black_remaining_ms == 10_000
            assert restored.moves[0].white_remaining_ms == 9_000
            assert restored.moves[0].black_remaining_ms == 10_000
            assert restored.clock.deadline_at == moved.clock.deadline_at

            clock.advance(seconds=3)
            ticking = await second.snapshot(game.id)
            assert ticking.clock.black_remaining_ms == 7_000
        finally:
            await second.close()

    asyncio.run(run())


def test_restart_adjudicates_elapsed_deadline(tmp_path: Path) -> None:
    async def run() -> None:
        clock = MutableClock()
        url = database_url(tmp_path / "clock-expired.db")
        first = GameManager(
            store=DatabaseStore(url),
            clock=clock,
            schedule_timeouts=False,
        )
        await first.start()
        game = await first.create(
            CreateGameRequest(
                opponent=OpponentKind.HUMAN,
                initial_time_ms=1_000,
                increment_ms=0,
            )
        )
        await first.close()

        clock.advance(seconds=2)
        second = GameManager(
            store=DatabaseStore(url),
            clock=clock,
            schedule_timeouts=False,
        )
        await second.start()
        try:
            restored = await second.snapshot(game.id)
            events = await second.events(game.id)
            assert restored.status is GameStatus.TIMEOUT
            assert restored.result == "0-1"
            assert [event.type for event in events][-2:] == [
                "clock.timeout",
                "match.completed",
            ]
        finally:
            await second.close()

    asyncio.run(run())


def test_two_managers_converge_on_one_timeout_result(tmp_path: Path) -> None:
    async def run() -> None:
        clock = MutableClock()
        url = database_url(tmp_path / "clock-race.db")
        first = GameManager(
            store=DatabaseStore(url),
            clock=clock,
            schedule_timeouts=False,
        )
        await first.start()
        game = await first.create(
            CreateGameRequest(
                opponent=OpponentKind.HUMAN,
                initial_time_ms=1_000,
                increment_ms=0,
            )
        )
        second = GameManager(
            store=DatabaseStore(url),
            clock=clock,
            schedule_timeouts=False,
        )
        await second.start()
        try:
            clock.advance(seconds=1)
            outcomes = await asyncio.gather(
                first.expire_due_games(),
                second.expire_due_games(),
            )

            assert sum(game.id in outcome for outcome in outcomes) == 1
            first_snapshot = await first.snapshot(game.id)
            second_snapshot = await second.snapshot(game.id)
            events = await first.events(game.id)
            assert first_snapshot.status is GameStatus.TIMEOUT
            assert second_snapshot.status is GameStatus.TIMEOUT
            assert [event.type for event in events].count("clock.timeout") == 1
            assert [event.type for event in events].count("match.completed") == 1
        finally:
            await first.close()
            await second.close()

    asyncio.run(run())


def test_cross_instance_snapshot_refreshes_stale_cache(tmp_path: Path) -> None:
    async def run() -> None:
        url = database_url(tmp_path / "cross-instance-read.db")
        first = GameManager(store=DatabaseStore(url), schedule_timeouts=False)
        second = GameManager(store=DatabaseStore(url), schedule_timeouts=False)
        await first.start()
        game = await first.create(CreateGameRequest(opponent=OpponentKind.HUMAN))
        await second.start()
        await second.get(game.id)
        try:
            committed = await first.make_human_move(game.id, "e2e4", 0)
            refreshed = await second.snapshot(game.id)

            assert refreshed.version == committed.version == 1
            assert refreshed.fen == committed.fen
            assert refreshed.moves[0].uci == "e2e4"
        finally:
            await first.close()
            await second.close()

    asyncio.run(run())


def test_cross_instance_mutation_reloads_stale_cache(tmp_path: Path) -> None:
    async def run() -> None:
        url = database_url(tmp_path / "cross-instance-write.db")
        first = GameManager(store=DatabaseStore(url), schedule_timeouts=False)
        second = GameManager(store=DatabaseStore(url), schedule_timeouts=False)
        await first.start()
        game = await first.create(CreateGameRequest(opponent=OpponentKind.HUMAN))
        await second.start()
        await second.get(game.id)
        try:
            await first.make_human_move(game.id, "e2e4", 0)
            committed = await second.make_human_move(game.id, "e7e5", 1)

            assert committed.version == 2
            assert [move.uci for move in committed.moves] == ["e2e4", "e7e5"]
        finally:
            await first.close()
            await second.close()

    asyncio.run(run())


def test_idempotent_move_retry_survives_process_handoff(tmp_path: Path) -> None:
    async def run() -> None:
        url = database_url(tmp_path / "idempotency.db")
        first = GameManager(store=DatabaseStore(url), schedule_timeouts=False)
        await first.start()
        game = await first.create(CreateGameRequest(opponent=OpponentKind.HUMAN))
        accepted = await first.make_human_move(
            game.id,
            "e2e4",
            0,
            "handoff-move-0001",
        )
        await first.close()

        second = GameManager(store=DatabaseStore(url), schedule_timeouts=False)
        await second.start()
        try:
            replayed = await second.make_human_move(
                game.id,
                "e2e4",
                0,
                "handoff-move-0001",
            )
            events = await second.events(game.id)

            assert replayed.version == accepted.version == 1
            assert len(replayed.moves) == 1
            assert [event.type for event in events].count("move.accepted") == 1
        finally:
            await second.close()

    asyncio.run(run())


def test_turn_lease_is_exclusive_expires_and_is_fenced_by_move(tmp_path: Path) -> None:
    async def run() -> None:
        clock = MutableClock()
        url = database_url(tmp_path / "leases.db")
        first = GameManager(
            store=DatabaseStore(url),
            clock=clock,
            schedule_timeouts=False,
        )
        second = GameManager(
            store=DatabaseStore(url),
            clock=clock,
            schedule_timeouts=False,
        )
        await first.start()
        game = await first.create(CreateGameRequest(opponent=OpponentKind.HUMAN))
        await second.start()
        try:
            first_lease = await first.acquire_turn_lease(
                game.id,
                "runner:first",
                game.version,
                lease_ms=500,
            )
            with pytest.raises(TurnLeaseUnavailable):
                await second.acquire_turn_lease(
                    game.id,
                    "runner:second",
                    game.version,
                    lease_ms=500,
                )

            clock.advance(seconds=1)
            second_lease = await second.acquire_turn_lease(
                game.id,
                "runner:second",
                game.version,
                lease_ms=500,
            )
            assert await first.release_turn_lease(first_lease) is False

            await first.make_human_move(game.id, "e2e4", game.version)
            with pytest.raises(TurnLeaseUnavailable):
                await second.renew_turn_lease(second_lease, lease_ms=500)
        finally:
            await first.close()
            await second.close()

    asyncio.run(run())


def test_injected_crash_rolls_back_projection_move_event_and_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class SimulatedCrash(RuntimeError):
        pass

    async def run() -> None:
        url = database_url(tmp_path / "crash-rollback.db")
        store = DatabaseStore(url)
        first = GameManager(store=store, schedule_timeouts=False)
        await first.start()
        game = await first.create(CreateGameRequest(opponent=OpponentKind.HUMAN))
        original_flush = store._flush_mutation

        async def crash_after_flush(session) -> None:
            await session.flush()
            raise SimulatedCrash("process exited before commit")

        monkeypatch.setattr(store, "_flush_mutation", crash_after_flush)
        with pytest.raises(SimulatedCrash):
            await first.make_human_move(game.id, "e2e4", 0, "crash-move-0001")
        cached = await first.get(game.id)
        restored = await store.load_game(game.id)
        persisted_hash = await store.get_idempotency_hash(
            game.id,
            "move",
            "crash-move-0001",
        )
        events = await first.events(game.id)

        assert cached.version == 0
        assert cached.moves == []
        assert restored is not None
        assert restored.version == 0
        assert restored.moves == []
        assert [event.type for event in events] == ["match.created", "match.started"]
        assert persisted_hash is None

        monkeypatch.setattr(store, "_flush_mutation", original_flush)
        try:
            retried = await first.make_human_move(
                game.id,
                "e2e4",
                0,
                "crash-move-0001",
            )
            assert retried.version == 1
            assert [move.uci for move in retried.moves] == ["e2e4"]
        finally:
            await first.close()

    asyncio.run(run())
