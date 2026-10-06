"""Durable batch queue. No adapter dispatch happens in this repository layer."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4, uuid5

from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError

from .persistence import (
    DatabaseStore,
    ExperimentDispatchRow,
    ExperimentJobRow,
    ExperimentRow,
    ExperimentRunRow,
    MatchRow,
)
from .tournaments import resolve_tournament, tournament_report


class QueueConflict(ValueError):
    pass


def utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class ExperimentQueue:
    def __init__(self, store: DatabaseStore):
        self.store = store

    async def create(self, experiment_id: str, run_id: str, concurrency: int = 1) -> dict:
        UUID(run_id)
        if not 1 <= concurrency <= 4:
            raise ValueError("Concurrency must be between one and four.")
        await self.store.initialize()
        try:
            async with self.store.sessions.begin() as session:
                if await session.get(ExperimentDispatchRow, 1) is None:
                    session.add(ExperimentDispatchRow(id=1))
        except IntegrityError:
            pass  # A concurrent creator initialized the same singleton.
        async with self.store.sessions() as session:
            existing = await session.get(ExperimentRunRow, run_id)
            if existing:
                if existing.experiment_id != experiment_id or existing.concurrency != concurrency:
                    raise QueueConflict("Run ID was used for different settings.")
                return await self.snapshot(run_id)
            experiment = await session.get(ExperimentRow, experiment_id)
            if experiment is None:
                raise KeyError(experiment_id)
            manifest = experiment.document
        now = datetime.now(UTC)
        try:
            async with self.store.sessions.begin() as session:
                session.add(
                    ExperimentRunRow(
                        id=run_id,
                        experiment_id=experiment_id,
                        state="ready",
                        revision=0,
                        concurrency=concurrency,
                        created_at=now,
                        deadline=None,
                    )
                )
                await session.flush()
                for game in manifest["schedule"]:
                    session.add(
                        ExperimentJobRow(
                            id=str(uuid5(UUID(run_id), str(game["number"]))),
                            run_id=run_id,
                            number=game["number"],
                            state="queued",
                            lease_token=None,
                            lease_expires_at=None,
                            result=None,
                        )
                    )
        except IntegrityError:
            async with self.store.sessions() as session:
                existing = await session.get(ExperimentRunRow, run_id)
                if (
                    existing is None
                    or existing.experiment_id != experiment_id
                    or existing.concurrency != concurrency
                ):
                    raise QueueConflict("Run ID was used for different settings.") from None
        return await self.snapshot(run_id)

    async def snapshot(self, run_id: str) -> dict:
        async with self.store.sessions() as session:
            run = await session.get(ExperimentRunRow, run_id)
            if run is None:
                raise KeyError(run_id)
            jobs = (
                await session.scalars(
                    select(ExperimentJobRow)
                    .where(ExperimentJobRow.run_id == run_id)
                    .order_by(ExperimentJobRow.number)
                )
            ).all()
            existing_games = set(
                await session.scalars(
                    select(MatchRow.id).where(MatchRow.id.in_([j.id for j in jobs]))
                )
            )
            experiment = await session.get(ExperimentRow, run.experiment_id)
            public_jobs = [
                {
                    "id": j.id,
                    "number": j.number,
                    "state": j.state,
                    "result": j.result,
                    "has_game": j.id in existing_games,
                }
                for j in jobs
            ]
            return {
                "id": run.id,
                "experiment_id": run.experiment_id,
                "state": run.state,
                "revision": run.revision,
                "concurrency": run.concurrency,
                "created_at": utc(run.created_at).isoformat(),
                "deadline": utc(run.deadline).isoformat() if run.deadline else None,
                "jobs": public_jobs,
                "report": tournament_report(experiment.document, public_jobs, run.state),
            }

    async def transition(
        self, run_id: str, target: str, expected_revision: int, *, now: datetime | None = None
    ) -> dict:
        now = now or datetime.now(UTC)
        transitions = {
            "ready": {"running", "cancelled"},
            "running": {"paused", "pausing", "cancelled"},
            "pausing": {"paused", "cancelled"},
            "paused": {"running", "cancelled"},
        }
        async with self.store.sessions.begin() as session:
            # A write locks the run before any child mutation on SQLite and PostgreSQL.
            result = await session.execute(
                update(ExperimentRunRow)
                .where(
                    ExperimentRunRow.id == run_id, ExperimentRunRow.revision == expected_revision
                )
                .values(revision=expected_revision + 1)
            )
            if result.rowcount != 1:
                raise QueueConflict("Run changed. Refresh before controlling it.")
            run = await session.get(ExperimentRunRow, run_id)
            if target not in transitions.get(run.state, set()):
                raise QueueConflict("This run transition is not allowed.")
            if run.deadline is not None and utc(run.deadline) <= now and target == "running":
                raise QueueConflict("Original run deadline has expired; create a new run.")
            if run.deadline is None and target == "running":
                experiment = await session.get(ExperimentRow, run.experiment_id)
                run.deadline = now + timedelta(
                    milliseconds=experiment.document["configuration"]["stops"]["max_wall_time_ms"]
                )
            run.state = target
            if target in {"paused", "pausing"}:
                await session.execute(
                    update(ExperimentJobRow)
                    .where(ExperimentJobRow.run_id == run_id, ExperimentJobRow.state == "leased")
                    .values(state="queued", lease_token=None, lease_expires_at=None)
                )
            if target == "cancelled":
                await session.execute(
                    update(ExperimentJobRow)
                    .execution_options(synchronize_session=False)
                    .where(
                        ExperimentJobRow.run_id == run_id,
                        ExperimentJobRow.state.in_(["queued", "leased"]),
                    )
                    .values(state="cancelled", lease_token=None, lease_expires_at=None)
                )
        return await self.snapshot(run_id)

    async def claim(self, run_id: str, *, now: datetime, lease_ms: int = 10_000) -> dict | None:
        if not 100 <= lease_ms <= 120_000:
            raise ValueError("Invalid worker lease parameters.")
        token = str(uuid4())
        async with self.store.sessions.begin() as session:
            locked = await session.execute(
                update(ExperimentDispatchRow).where(ExperimentDispatchRow.id == 1).values(id=1)
            )
            if locked.rowcount != 1:
                raise QueueConflict("Dispatch coordination is not initialized.")
            await session.execute(
                update(ExperimentRunRow)
                .where(ExperimentRunRow.id == run_id)
                .values(revision=ExperimentRunRow.revision)
            )
            run = await session.get(ExperimentRunRow, run_id)
            if run is None or run.state != "running":
                return None
            if run.deadline is None or utc(run.deadline) <= now:
                return None
            # Expired reservations can be reclaimed with the SAME durable game ID.
            await session.execute(
                update(ExperimentJobRow)
                .execution_options(synchronize_session=False)
                .where(
                    ExperimentJobRow.run_id == run_id,
                    ExperimentJobRow.state == "leased",
                    ExperimentJobRow.lease_expires_at <= now,
                )
                .values(state="queued", lease_token=None, lease_expires_at=None)
            )
            active = await session.scalar(
                select(func.count())
                .select_from(ExperimentJobRow)
                .where(
                    ExperimentJobRow.run_id == run_id,
                    ExperimentJobRow.state.in_(["leased", "running"]),
                )
            )
            total_active = await session.scalar(
                select(func.count())
                .select_from(ExperimentJobRow)
                .where(ExperimentJobRow.state == "leased")
            )
            if active >= run.concurrency or total_active >= 4:
                return None
            jobs = list(
                await session.scalars(
                    select(ExperimentJobRow)
                    .where(ExperimentJobRow.run_id == run_id)
                    .order_by(ExperimentJobRow.number)
                )
            )
            experiment = await session.get(ExperimentRow, run.experiment_id)
            opponents, _, _ = resolve_tournament(
                experiment.document,
                [{"number": j.number, "state": j.state, "result": j.result} for j in jobs],
            )
            job = next((j for j in jobs if j.state == "queued" and j.number in opponents), None)
            if job is None:
                return None
            job.state, job.lease_token = "leased", token
            job.lease_expires_at = min(now + timedelta(milliseconds=lease_ms), utc(run.deadline))
            return {
                "id": job.id,
                "run_id": run.id,
                "number": job.number,
                "lease_token": token,
                "lease_expires_at": job.lease_expires_at.isoformat(),
                "white": opponents[job.number][0],
                "black": opponents[job.number][1],
            }

    async def finish(self, job_id: str, token: str, result: str, *, now: datetime) -> None:
        if result not in {"1-0", "0-1", "1/2-1/2", "failed", "limited"}:
            raise ValueError("Invalid job result.")
        async with self.store.sessions.begin() as session:
            job = await session.get(ExperimentJobRow, job_id)
            if job is None:
                raise KeyError(job_id)
            await session.execute(
                update(ExperimentRunRow)
                .where(ExperimentRunRow.id == job.run_id)
                .values(revision=ExperimentRunRow.revision)
            )
            run = await session.get(ExperimentRunRow, job.run_id)
            updated = await session.execute(
                update(ExperimentJobRow)
                .execution_options(synchronize_session=False)
                .where(
                    ExperimentJobRow.id == job_id,
                    ExperimentJobRow.state == "leased",
                    ExperimentJobRow.lease_token == token,
                    ExperimentJobRow.lease_expires_at > now,
                )
                .values(
                    state="failed" if result == "failed" else "completed",
                    result=result,
                    lease_token=None,
                    lease_expires_at=None,
                )
            )
            if run.state != "running" or updated.rowcount != 1:
                raise QueueConflict("Job lease or run is no longer active.")
            await session.refresh(job)
            jobs = list(
                await session.scalars(
                    select(ExperimentJobRow).where(ExperimentJobRow.run_id == run.id)
                )
            )
            experiment = await session.get(ExperimentRow, run.experiment_id)
            _, blocked, _ = resolve_tournament(
                experiment.document,
                [{"number": j.number, "state": j.state, "result": j.result} for j in jobs],
            )
            for pending in jobs:
                if pending.number in blocked and pending.state == "queued":
                    pending.state = "blocked"
            await session.flush()
            failed = await session.scalar(
                select(func.count())
                .select_from(ExperimentJobRow)
                .where(ExperimentJobRow.run_id == run.id, ExperimentJobRow.state == "failed")
            )
            experiment = await session.get(ExperimentRow, run.experiment_id)
            if failed >= experiment.document["configuration"]["stops"]["max_failures"]:
                run.state = "stopped"
                await session.execute(
                    update(ExperimentJobRow)
                    .execution_options(synchronize_session=False)
                    .where(
                        ExperimentJobRow.run_id == run.id,
                        ExperimentJobRow.state.in_(["queued", "leased"]),
                    )
                    .values(state="cancelled", lease_token=None, lease_expires_at=None)
                )
            else:
                remaining = await session.scalar(
                    select(func.count())
                    .select_from(ExperimentJobRow)
                    .where(
                        ExperimentJobRow.run_id == run.id,
                        ExperimentJobRow.state.in_(["queued", "leased", "running"]),
                    )
                )
                if remaining == 0:
                    run.state = "stopped" if blocked else "completed"
            run.revision += 1

    async def renew(
        self, job_id: str, token: str, *, now: datetime, lease_ms: int = 10_000
    ) -> bool:
        if not 100 <= lease_ms <= 120_000:
            raise ValueError("Invalid lease duration.")
        async with self.store.sessions.begin() as session:
            job = await session.get(ExperimentJobRow, job_id)
            if job is None:
                return False
            await session.execute(
                update(ExperimentRunRow)
                .where(ExperimentRunRow.id == job.run_id)
                .values(revision=ExperimentRunRow.revision)
            )
            run = await session.get(ExperimentRunRow, job.run_id)
            if run.state != "running" or run.deadline is None or utc(run.deadline) <= now:
                return False
            result = await session.execute(
                update(ExperimentJobRow)
                .execution_options(synchronize_session=False)
                .where(
                    ExperimentJobRow.id == job_id,
                    ExperimentJobRow.state == "leased",
                    ExperimentJobRow.lease_token == token,
                    ExperimentJobRow.lease_expires_at > now,
                )
                .values(
                    lease_expires_at=min(now + timedelta(milliseconds=lease_ms), utc(run.deadline))
                )
            )
            return result.rowcount == 1

    async def guard(
        self, game_id: str, *, now: datetime, plies: int, token: str | None = None
    ) -> str | None:
        async with self.store.sessions() as session:
            job = await session.get(ExperimentJobRow, game_id)
            if job is None:
                return None
            run = await session.get(ExperimentRunRow, job.run_id)
            if run.state in {"paused", "pausing"}:
                return "paused"
            if run.state != "running" or job.state != "leased":
                return "cancelled"
            if run.deadline is None or utc(run.deadline) <= now:
                return "deadline"
            if (
                job.lease_expires_at is None
                or utc(job.lease_expires_at) <= now
                or token is None
                or token != job.lease_token
            ):
                return "lease_expired"
            experiment = await session.get(ExperimentRow, run.experiment_id)
            if plies >= experiment.document["configuration"]["stops"]["max_plies"]:
                return "ply_limit"
            return None

    async def active_runs(self) -> list[str]:
        async with self.store.sessions() as session:
            unfinished = (
                select(ExperimentJobRow.run_id)
                .join(MatchRow, MatchRow.id == ExperimentJobRow.id)
                .where(MatchRow.lifecycle.in_(["running", "paused"]))
            )
            return list(
                await session.scalars(
                    select(ExperimentRunRow.id).where(
                        or_(
                            ExperimentRunRow.state.in_(["running", "paused", "pausing"]),
                            ExperimentRunRow.id.in_(unfinished),
                        )
                    )
                )
            )

    async def expire(self, run_id: str, *, now: datetime) -> None:
        async with self.store.sessions.begin() as session:
            await session.execute(
                update(ExperimentRunRow)
                .where(ExperimentRunRow.id == run_id)
                .values(revision=ExperimentRunRow.revision)
            )
            run = await session.get(ExperimentRunRow, run_id)
            if (
                run
                and run.state in {"running", "paused", "pausing"}
                and run.deadline
                and utc(run.deadline) <= now
            ):
                run.state, run.revision = "stopped", run.revision + 1
                await session.execute(
                    update(ExperimentJobRow)
                    .where(
                        ExperimentJobRow.run_id == run_id,
                        ExperimentJobRow.state.in_(["queued", "leased"]),
                    )
                    .values(state="cancelled", lease_token=None, lease_expires_at=None)
                )

    async def list_runs(self, experiment_id: str) -> list[dict]:
        async with self.store.sessions() as session:
            runs = (
                await session.scalars(
                    select(ExperimentRunRow)
                    .where(ExperimentRunRow.experiment_id == experiment_id)
                    .order_by(ExperimentRunRow.created_at.desc())
                    .limit(50)
                )
            ).all()
            return [
                {
                    "id": r.id,
                    "state": r.state,
                    "revision": r.revision,
                    "created_at": utc(r.created_at).isoformat(),
                }
                for r in runs
            ]

    async def state(self, run_id: str) -> str | None:
        async with self.store.sessions() as session:
            return await session.scalar(
                select(ExperimentRunRow.state).where(ExperimentRunRow.id == run_id)
            )
