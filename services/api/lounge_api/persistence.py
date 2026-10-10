from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import chess
from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    delete,
    inspect,
    or_,
    select,
    text,
    update,
)
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.pool import StaticPool

from .comparison_identity import outcome as comparison_outcome
from .deployment_guard import require_local_runtime
from .domain import GameSession
from .models import (
    Consultation,
    EngineSummary,
    MatchEvent,
    MatchState,
    MoveRecord,
    OpponentKind,
    RunnerPairingRecord,
    RunnerSessionRecord,
    SeatChange,
    TurnLease,
)
from .player_protocol import PlayerConfiguration, PlayerMoveMetadata

DEFAULT_DATABASE_URL = "sqlite+aiosqlite:///./.runtime/lounge.db"
SCHEMA_REVISION = "0012_comparison_games"


class ConcurrentGameUpdate(RuntimeError):
    """Raised when another process changed a match before this write committed."""


class IdempotencyConflict(RuntimeError):
    """Raised when an idempotency key is reused for a different command."""


class TurnLeaseUnavailable(RuntimeError):
    """Raised when another worker owns the active turn lease."""


class Base(DeclarativeBase):
    pass


class ExperimentRow(Base):
    __tablename__ = "experiments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    document: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)


class ExperimentDispatchRow(Base):
    __tablename__ = "experiment_dispatch_lock"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)


