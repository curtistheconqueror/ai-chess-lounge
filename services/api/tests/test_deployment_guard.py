import asyncio

import pytest
from fastapi.testclient import TestClient
from lounge_api.deployment_guard import require_local_runtime
from lounge_api.experiment_worker import ExperimentWorker
from lounge_api.main import create_app
from lounge_api.manager import GameManager
from lounge_api.persistence import SCHEMA_REVISION, DatabaseStore
from sqlalchemy import text
from test_manager import FakeEngine


@pytest.mark.parametrize(
    "deployment,hosted",
    [
        ("hosted", None),
        ("hosted", "0"),
        ("hosted", "1"),
        ("production", None),
        ("local", "true"),
        ("local", "01"),
        ("local", " 1"),
        ("local", ""),
        ("", "0"),
        (None, "1"),
    ],
)
def test_invalid_or_hosted_mode_cannot_start_workers_or_database(
    tmp_path, monkeypatch, deployment, hosted
):
    monkeypatch.delenv("LOUNGE_DEPLOYMENT", raising=False)
    monkeypatch.delenv("LOUNGE_HOSTED_MODE", raising=False)
    if deployment is not None:
        monkeypatch.setenv("LOUNGE_DEPLOYMENT", deployment)
    if hosted is not None:
        monkeypatch.setenv("LOUNGE_HOSTED_MODE", hosted)
    db = tmp_path / "must-not-open.db"
    m = GameManager(engine=FakeEngine(), store=DatabaseStore(f"sqlite+aiosqlite:///{db}"))
    worker = ExperimentWorker(m)
    with pytest.raises(RuntimeError):
        require_local_runtime()
    with pytest.raises(RuntimeError):
        asyncio.run(m.start())
    with pytest.raises(RuntimeError):
        worker.start()
    with pytest.raises(RuntimeError):
        asyncio.run(m.store.initialize())
    with pytest.raises(RuntimeError):
        with TestClient(create_app(m)):
            pytest.fail("Hosted lifespan must not enter")
    assert not db.exists()
    assert not m._agent_tasks and not m._timeout_tasks and worker.task is None
    asyncio.run(m.store.close())


@pytest.mark.parametrize(
    "failure",
    [
        "none",
        "missing_revision",
        "wrong_revision",
        "multiple_heads",
        "missing_table",
        "missing_column",
        "missing_ownership",
    ],
)
def test_schema_verification_reads_all_heads_and_required_columns(tmp_path, monkeypatch, failure):
    monkeypatch.setenv("LOUNGE_DEPLOYMENT", "local")
    monkeypatch.setenv("LOUNGE_HOSTED_MODE", "0")

    async def run():
        store = DatabaseStore(f"sqlite+aiosqlite:///{tmp_path / 'schema.db'}")
        await store.initialize()
        try:
            async with store.engine.begin() as connection:
                if failure == "missing_revision":
                    await connection.execute(text("DROP TABLE alembic_version"))
                elif failure == "wrong_revision":
                    await connection.execute(text("UPDATE alembic_version SET version_num='old'"))
                elif failure == "multiple_heads":
                    await connection.execute(
                        text("INSERT INTO alembic_version VALUES ('other_head')")
                    )
                elif failure == "missing_table":
                    await connection.execute(text("DROP TABLE comparison_games"))
                elif failure == "missing_column":
                    await connection.execute(text("ALTER TABLE matches DROP COLUMN consultations"))
                before = list(
                    (
                        await connection.execute(
                            text("SELECT name, sql FROM sqlite_master ORDER BY name")
                        )
                    ).all()
                )
            monkeypatch.setenv("LOUNGE_DEPLOYMENT", "hosted")
            if failure == "none":
                await store.validate_existing_schema(SCHEMA_REVISION)
            else:
                with pytest.raises(RuntimeError, match="schema"):
                    await store.validate_existing_schema(
                        SCHEMA_REVISION,
                        {"matches": {"owner_id"}} if failure == "missing_ownership" else None,
                    )
            async with store.engine.connect() as connection:
                after = list(
                    (
                        await connection.execute(
                            text("SELECT name, sql FROM sqlite_master ORDER BY name")
                        )
                    ).all()
                )
            assert before == after
            # Read-only schema success must never unlock this unfinished hosted build.
            with pytest.raises(RuntimeError, match="Hosted startup"):
                await store.initialize()
        finally:
            await store.close()

    asyncio.run(run())
