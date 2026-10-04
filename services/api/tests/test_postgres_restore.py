"""Native backup/restore of disposable CI databases, never an application DB."""

import asyncio
import json
import os
import re
import shutil
from pathlib import Path
from time import monotonic
from uuid import uuid4

import pytest
from lounge_api.experiment_queue import ExperimentQueue
from lounge_api.experiment_reports import ExperimentReports
from lounge_api.persistence import DatabaseStore
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine
from test_experiment_reports import terminal_run
from test_restore_rehearsal import stable_bundle_files

pytestmark = pytest.mark.skipif(
    os.getenv("TEST_POSTGRES_RESTORE") != "1",
    reason="Explicit disposable CI PostgreSQL restore infrastructure is required.",
)


async def native_tool(container, command, database, *, data=None):
    arguments = ["docker", "exec"] + (["-i"] if data is not None else [])
    arguments += [container, command, "--username=lounge", f"--dbname={database}"]
    if command == "pg_dump":
        arguments += ["--format=custom", "--no-privileges"]
    else:
        arguments += ["--exit-on-error", "--single-transaction", "--no-owner", "--no-privileges"]
    process = await asyncio.create_subprocess_exec(
        *arguments,
        stdin=asyncio.subprocess.PIPE if data is not None else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        async with asyncio.timeout(30):
            output, error = await process.communicate(data)
    except BaseException:
        if process.returncode is None:
            process.kill()
        await process.communicate()
        raise
    # Native diagnostics can contain connection details. Do not print them or dumps.
    assert process.returncode == 0, f"Disposable fixture {command} failed."
    assert not error, f"Disposable fixture {command} reported a diagnostic."
    return output


async def logical_contents(engine):
    async with engine.connect() as connection:
        names = list(
            await connection.scalars(
                text(
                    "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename"
                )
            )
        )
        result = {}
        for name in names:
            assert re.fullmatch(r"[a-z_]+", name)
            rows = await connection.scalars(text(f'SELECT row_to_json(t)::text FROM "{name}" t'))
            result[name] = sorted(json.dumps(json.loads(row), sort_keys=True) for row in rows)
        return result


def test_native_postgres_restore_preserves_generated_game_events_and_reports(tmp_path):
    async def run():
        # Guard the destructive fixture cleanup: only the declared GitHub Actions
        # loopback test service and fresh generated names are supported by this test.
        assert os.getenv("GITHUB_ACTIONS") == "true"
        assert shutil.which("docker")
        container = os.environ["POSTGRES_TEST_CONTAINER"]
        assert re.fullmatch(r"[a-f0-9]{12,64}", container)
        url = make_url(os.environ["TEST_POSTGRES_URL"])
        assert url.host in {"127.0.0.1", "localhost"}
        assert url.database == "lounge_test" and url.username == "lounge"
        assert url.port == 5432 and not url.query
        names = [f"restore_fixture_{uuid4().hex}" for _ in range(2)]
        admin = create_async_engine(url, isolation_level="AUTOCOMMIT")
        created = []
        source_engine = restore_engine = manager = restored = None
        try:
            async with admin.connect() as connection:
                for name in names:
                    await connection.execute(text(f'CREATE DATABASE "{name}"'))
                    created.append(name)
            source_url, restore_url = [
                url.set(database=name).render_as_string(hide_password=False) for name in names
            ]
            manager, plan, queue, rid = await terminal_run(tmp_path, database_url=source_url)
            before = await queue.snapshot(rid)
            game_id = before["jobs"][0]["id"]
            game = await manager.store.load_game(game_id)
            expected = (game.board.fen(), game.version, game.revision, game.result)
            events = await manager.store.list_events(game_id)
            exported = stable_bundle_files(await ExperimentReports(manager.store).bundle(rid))
            source_engine = create_async_engine(source_url)
            original = await logical_contents(source_engine)
            await manager.close()
            manager = None
            started = monotonic()
            dump = await native_tool(container, "pg_dump", names[0])
            assert dump.startswith(b"PGDMP")
            archive = tmp_path / "generated-fixture.dump"
            with archive.open("xb") as handle:
                os.chmod(archive, 0o600)
                handle.write(dump)
            await native_tool(container, "pg_restore", names[1], data=archive.read_bytes())
            restore_engine = create_async_engine(restore_url)
            # Check complete persisted rows BEFORE application initialize/create_all
            # can hide a missing restored table or migration revision.
            assert await logical_contents(restore_engine) == original
            restored = DatabaseStore(restore_url)
            recovered = await restored.load_game(game_id)
            assert (
                recovered.board.fen(),
                recovered.version,
                recovered.revision,
                recovered.result,
            ) == expected
            assert await restored.list_events(game_id) == events
            assert await ExperimentQueue(restored).snapshot(rid) == before
            actual = stable_bundle_files(await ExperimentReports(restored).bundle(rid))
            assert actual == exported
            assert plan["configuration_hash"].encode() in actual["manifest.json"]
            evidence_dir = Path(os.environ.get("TEST_RESTORE_EVIDENCE_DIR", str(tmp_path)))
            evidence_dir.mkdir(parents=True, exist_ok=True)
            (evidence_dir / "restore-evidence.json").write_text(
                json.dumps(
                    {
                        "scope": "generated_postgres_fixture",
                        "tables": len(original),
                        "rows": sum(len(rows) for rows in original.values()),
                        "archive_bytes": len(dump),
                        "elapsed_seconds": monotonic() - started,
                        "production_rpo_rto": "not_established",
                    }
                )
            )
        finally:
            cleanup = []
            if manager is not None:
                cleanup.append(manager.close())
            if restored is not None:
                cleanup.append(restored.close())
            cleanup += [
                engine.dispose() for engine in [source_engine, restore_engine] if engine is not None
            ]
            failed_cleanup = False
            try:
                results = await asyncio.gather(*cleanup, return_exceptions=True)
                failed_cleanup = any(isinstance(result, BaseException) for result in results)
            finally:
                try:
                    async with admin.connect() as connection:
                        for name in reversed(created):
                            try:
                                # Only names whose CREATE succeeded here can be dropped.
                                await connection.execute(
                                    text(f'DROP DATABASE "{name}" WITH (FORCE)')
                                )
                            except Exception:
                                failed_cleanup = True
                finally:
                    await admin.dispose()
            assert not failed_cleanup, "Disposable recovery fixture cleanup failed."

    asyncio.run(run())
