from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

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
    select,
    text,
    update,
)
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.pool import StaticPool

from .domain import GameSession
from .models import EngineSummary, MatchEvent, MatchState, MoveRecord, OpponentKind

DEFAULT_DATABASE_URL = "sqlite+aiosqlite:///./.runtime/lounge.db"


class ConcurrentGameUpdate(RuntimeError):
    """Raised when another process changed a match before this write committed."""


class Base(DeclarativeBase):
    pass


class MatchRow(Base):
    __tablename__ = "matches"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    lifecycle: Mapped[str] = mapped_column(String(24), nullable=False)
    opponent: Mapped[str] = mapped_column(String(24), nullable=False)
    stockfish_elo: Mapped[int] = mapped_column(Integer, nullable=False)
    engine_move_time_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    initial_fen: Mapped[str] = mapped_column(Text, nullable=False)
    current_fen: Mapped[str] = mapped_column(Text, nullable=False)
    position_version: Mapped[int] = mapped_column(Integer, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    generation: Mapped[int] = mapped_column(Integer, nullable=False)
    event_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    resigned_by: Mapped[str | None] = mapped_column(String(5), nullable=True)
    adjudicated_result: Mapped[str | None] = mapped_column(String(7), nullable=True)
    engine_summary: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


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
                    text(
                        "INSERT INTO alembic_version (version_num) VALUES ('0001_durable_matches')"
                    )
                )
        self._initialized = True

    async def close(self) -> None:
        await self.engine.dispose()
        self._initialized = False

    async def create_game(self, game: GameSession, events: list[MatchEvent]) -> None:
        await self.initialize()
        async with self.sessions.begin() as session:
            session.add(self._match_row(game))
            session.add_all(self._event_rows(game.id, events))

    async def record_move(
        self,
        game: GameSession,
        move: MoveRecord,
        events: list[MatchEvent],
        *,
        expected_revision: int,
    ) -> None:
        await self.initialize()
        async with self.sessions.begin() as session:
            result = await session.execute(
                update(MatchRow)
                .where(MatchRow.id == game.id, MatchRow.revision == expected_revision)
                .values(**self._match_values(game))
            )
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
                )
            )
            session.add_all(self._event_rows(game.id, events))

    async def record_action(
        self,
        game: GameSession,
        events: list[MatchEvent],
        *,
        expected_revision: int,
    ) -> None:
        await self.initialize()
        async with self.sessions.begin() as session:
            result = await session.execute(
                update(MatchRow)
                .where(MatchRow.id == game.id, MatchRow.revision == expected_revision)
                .values(**self._match_values(game))
            )
            if result.rowcount != 1:
                raise ConcurrentGameUpdate(game.id)
            session.add_all(self._event_rows(game.id, events))

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
            return self._restore_game(row, moves)

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
            await session.execute(delete(EventRow))
            await session.execute(delete(MoveRow))
            await session.execute(delete(MatchRow))

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
            "initial_fen": game.initial_fen,
            "current_fen": game.board.fen(),
            "position_version": game.version,
            "revision": game.revision,
            "generation": game.generation,
            "event_sequence": game.event_sequence,
            "resigned_by": game.resigned_by,
            "adjudicated_result": game.adjudicated_result,
            "engine_summary": (
                game.engine_summary.model_dump(mode="json") if game.engine_summary else None
            ),
            "created_at": game.created_at,
            "updated_at": game.updated_at,
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
                )
            )
        if board.fen() != row.current_fen:
            raise RuntimeError(f"Persisted projection for {row.id} does not match move history.")
        return GameSession(
            id=row.id,
            opponent=OpponentKind(row.opponent),
            stockfish_elo=row.stockfish_elo,
            engine_move_time_ms=row.engine_move_time_ms,
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
            adjudicated_result=row.adjudicated_result,
            engine_summary=(
                EngineSummary.model_validate(row.engine_summary) if row.engine_summary else None
            ),
        )
