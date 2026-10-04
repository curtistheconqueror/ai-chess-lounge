"""Offline recovery rehearsal: generated fixtures only, no deployment or providers."""

import asyncio
import io
import sqlite3
from contextlib import closing
from pathlib import Path
from zipfile import ZipFile

from lounge_api.experiment_queue import ExperimentQueue
from lounge_api.experiment_reports import ExperimentReports
from lounge_api.persistence import DatabaseStore
from test_experiment_reports import terminal_run


def snapshot_sqlite(source: Path, destination: Path) -> None:
    # A test rehearsal, not a production backup/retention service. The destination
    # is a fresh tmp_path file; no existing database is ever replaced.
    with destination.open("xb"):
        pass
    with (
        closing(sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True)) as reader,
        closing(sqlite3.connect(destination)) as writer,
    ):
        reader.backup(writer)
        assert writer.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
        assert writer.execute("PRAGMA foreign_key_check").fetchall() == []


def stable_bundle_files(data: bytes) -> dict[str, bytes]:
    with ZipFile(io.BytesIO(data)) as archive:
        return {
            name: archive.read(name)
            for name in ["manifest.json", "games.csv", "moves.csv", "games.pgn"]
        }


def test_restore_retains_terminal_games_events_queue_and_reproducible_exports(tmp_path):
    async def run():
        manager, plan, queue, rid = await terminal_run(tmp_path)
        source = Path(manager.store.engine.url.database)
        try:
            before = await queue.snapshot(rid)
            exported = stable_bundle_files(await ExperimentReports(manager.store).bundle(rid))
            game_id = before["jobs"][0]["id"]
            game = await manager.store.load_game(game_id)
            assert game is not None
            expected = (game.board.fen(), game.version, game.revision, game.result)
        finally:
            await manager.close()

        backup, restored = tmp_path / "backup.sqlite", tmp_path / "restored.sqlite"
        snapshot_sqlite(source, backup)
        # Recovery operates on a second isolated copy, preserving backup evidence.
        snapshot_sqlite(backup, restored)
        with (
            closing(sqlite3.connect(source)) as original,
            closing(sqlite3.connect(restored)) as copy,
        ):
            assert list(original.iterdump()) == list(copy.iterdump())
        store = DatabaseStore(f"sqlite+aiosqlite:///{restored}")
        try:
            recovered = await store.load_game(game_id)
            assert recovered is not None
            assert (
                recovered.board.fen(),
                recovered.version,
                recovered.revision,
                recovered.result,
            ) == expected
            assert await ExperimentQueue(store).snapshot(rid) == before
            actual = stable_bundle_files(await ExperimentReports(store).bundle(rid))
            assert actual == exported
            assert plan["configuration_hash"].encode() in actual["manifest.json"]
        finally:
            await store.close()

    asyncio.run(run())


def test_sqlite_backup_includes_committed_wal_and_excludes_uncommitted_work(tmp_path):
    source, backup = tmp_path / "live.sqlite", tmp_path / "backup.sqlite"
    with closing(sqlite3.connect(source)) as writer:
        assert writer.execute("PRAGMA journal_mode=WAL").fetchone() == ("wal",)
        writer.execute("PRAGMA wal_autocheckpoint=0")
        writer.execute("CREATE TABLE evidence (value TEXT NOT NULL)")
        writer.execute("INSERT INTO evidence VALUES ('committed')")
        writer.commit()
        writer.execute("INSERT INTO evidence VALUES ('uncommitted')")
        assert Path(str(source) + "-wal").stat().st_size > 0
        snapshot_sqlite(source, backup)
        with closing(sqlite3.connect(backup)) as recovered:
            assert recovered.execute("SELECT value FROM evidence").fetchall() == [("committed",)]
        writer.rollback()