class ExperimentRunRow(Base):
    __tablename__ = "experiment_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    experiment_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("experiments.id"), nullable=False
    )
    state: Mapped[str] = mapped_column(String(24), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    concurrency: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ExperimentJobRow(Base):
    __tablename__ = "experiment_jobs"
    __table_args__ = (UniqueConstraint("run_id", "number", name="uq_experiment_job_number"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("experiment_runs.id"), nullable=False
    )
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[str] = mapped_column(String(24), nullable=False)
    lease_token: Mapped[str | None] = mapped_column(String(120), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    result: Mapped[str | None] = mapped_column(String(24), nullable=True)


class MatchRow(Base):
    __tablename__ = "matches"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    lifecycle: Mapped[str] = mapped_column(String(24), nullable=False)
    opponent: Mapped[str] = mapped_column(String(24), nullable=False)
    stockfish_elo: Mapped[int] = mapped_column(Integer, nullable=False)
    engine_move_time_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    initial_time_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    increment_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    white_remaining_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    black_remaining_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    turn_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    timed_out_by: Mapped[str | None] = mapped_column(String(5), nullable=True)
    initial_fen: Mapped[str] = mapped_column(Text, nullable=False)
    current_fen: Mapped[str] = mapped_column(Text, nullable=False)
    position_version: Mapped[int] = mapped_column(Integer, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    generation: Mapped[int] = mapped_column(Integer, nullable=False)
    event_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    draw_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    resigned_by: Mapped[str | None] = mapped_column(String(5), nullable=True)
    adjudicated_result: Mapped[str | None] = mapped_column(String(7), nullable=True)
    engine_summary: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    white_player: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    black_player: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    seat_history: Mapped[list[dict[str, object]] | None] = mapped_column(JSON, nullable=True)
    consultations: Mapped[list[dict[str, object]] | None] = mapped_column(JSON, nullable=True)
    turn_lease_owner: Mapped[str | None] = mapped_column(String(120), nullable=True)
    turn_lease_token: Mapped[str | None] = mapped_column(String(36), nullable=True)
    turn_lease_position_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    turn_lease_acquired_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    turn_lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ComparisonGameRow(Base):
    __tablename__ = "comparison_games"
    match_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("matches.id", ondelete="CASCADE"), primary_key=True
    )
    generation: Mapped[int] = mapped_column(Integer, primary_key=True)
    identity: Mapped[dict] = mapped_column(JSON, nullable=False)
    outcome: Mapped[dict] = mapped_column(JSON, nullable=False)


class MoveRow(Base):
    __tablename__ = "moves"
    __table_args__ = (
        UniqueConstraint("match_id", "generation", "ply", name="uq_moves_match_generation_ply"),
        Index("ix_moves_match_generation", "match_id", "generation"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    match_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("matches.id", ondelete="CASCADE"), nullable=False
    )
    generation: Mapped[int] = mapped_column(Integer, nullable=False)
    ply: Mapped[int] = mapped_column(Integer, nullable=False)
    uci: Mapped[str] = mapped_column(String(5), nullable=False)
    san: Mapped[str] = mapped_column(String(16), nullable=False)
    actor: Mapped[str] = mapped_column(String(120), nullable=False)
    fen: Mapped[str] = mapped_column(Text, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    elapsed_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    white_remaining_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    black_remaining_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    player_metadata: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)


class EventRow(Base):
    __tablename__ = "match_events"
    __table_args__ = (
        UniqueConstraint("match_id", "sequence", name="uq_events_match_sequence"),
        Index("ix_events_match_sequence", "match_id", "sequence"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    match_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("matches.id", ondelete="CASCADE"), nullable=False
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    position_version: Mapped[int] = mapped_column(Integer, nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class IdempotencyRow(Base):
    __tablename__ = "idempotency_keys"
    __table_args__ = (
        UniqueConstraint(
            "match_id",
            "operation",
            "idempotency_key",
            name="uq_idempotency_match_operation_key",
        ),
        Index("ix_idempotency_match_created", "match_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    match_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("matches.id", ondelete="CASCADE"), nullable=False
    )
    operation: Mapped[str] = mapped_column(String(32), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    applied_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class RunnerPairingRow(Base):
    __tablename__ = "runner_pairings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    code_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    player: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    session_ttl_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    webhook_url: Mapped[str | None] = mapped_column(String(2_048), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RunnerSessionRow(Base):
    __tablename__ = "runner_sessions"
    __table_args__ = (
        UniqueConstraint("pairing_id", name="uq_runner_sessions_pairing"),
        Index("ix_runner_sessions_player", "player_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    pairing_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("runner_pairings.id", ondelete="CASCADE"), nullable=False
    )
    player_id: Mapped[str] = mapped_column(String(120), nullable=False)
    player: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    token_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    issuer_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    permissions: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    webhook_url: Mapped[str | None] = mapped_column(String(2_048), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_heartbeat_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RunnerTrustError(RuntimeError):
    """A match grant is unavailable, exhausted, expired, or revoked."""


class RunnerGrantRow(Base):
    __tablename__ = "runner_match_grants"

    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("runner_sessions.id"), primary_key=True
    )
    match_id: Mapped[str] = mapped_column(String(120), nullable=False)
    generation: Mapped[int] = mapped_column(Integer, nullable=False)
    color: Mapped[str] = mapped_column(String(5), nullable=False)
    turns_dispatched: Mapped[int] = mapped_column(Integer, nullable=False)
    max_turns: Mapped[int] = mapped_column(Integer, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class RunnerAuditRow(Base):
    __tablename__ = "runner_audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    match_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


def normalize_database_url(url: str) -> str:
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    if url.startswith("postgresql://") and "+" not in url.split("://", 1)[0]:
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class DatabaseStore:
    def __init__(self, url: str | None = None) -> None:
        self.url = normalize_database_url(url or os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL))
        if self.url.startswith("sqlite") and ":memory:" not in self.url:
            raw_path = self.url.rsplit("///", 1)[-1]
            if raw_path and raw_path != self.url:
                Path(raw_path).expanduser().parent.mkdir(parents=True, exist_ok=True)
        engine_options: dict[str, object] = {"pool_pre_ping": True}
        if self.url.endswith(":memory:"):
            engine_options["poolclass"] = StaticPool
        self.engine: AsyncEngine = create_async_engine(self.url, **engine_options)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        self._initialized = False

    async def initialize(self) -> None:
        require_local_runtime()
        if self._initialized:
            return
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
            await connection.execute(
                text(
                    "CREATE TABLE IF NOT EXISTS alembic_version "
                    "(version_num VARCHAR(32) NOT NULL PRIMARY KEY)"
                )
            )
            current_revision = await connection.scalar(
                text("SELECT version_num FROM alembic_version LIMIT 1")
            )
            if current_revision is None:
                await connection.execute(
                    text(f"INSERT INTO alembic_version (version_num) VALUES ('{SCHEMA_REVISION}')")
                )
        self._initialized = True

    async def validate_existing_schema(
        self, expected_revision: str, extra_columns: dict[str, set[str]] | None = None
    ) -> None:
        """Read-only validation; never create/stamp tables or enable hosted mode.

        The eventual ownership migration must supply its exact revision and its
        required ownership/permission columns; today's schema is not that schema.
        """
        required = {table.name: set(table.columns.keys()) for table in Base.metadata.sorted_tables}
        for table, columns in (extra_columns or {}).items():
            required.setdefault(table, set()).update(columns)

        def check_columns(connection):
            inspector = inspect(connection)
            tables = set(inspector.get_table_names())
            for table, columns in required.items():
                if table not in tables or not columns.issubset(
                    {column["name"] for column in inspector.get_columns(table)}
                ):
                    raise RuntimeError("Required Lounge schema is missing; startup refused.")

        try:
            async with self.engine.connect() as connection:
                revisions = list(
                    await connection.scalars(text("SELECT version_num FROM alembic_version"))
                )
                if revisions != [expected_revision]:
                    raise RuntimeError("Lounge schema revision mismatch; startup refused.")
                await connection.run_sync(check_columns)
        except SQLAlchemyError:
            raise RuntimeError("Lounge schema cannot be verified; startup refused.") from None

    async def close(self) -> None:
        await self.engine.dispose()
        self._initialized = False

    async def experiment_game_ids(self) -> set[str]:
        await self.initialize()
        async with self.sessions() as session:
            return set(await session.scalars(select(ExperimentJobRow.id)))

    async def validate_experiment_claim(self, game_id: str, token: str, *, now: datetime) -> bool:
        await self.initialize()
        async with self.sessions.begin() as session:
            job = await session.get(ExperimentJobRow, game_id)
            if job is None:
                return False
            await session.execute(
                update(ExperimentRunRow)
                .where(ExperimentRunRow.id == job.run_id)
                .values(revision=ExperimentRunRow.revision)
            )
            await session.refresh(job)
            run = await session.get(ExperimentRunRow, job.run_id)
            return bool(
                run is not None
                and run.state == "running"
                and run.deadline is not None
                and _utc(run.deadline) > now
                and job.state == "leased"
                and job.lease_token == token
                and job.lease_expires_at is not None
                and _utc(job.lease_expires_at) > now
            )

    async def create_game(
        self, game: GameSession, events: list[MatchEvent], *, experiment_token: str | None = None
    ) -> None:
        await self.initialize()
        async with self.sessions.begin() as session:
            await self._guard_experiment(session, game, datetime.now(UTC), experiment_token)
            session.add(self._match_row(game))
            # The event rows reference the match, but the ORM models intentionally
            # do not expose relationship properties. Flush the parent explicitly
            # so PostgreSQL never batches the child inserts ahead of it.
            await session.flush()
            await self._record_comparison(session, game)
            session.add_all(self._event_rows(game.id, events))

    async def _guard_experiment(self, session, game, now, token=None):
        job = await session.get(ExperimentJobRow, game.id)
        if job is None:
            if token is not None:
                raise ConcurrentGameUpdate(game.id)
            return
        await session.execute(
            update(ExperimentRunRow)
            .where(ExperimentRunRow.id == job.run_id)
            .values(revision=ExperimentRunRow.revision)
        )
        await session.refresh(job)
        run = await session.get(ExperimentRunRow, job.run_id)
        if (
            run.state != "running"
            or job.state != "leased"
            or job.lease_expires_at is None
            or _utc(job.lease_expires_at) <= now
            or run.deadline is None
            or _utc(run.deadline) <= now
            or token is None
            or token != job.lease_token
        ):
            raise ConcurrentGameUpdate(game.id)
        experiment = await session.get(ExperimentRow, run.experiment_id)
        if len(game.moves) > experiment.document["configuration"]["stops"]["max_plies"]:
            raise ConcurrentGameUpdate(game.id)

    async def record_move(
        self,
        game: GameSession,
        move: MoveRecord,
        events: list[MatchEvent],
        *,
        expected_revision: int,
        idempotency_key: str | None = None,
        request_hash: str | None = None,
        turn_lease: TurnLease | None = None,
        lease_now: datetime | None = None,
        experiment_token: str | None = None,
    ) -> None:
        await self.initialize()
        async with self.sessions.begin() as session:
            await self._guard_experiment(
                session,
                game,
                lease_now or datetime.now(UTC),
                experiment_token,
            )
            if move.actor.startswith("remote_runner:"):
                color = move.actor.split(":", 1)[1]
                player = game.white_player if color == "white" else game.black_player
                runner = await session.scalar(
                    select(RunnerSessionRow).where(RunnerSessionRow.player_id == player.player_id)
                )
                if runner is None:
                    raise RunnerTrustError("The runner session is unavailable.")
                now = lease_now or datetime.now(UTC)
                await self._lock_runner(session, runner.id, now)
                grant = await session.get(RunnerGrantRow, runner.id)
                self._check_grant(grant, game.id, game.generation, color, now)
                self._audit(session, runner.id, "move.committed", now, game.id)
            values = {**self._match_values(game), **self._cleared_lease_values()}
            statement = update(MatchRow).where(
                MatchRow.id == game.id,
                MatchRow.revision == expected_revision,
            )
            if turn_lease is not None:
                if lease_now is None:
                    raise ValueError("lease_now is required with a turn lease.")
                statement = statement.where(
                    MatchRow.turn_lease_owner == turn_lease.owner_id,
                    MatchRow.turn_lease_token == turn_lease.token,
                    MatchRow.turn_lease_position_version == turn_lease.position_version,
                    MatchRow.turn_lease_expires_at > lease_now,
                )
            result = await session.execute(statement.values(**values))
            if result.rowcount != 1:
                raise ConcurrentGameUpdate(game.id)
            session.add(
                MoveRow(
                    match_id=game.id,
                    generation=move.generation,
                    ply=move.ply,
                    uci=move.uci,
                    san=move.san,
                    actor=move.actor,
                    fen=move.fen,
                    timestamp=datetime.fromisoformat(move.timestamp),
                    elapsed_ms=move.elapsed_ms,
                    white_remaining_ms=move.white_remaining_ms,
                    black_remaining_ms=move.black_remaining_ms,
                    player_metadata=(
                        move.player_metadata.model_dump(mode="json")
                        if move.player_metadata
                        else None
                    ),
                )
            )
            await self._record_comparison(session, game)
            session.add_all(self._event_rows(game.id, events))
            if idempotency_key is not None:
                if request_hash is None:
                    raise ValueError("request_hash is required with an idempotency key.")
                session.add(
                    IdempotencyRow(
                        match_id=game.id,
                        operation="move",
                        idempotency_key=idempotency_key,
                        request_hash=request_hash,
                        applied_revision=game.revision,
                        created_at=game.updated_at,
                    )
                )
            await self._flush_mutation(session)

    async def record_action(
        self,
        game: GameSession,
        events: list[MatchEvent],
        *,
        expected_revision: int,
        experiment_token: str | None = None,
    ) -> None:
        await self.initialize()
        async with self.sessions.begin() as session:
            if experiment_token is not None:
                await self._guard_experiment(
                    session,
                    game,
                    datetime.now(UTC),
                    experiment_token,
                )
            values = {**self._match_values(game), **self._cleared_lease_values()}
            result = await session.execute(
                update(MatchRow)
                .where(MatchRow.id == game.id, MatchRow.revision == expected_revision)
                .values(**values)
            )
            if result.rowcount != 1:
                raise ConcurrentGameUpdate(game.id)
            await self._record_comparison(session, game)
            session.add_all(self._event_rows(game.id, events))
            await self._flush_mutation(session)

    async def get_idempotency_hash(
        self,
        match_id: str,
        operation: str,
        idempotency_key: str,
    ) -> str | None:
        await self.initialize()
        async with self.sessions() as session:
            return await session.scalar(
                select(IdempotencyRow.request_hash).where(
                    IdempotencyRow.match_id == match_id,
                    IdempotencyRow.operation == operation,
                    IdempotencyRow.idempotency_key == idempotency_key,
                )
            )

    async def create_runner_pairing(self, pairing: RunnerPairingRecord) -> None:
        await self.initialize()
        async with self.sessions.begin() as session:
            session.add(
                RunnerPairingRow(
                    id=pairing.pairing_id,
                    code_digest=pairing.code_digest,
                    player=pairing.player.model_dump(mode="json"),
                    session_ttl_ms=pairing.session_ttl_ms,
                    webhook_url=pairing.webhook_url,
                    created_at=datetime.fromisoformat(pairing.created_at),
                    expires_at=datetime.fromisoformat(pairing.expires_at),
                    claimed_at=(
                        datetime.fromisoformat(pairing.claimed_at)
                        if pairing.claimed_at is not None
                        else None
                    ),
                )
            )

    async def load_runner_pairing(self, pairing_id: str) -> RunnerPairingRecord | None:
        await self.initialize()
        async with self.sessions() as session:
            row = await session.get(RunnerPairingRow, pairing_id)
            if row is None:
                return None
            return self._runner_pairing_record(row)

    async def claim_runner_pairing(
        self,
        pairing_id: str,
        code_digest: str,
        runner_session: RunnerSessionRecord,
        *,
        now: datetime,
    ) -> bool:
        """Atomically consume a live pairing code and create one runner session."""

        await self.initialize()
        async with self.sessions.begin() as session:
            claimed = await session.execute(
                update(RunnerPairingRow)
                .where(
                    RunnerPairingRow.id == pairing_id,
                    RunnerPairingRow.code_digest == code_digest,
                    RunnerPairingRow.claimed_at.is_(None),
                    RunnerPairingRow.expires_at > now,
                )
                .values(claimed_at=now)
            )
            if claimed.rowcount != 1:
                return False
            session.add(
                RunnerSessionRow(
                    id=runner_session.session_id,
                    pairing_id=runner_session.pairing_id,
                    player_id=runner_session.player.player_id,
                    player=runner_session.player.model_dump(mode="json"),
                    token_digest=runner_session.token_digest,
                    issuer_digest=runner_session.issuer_digest,
                    permissions=runner_session.permissions,
                    webhook_url=runner_session.webhook_url,
                    created_at=datetime.fromisoformat(runner_session.created_at),
                    expires_at=datetime.fromisoformat(runner_session.expires_at),
                    last_heartbeat_at=datetime.fromisoformat(runner_session.last_heartbeat_at),
                    revoked_at=(
                        datetime.fromisoformat(runner_session.revoked_at)
                        if runner_session.revoked_at is not None
                        else None
                    ),
                )
            )
            self._audit(session, runner_session.session_id, "session.claimed", now)
        return True

    async def load_runner_session(self, session_id: str) -> RunnerSessionRecord | None:
        await self.initialize()
        async with self.sessions() as session:
            row = await session.get(RunnerSessionRow, session_id)
            if row is None:
                return None
            return self._runner_session_record(row)

    async def load_active_runner_session_for_player(
        self,
        player_id: str,
        *,
        now: datetime,
    ) -> RunnerSessionRecord | None:
        await self.initialize()
        async with self.sessions() as session:
            row = await session.scalar(
                select(RunnerSessionRow)
                .where(
                    RunnerSessionRow.player_id == player_id,
                    RunnerSessionRow.expires_at > now,
                    RunnerSessionRow.revoked_at.is_(None),
                )
                .order_by(RunnerSessionRow.created_at.desc())
                .limit(1)
            )
            return self._runner_session_record(row) if row is not None else None

    async def list_runner_sessions(self) -> list[RunnerSessionRecord]:
        await self.initialize()
        async with self.sessions() as session:
            rows = list(
                (
                    await session.scalars(
                        select(RunnerSessionRow).order_by(RunnerSessionRow.created_at.desc())
                    )
                ).all()
            )
        return [self._runner_session_record(row) for row in rows]

    async def touch_runner_session(self, session_id: str, *, now: datetime) -> bool:
        await self.initialize()
        async with self.sessions.begin() as session:
            result = await session.execute(
                update(RunnerSessionRow)
                .execution_options(synchronize_session=False)
                .where(
                    RunnerSessionRow.id == session_id,
                    RunnerSessionRow.expires_at > now,
                    RunnerSessionRow.revoked_at.is_(None),
                )
                .values(last_heartbeat_at=now)
            )
            return result.rowcount == 1

    @staticmethod
    def _audit(
        session: AsyncSession,
        session_id: str,
        kind: str,
        now: datetime,
        match_id: str | None = None,
    ) -> None:
        session.add(
            RunnerAuditRow(session_id=session_id, match_id=match_id, kind=kind, created_at=now)
        )

    async def _lock_runner(
        self, session: AsyncSession, session_id: str, now: datetime
    ) -> RunnerSessionRow:
        # A write lock works on SQLite and PostgreSQL and serializes grant,
        # revoke, and final move-commit checks on this session.
        result = await session.execute(
            update(RunnerSessionRow)
            .execution_options(synchronize_session=False)
            .where(
                RunnerSessionRow.id == session_id,
                RunnerSessionRow.revoked_at.is_(None),
                RunnerSessionRow.expires_at > now,
            )
            .values(last_heartbeat_at=RunnerSessionRow.last_heartbeat_at)
        )
        if result.rowcount != 1:
            raise RunnerTrustError("The runner session is expired or revoked.")
        row = await session.get(RunnerSessionRow, session_id)
        assert row is not None
        return row

    async def reserve_runner_turn(
        self,
        session_id: str,
        match_id: str,
        color: str,
        *,
        now: datetime,
        position_version: int = 0,
        match_revision: int | None = None,
    ) -> dict[str, object]:
        async with self.sessions.begin() as session:
            runner = await self._lock_runner(session, session_id, now)
            grant = await session.get(RunnerGrantRow, session_id)
            match = await session.get(MatchRow, match_id)
            if match is not None and (
                (match_revision is not None and match.revision != match_revision)
                or match.position_version != position_version
                or match.lifecycle != MatchState.RUNNING.value
                or ("white" if chess.Board(match.current_fen).turn else "black") != color
            ):
                raise RunnerTrustError("The runner turn is stale or the match is not running.")
            self._check_runner_seat(match, runner, color)
            generation = match.generation if match else 0
            if grant is None:
                settings = runner.player.get("settings", {})
                grant = RunnerGrantRow(
                    session_id=session_id,
                    match_id=match_id,
                    generation=generation,
                    color=color,
                    turns_dispatched=0,
                    max_turns=int(settings.get("max_turns", 500)),
                    expires_at=min(
                        _utc(runner.expires_at),
                        now + timedelta(milliseconds=int(settings.get("match_ttl_ms", 14_400_000))),
                    ),
                )
                session.add(grant)
                self._audit(session, session_id, "match.authorized", now, match_id)
            self._check_grant(grant, match_id, generation, color, now)
            if grant.turns_dispatched >= grant.max_turns:
                raise RunnerTrustError("The runner match turn limit has been reached.")
            grant.turns_dispatched += 1
            self._audit(session, session_id, "turn.dispatched", now, match_id)
            return {**self._grant_view(grant), "match_revision": match.revision if match else None}

    @staticmethod
    def _check_grant(
        grant: RunnerGrantRow | None, match_id: str, generation: int, color: str, now: datetime
    ) -> None:
        if grant is None or (grant.match_id, grant.generation, grant.color) != (
            match_id,
            generation,
            color,
        ):
            raise RunnerTrustError("The runner is authorized for a different match or seat.")
        if _utc(grant.expires_at) <= now:
            raise RunnerTrustError("The runner match authorization has expired.")

    async def check_runner_grant(
        self,
        session_id: str,
        match_id: str,
        color: str,
        *,
        now: datetime,
        position_version: int | None = None,
        match_revision: int | None = None,
    ) -> None:
        async with self.sessions.begin() as session:
            runner = await self._lock_runner(session, session_id, now)
            grant = await session.get(RunnerGrantRow, session_id)
            match = await session.get(MatchRow, match_id)
            self._check_runner_seat(match, runner, color)
            self._check_grant(grant, match_id, match.generation if match else 0, color, now)
            if (
                match is not None
                and position_version is not None
                and (
                    (match_revision is not None and match.revision != match_revision)
                    or match.position_version != position_version
                    or match.lifecycle != MatchState.RUNNING.value
                    or ("white" if chess.Board(match.current_fen).turn else "black") != color
                )
            ):
                raise RunnerTrustError("The runner turn is stale or the match is not running.")

    @staticmethod
    def _check_runner_seat(match: MatchRow | None, runner: RunnerSessionRow, color: str) -> None:
        if match is not None:
            player = match.white_player if color == "white" else match.black_player
            if not player or player.get("player_id") != runner.player_id:
                raise RunnerTrustError("This runner no longer controls the seat.")

    @staticmethod
    def _grant_view(grant: RunnerGrantRow) -> dict[str, object]:
        return {
            "match_id": grant.match_id,
            "generation": grant.generation,
            "color": grant.color,
            "turns_dispatched": grant.turns_dispatched,
            "max_turns": grant.max_turns,
            "expires_at": _utc(grant.expires_at).isoformat(),
        }

    async def runner_grant(self, session_id: str) -> dict[str, object] | None:
        async with self.sessions() as session:
            grant = await session.get(RunnerGrantRow, session_id)
            return self._grant_view(grant) if grant else None

    async def revoke_runner_session(self, session_id: str, *, now: datetime) -> bool:
        async with self.sessions.begin() as session:
            result = await session.execute(
                update(RunnerSessionRow)
                .execution_options(synchronize_session=False)
                .where(RunnerSessionRow.id == session_id, RunnerSessionRow.revoked_at.is_(None))
                .values(revoked_at=now)
            )
            if result.rowcount:
                grant = await session.get(RunnerGrantRow, session_id)
                self._audit(
                    session, session_id, "session.revoked", now, grant.match_id if grant else None
                )
            return await session.get(RunnerSessionRow, session_id) is not None

    async def runner_audit(self, session_id: str) -> list[dict[str, object]]:
        async with self.sessions() as session:
            rows = (
                await session.scalars(
                    select(RunnerAuditRow)
                    .where(RunnerAuditRow.session_id == session_id)
                    .order_by(RunnerAuditRow.id.desc())
                    .limit(200)
                )
            ).all()
            return [
                {
                    "sequence": row.id,
                    "kind": row.kind,
                    "match_id": row.match_id,
                    "timestamp": _utc(row.created_at).isoformat(),
                }
                for row in reversed(rows)
            ]

    async def acquire_turn_lease(
        self,
        match_id: str,
        owner_id: str,
        position_version: int,
        *,
        now: datetime,
        lease_ms: int,
    ) -> TurnLease:
        await self.initialize()
        token = str(uuid4())
        expires_at = now + timedelta(milliseconds=lease_ms)
        async with self.sessions.begin() as session:
            result = await session.execute(
                update(MatchRow)
                .where(
                    MatchRow.id == match_id,
                    MatchRow.lifecycle == MatchState.RUNNING.value,
                    MatchRow.position_version == position_version,
                    or_(
                        MatchRow.turn_lease_expires_at.is_(None),
                        MatchRow.turn_lease_expires_at <= now,
                    ),
                )
                .values(
                    turn_lease_owner=owner_id,
                    turn_lease_token=token,
                    turn_lease_position_version=position_version,
                    turn_lease_acquired_at=now,
                    turn_lease_expires_at=expires_at,
                )
            )
            if result.rowcount != 1:
                raise TurnLeaseUnavailable(
                    "The turn is stale, unavailable, or already leased by another worker."
                )
        return TurnLease(
            match_id=match_id,
            owner_id=owner_id,
            token=token,
            position_version=position_version,
            acquired_at=now.isoformat(),
            expires_at=expires_at.isoformat(),
        )

    async def renew_turn_lease(
        self,
        lease: TurnLease,
        *,
        now: datetime,
        lease_ms: int,
    ) -> TurnLease:
        await self.initialize()
        expires_at = now + timedelta(milliseconds=lease_ms)
        async with self.sessions.begin() as session:
            result = await session.execute(
                update(MatchRow)
                .where(
                    MatchRow.id == lease.match_id,
                    MatchRow.position_version == lease.position_version,
                    MatchRow.turn_lease_owner == lease.owner_id,
                    MatchRow.turn_lease_token == lease.token,
                    MatchRow.turn_lease_position_version == lease.position_version,
                    MatchRow.turn_lease_expires_at > now,
                )
                .values(turn_lease_expires_at=expires_at)
            )
            if result.rowcount != 1:
                raise TurnLeaseUnavailable("The turn lease expired or no longer owns this turn.")
        return lease.model_copy(update={"expires_at": expires_at.isoformat()})

    async def release_turn_lease(self, lease: TurnLease) -> bool:
        await self.initialize()
        async with self.sessions.begin() as session:
            result = await session.execute(
                update(MatchRow)
                .where(
                    MatchRow.id == lease.match_id,
                    MatchRow.turn_lease_owner == lease.owner_id,
                    MatchRow.turn_lease_token == lease.token,
                    MatchRow.turn_lease_position_version == lease.position_version,
                )
                .values(**self._cleared_lease_values())
            )
            return result.rowcount == 1

    async def load_game(self, game_id: str) -> GameSession | None:
        await self.initialize()
        async with self.sessions() as session:
            row = await session.get(MatchRow, game_id)
            if row is None:
                return None
            moves = list(
                (
                    await session.scalars(
                        select(MoveRow)
                        .where(
                            MoveRow.match_id == game_id,
                            MoveRow.generation == row.generation,
                        )
                        .order_by(MoveRow.ply)
                    )
                ).all()
            )
            game = self._restore_game(row, moves)
            comparison = await session.get(ComparisonGameRow, (game.id, game.generation))
            game.comparison_snapshot = comparison.identity if comparison else None
            return game

    async def latest_live_match_ids(self, limit: int | None = None) -> list[str]:
        """Most recently updated running or paused exhibition matches (not batch jobs)."""
        await self.initialize()
        async with self.sessions() as session:
            return list(
                (
                    await session.scalars(
                        select(MatchRow.id)
                        .where(
                            MatchRow.lifecycle.in_(
                                [MatchState.RUNNING.value, MatchState.PAUSED.value]
                            ),
                            MatchRow.id.not_in(select(ExperimentJobRow.id)),
                        )
                        .order_by(MatchRow.updated_at.desc())
                        .limit(limit)
                    )
                ).all()
            )

    async def load_revision(self, game_id: str) -> tuple[int, int] | None:
        await self.initialize()
        async with self.sessions() as session:
            row = (
                await session.execute(
                    select(MatchRow.generation, MatchRow.revision).where(MatchRow.id == game_id)
                )
            ).one_or_none()
            return (row.generation, row.revision) if row is not None else None

    async def load_position_marker(self, game_id: str) -> tuple[int, int] | None:
        await self.initialize()
        async with self.sessions() as session:
            row = (
                await session.execute(
                    select(MatchRow.generation, MatchRow.position_version).where(
                        MatchRow.id == game_id
                    )
                )
            ).one_or_none()
            return (row.generation, row.position_version) if row is not None else None

    async def load_recoverable_games(self) -> list[GameSession]:
        await self.initialize()
        async with self.sessions() as session:
            ids = list(
                (
                    await session.scalars(
                        select(MatchRow.id).where(
                            MatchRow.lifecycle.in_(
                                [
                                    MatchState.CREATED.value,
                                    MatchState.WAITING.value,
                                    MatchState.RUNNING.value,
                                    MatchState.PAUSED.value,
                                ]
                            )
                        )
                    )
                ).all()
            )
        games: list[GameSession] = []
        for game_id in ids:
            game = await self.load_game(game_id)
            if game is not None:
                games.append(game)
        return games

    async def list_events(self, game_id: str) -> list[MatchEvent] | None:
        await self.initialize()
        async with self.sessions() as session:
            if await session.get(MatchRow, game_id) is None:
                return None
            rows = list(
                (
                    await session.scalars(
                        select(EventRow)
                        .where(EventRow.match_id == game_id)
                        .order_by(EventRow.sequence)
                    )
                ).all()
            )
        return [
            MatchEvent(
                sequence=row.sequence,
                type=row.event_type,
                position_version=row.position_version,
                payload=row.payload,
                timestamp=_utc(row.created_at).isoformat(),
            )
            for row in rows
        ]

    async def clear(self) -> None:
        """Delete test data while preserving the schema."""
        await self.initialize()
        async with self.sessions.begin() as session:
            await session.execute(delete(RunnerAuditRow))
            await session.execute(delete(RunnerGrantRow))
            await session.execute(delete(RunnerSessionRow))
            await session.execute(delete(RunnerPairingRow))
            await session.execute(delete(IdempotencyRow))
            await session.execute(delete(EventRow))
            await session.execute(delete(MoveRow))
            await session.execute(delete(ComparisonGameRow))
            await session.execute(delete(MatchRow))

    async def _record_comparison(self, session: AsyncSession, game: GameSession) -> None:
        row = await session.get(ComparisonGameRow, (game.id, game.generation))
        if row is None:
            # Legacy games with no original snapshot remain explicitly unknown.
            # Only creation/reset supplies a snapshot; later legacy mutations do not
            # reconstruct the original identity from possibly changed seats.
            if game.comparison_snapshot is None:
                return
            session.add(
                ComparisonGameRow(
                    match_id=game.id,
                    generation=game.generation,
                    identity=game.comparison_snapshot,
                    outcome=comparison_outcome(game),
                )
            )
        else:
            row.outcome = comparison_outcome(game)

    async def _flush_mutation(self, session: AsyncSession) -> None:
        """Flush once inside the transaction; tests replace this to inject a crash."""
        await session.flush()

    @staticmethod
    def _match_row(game: GameSession) -> MatchRow:
        return MatchRow(id=game.id, **DatabaseStore._match_values(game))

    @staticmethod
    def _match_values(game: GameSession) -> dict[str, object]:
        return {
            "lifecycle": game.lifecycle.value,
            "opponent": game.opponent.value,
            "stockfish_elo": game.stockfish_elo,
            "engine_move_time_ms": game.engine_move_time_ms,
            "initial_time_ms": game.initial_time_ms,
            "increment_ms": game.increment_ms,
            "white_remaining_ms": game._stored_remaining("white"),
            "black_remaining_ms": game._stored_remaining("black"),
            "turn_started_at": game.turn_started_at,
            "timed_out_by": game.timed_out_by,
            "initial_fen": game.initial_fen,
            "current_fen": game.board.fen(),
            "position_version": game.version,
            "revision": game.revision,
            "generation": game.generation,
            "event_sequence": game.event_sequence,
            "resigned_by": game.resigned_by,
            "draw_reason": game.draw_reason,
            "adjudicated_result": game.adjudicated_result,
            "engine_summary": (
                game.engine_summary.model_dump(mode="json") if game.engine_summary else None
            ),
            "white_player": (
                game.white_player.model_dump(mode="json") if game.white_player else None
            ),
            "black_player": (
                game.black_player.model_dump(mode="json") if game.black_player else None
            ),
            "seat_history": [change.model_dump(mode="json") for change in game.seat_history],
            "consultations": [item.model_dump(mode="json") for item in game.consultations],
            "created_at": game.created_at,
            "updated_at": game.updated_at,
        }

    @staticmethod
    def _cleared_lease_values() -> dict[str, object | None]:
        return {
            "turn_lease_owner": None,
            "turn_lease_token": None,
            "turn_lease_position_version": None,
            "turn_lease_acquired_at": None,
            "turn_lease_expires_at": None,
        }

    @staticmethod
    def _event_rows(game_id: str, events: list[MatchEvent]) -> list[EventRow]:
        return [
            EventRow(
                match_id=game_id,
                sequence=event.sequence,
                event_type=event.type,
                position_version=event.position_version,
                payload=event.payload,
                created_at=datetime.fromisoformat(event.timestamp),
            )
            for event in events
        ]

    @staticmethod
    def _runner_pairing_record(row: RunnerPairingRow) -> RunnerPairingRecord:
        return RunnerPairingRecord(
            pairing_id=row.id,
            code_digest=row.code_digest,
            player=PlayerConfiguration.model_validate(row.player),
            session_ttl_ms=row.session_ttl_ms,
            webhook_url=row.webhook_url,
            created_at=_utc(row.created_at).isoformat(),
            expires_at=_utc(row.expires_at).isoformat(),
            claimed_at=_utc(row.claimed_at).isoformat() if row.claimed_at else None,
        )

    @staticmethod
    def _runner_session_record(row: RunnerSessionRow) -> RunnerSessionRecord:
        return RunnerSessionRecord(
            session_id=row.id,
            pairing_id=row.pairing_id,
            player=PlayerConfiguration.model_validate(row.player),
            token_digest=row.token_digest,
            issuer_digest=row.issuer_digest,
            permissions=list(row.permissions),
            webhook_url=row.webhook_url,
            created_at=_utc(row.created_at).isoformat(),
            expires_at=_utc(row.expires_at).isoformat(),
            last_heartbeat_at=_utc(row.last_heartbeat_at).isoformat(),
            revoked_at=_utc(row.revoked_at).isoformat() if row.revoked_at else None,
        )

    @staticmethod
    def _restore_game(row: MatchRow, rows: list[MoveRow]) -> GameSession:
        board = chess.Board(row.initial_fen)
        moves: list[MoveRecord] = []
        for persisted in rows:
            board.push_uci(persisted.uci)
            if board.fen() != persisted.fen:
                raise RuntimeError(
                    f"Persisted move {persisted.ply} for {row.id} does not match its FEN."
                )
            moves.append(
                MoveRecord(
                    generation=persisted.generation,
                    ply=persisted.ply,
                    uci=persisted.uci,
                    san=persisted.san,
                    actor=persisted.actor,
                    fen=persisted.fen,
                    timestamp=_utc(persisted.timestamp).isoformat(),
                    elapsed_ms=persisted.elapsed_ms,
                    white_remaining_ms=persisted.white_remaining_ms,
                    black_remaining_ms=persisted.black_remaining_ms,
                    player_metadata=(
                        PlayerMoveMetadata.model_validate(persisted.player_metadata)
                        if persisted.player_metadata
                        else None
                    ),
                )
            )
        if board.fen() != row.current_fen:
            raise RuntimeError(f"Persisted projection for {row.id} does not match move history.")
        return GameSession(
            id=row.id,
            opponent=OpponentKind(row.opponent),
            stockfish_elo=row.stockfish_elo,
            engine_move_time_ms=row.engine_move_time_ms,
            initial_time_ms=row.initial_time_ms,
            increment_ms=row.increment_ms,
            board=board,
            initial_fen=row.initial_fen,
            lifecycle=MatchState(row.lifecycle),
            version=row.position_version,
            revision=row.revision,
            generation=row.generation,
            event_sequence=row.event_sequence,
            moves=moves,
            created_at=_utc(row.created_at),
            updated_at=_utc(row.updated_at),
            resigned_by=row.resigned_by,
            draw_reason=row.draw_reason,
            adjudicated_result=row.adjudicated_result,
            engine_summary=(
                EngineSummary.model_validate(row.engine_summary) if row.engine_summary else None
            ),
            seat_history=[SeatChange.model_validate(change) for change in (row.seat_history or [])],
            consultations=[Consultation.model_validate(item) for item in (row.consultations or [])],
            white_remaining_ms=row.white_remaining_ms,
            black_remaining_ms=row.black_remaining_ms,
            turn_started_at=(
                _utc(row.turn_started_at) if row.turn_started_at is not None else None
            ),
            timed_out_by=row.timed_out_by,
            white_player=(
                PlayerConfiguration.model_validate(row.white_player) if row.white_player else None
            ),
            black_player=(
                PlayerConfiguration.model_validate(row.black_player) if row.black_player else None
            ),
        )
