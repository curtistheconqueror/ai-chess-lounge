from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, datetime

import chess
from fastapi import WebSocket

from .domain import ClockExpired, GameSession, StalePosition
from .engine import StockfishService
from .models import CreateGameRequest, GameSnapshot, MatchEvent, MatchState, OpponentKind
from .persistence import ConcurrentGameUpdate, DatabaseStore


class GameNotFound(KeyError):
    pass


class GameManager:
    def __init__(
        self,
        engine: StockfishService | None = None,
        store: DatabaseStore | None = None,
        clock: Callable[[], datetime] | None = None,
        *,
        schedule_timeouts: bool = True,
    ) -> None:
        self.engine = engine or StockfishService()
        self.store = store or DatabaseStore()
        self.games: dict[str, GameSession] = {}
        self._game_locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._listeners: defaultdict[str, set[WebSocket]] = defaultdict(set)
        self._clock = clock or (lambda: datetime.now(UTC))
        self._schedule_timeouts_enabled = schedule_timeouts
        self._timeout_tasks: dict[str, asyncio.Task[None]] = {}
        self._closed = False

    async def start(self) -> None:
        self._closed = False
        await self.store.initialize()
        for game in await self.store.load_recoverable_games():
            self.games[game.id] = game
            self._schedule_timeout(game)
        for game in tuple(self.games.values()):
            if (
                game.lifecycle is MatchState.RUNNING
                and game.opponent is OpponentKind.STOCKFISH
                and game.board.turn is chess.BLACK
            ):
                try:
                    async with self._game_locks[game.id]:
                        await self._complete_engine_turn(game)
                except RuntimeError:
                    # A recovered match remains valid and can be resumed when the engine returns.
                    continue

    async def create(self, request: CreateGameRequest) -> GameSession:
        game = GameSession(
            opponent=request.opponent,
            stockfish_elo=request.stockfish_elo,
            engine_move_time_ms=request.engine_move_time_ms,
            initial_time_ms=request.initial_time_ms,
            increment_ms=request.increment_ms,
        )
        if game.opponent is OpponentKind.STOCKFISH:
            game.engine_summary = await self.engine.summary(
                game.stockfish_elo, game.engine_move_time_ms
            )
        now = self._clock()
        events = [
            game.event(
                "match.created",
                {
                    "opponent": game.opponent.value,
                    "stockfish_elo": game.stockfish_elo,
                    "engine_move_time_ms": game.engine_move_time_ms,
                    "initial_time_ms": game.initial_time_ms,
                    "increment_ms": game.increment_ms,
                },
                now=now,
            )
        ]
        game.start(now=now)
        events.append(game.event("match.started", self._clock_payload(game, now), now=now))
        await self.store.create_game(game, events)
        self.games[game.id] = game
        self._schedule_timeout(game)
        return game

    async def get(self, game_id: str) -> GameSession:
        game = self.games.get(game_id)
        if game is not None:
            return game
        game = await self.store.load_game(game_id)
        if game is None:
            raise GameNotFound(game_id)
        self.games[game_id] = game
        return game

    async def snapshot(self, game_id: str) -> GameSnapshot:
        game = await self.get(game_id)
        async with self._game_locks[game_id]:
            try:
                await self._expire_locked(game, self._clock())
            except ConcurrentGameUpdate:
                game = self.games[game_id]
            return game.snapshot(now=self._clock())

    async def make_human_move(self, game_id: str, uci: str, position_version: int) -> GameSnapshot:
        game = await self.get(game_id)
        async with self._game_locks[game_id]:
            expected_revision = game.revision
            now = self._clock()
            if await self._expire_locked(game, now, expected_revision=expected_revision):
                raise ClockExpired(f"{game.timed_out_by.title()} lost on time.")
            move = game.apply_uci(
                uci,
                actor="human:white",
                position_version=position_version,
                now=now,
            )
            events = [game.event("move.accepted", self._move_payload(move), now=now)]
            if game.lifecycle is MatchState.COMPLETED:
                events.append(game.event("match.completed", {"result": game.result}, now=now))
            try:
                await self.store.record_move(
                    game,
                    move,
                    events,
                    expected_revision=expected_revision,
                )
            except ConcurrentGameUpdate as exc:
                await self._reload(game_id)
                raise StalePosition("The match changed while this move was submitted.") from exc
            self._schedule_timeout(game)
            await self.broadcast(game, now=now)
            if (
                game.opponent is OpponentKind.STOCKFISH
                and game.lifecycle is MatchState.RUNNING
                and game.board.turn is chess.BLACK
            ):
                await self._complete_engine_turn(game)
            return game.snapshot(now=self._clock())

    async def reset(self, game_id: str) -> GameSnapshot:
        game = await self.get(game_id)
        async with self._game_locks[game_id]:
            expected_revision = game.revision
            now = self._clock()
            game.reset(now=now)
            payload = {"generation": game.generation, **self._clock_payload(game, now)}
            event = game.event("match.reset", payload, now=now)
            await self._record_action(game, [event], expected_revision)
            self._schedule_timeout(game)
            snapshot = game.snapshot(now=now)
            await self.broadcast(game, now=now)
            return snapshot

    async def resign(self, game_id: str, color: str = "white") -> GameSnapshot:
        game = await self.get(game_id)
        async with self._game_locks[game_id]:
            expected_revision = game.revision
            now = self._clock()
            if await self._expire_locked(game, now, expected_revision=expected_revision):
                raise ClockExpired(f"{game.timed_out_by.title()} lost on time.")
            game.resign(color, now=now)
            events = [
                game.event(
                    "match.resigned",
                    {
                        "color": color,
                        "result": game.result,
                        **self._clock_payload(game, now),
                    },
                    now=now,
                ),
                game.event("match.completed", {"result": game.result}, now=now),
            ]
            await self._record_action(game, events, expected_revision)
            self._cancel_timeout(game_id)
            snapshot = game.snapshot(now=now)
            await self.broadcast(game, now=now)
            return snapshot

    async def pause(self, game_id: str) -> GameSnapshot:
        return await self._transition(game_id, MatchState.PAUSED, "match.paused")

    async def resume(self, game_id: str) -> GameSnapshot:
        snapshot = await self._transition(game_id, MatchState.RUNNING, "match.resumed")
        game = await self.get(game_id)
        if game.opponent is OpponentKind.STOCKFISH and game.board.turn is chess.BLACK:
            async with self._game_locks[game_id]:
                await self._complete_engine_turn(game)
                now = self._clock()
                snapshot = game.snapshot(now=now)
                await self.broadcast(game, now=now)
        return snapshot

    async def abort(self, game_id: str) -> GameSnapshot:
        return await self._transition(game_id, MatchState.ABORTED, "match.aborted")

    async def adjudicate(self, game_id: str, result: str) -> GameSnapshot:
        game = await self.get(game_id)
        async with self._game_locks[game_id]:
            expected_revision = game.revision
            now = self._clock()
            if await self._expire_locked(game, now, expected_revision=expected_revision):
                raise ClockExpired(f"{game.timed_out_by.title()} lost on time.")
            game.adjudicate(result, now=now)
            event = game.event(
                "match.adjudicated",
                {"result": result, **self._clock_payload(game, now)},
                now=now,
            )
            await self._record_action(game, [event], expected_revision)
            self._cancel_timeout(game_id)
            snapshot = game.snapshot(now=now)
            await self.broadcast(game, now=now)
            return snapshot

    async def events(self, game_id: str) -> list[MatchEvent]:
        events = await self.store.list_events(game_id)
        if events is None:
            raise GameNotFound(game_id)
        return events

    async def subscribe(self, game_id: str, websocket: WebSocket) -> None:
        snapshot = await self.snapshot(game_id)
        await websocket.accept()
        self._listeners[game_id].add(websocket)
        await websocket.send_json({"type": "snapshot", "payload": snapshot.model_dump(mode="json")})

    def unsubscribe(self, game_id: str, websocket: WebSocket) -> None:
        self._listeners[game_id].discard(websocket)

    async def broadcast(self, game: GameSession, *, now: datetime | None = None) -> None:
        message = {
            "type": "snapshot",
            "payload": game.snapshot(now=now or self._clock()).model_dump(mode="json"),
        }
        disconnected: list[WebSocket] = []
        for websocket in tuple(self._listeners[game.id]):
            try:
                await websocket.send_json(message)
            except Exception:
                disconnected.append(websocket)
        for websocket in disconnected:
            self.unsubscribe(game.id, websocket)

    async def close(self) -> None:
        self._closed = True
        tasks = list(self._timeout_tasks.values())
        self._timeout_tasks.clear()
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        await self.engine.close()
        await self.store.close()

    async def _complete_engine_turn(self, game: GameSession) -> None:
        expected_revision = game.revision
        now = self._clock()
        if await self._expire_locked(game, now, expected_revision=expected_revision):
            return
        engine_move = await self.engine.choose_move(
            game.board,
            target_elo=game.stockfish_elo,
            move_time_ms=game.engine_move_time_ms,
        )
        now = self._clock()
        if await self._expire_locked(game, now, expected_revision=expected_revision):
            return
        move = game.apply_uci(engine_move.uci, actor="stockfish:black", now=now)
        move.elapsed_ms = engine_move.elapsed_ms
        events = [game.event("move.accepted", self._move_payload(move), now=now)]
        if game.lifecycle is MatchState.COMPLETED:
            events.append(game.event("match.completed", {"result": game.result}, now=now))
        try:
            await self.store.record_move(
                game,
                move,
                events,
                expected_revision=expected_revision,
            )
        except ConcurrentGameUpdate:
            await self._reload(game.id)
            raise
        self._schedule_timeout(game)
        await self.broadcast(game, now=now)

    async def _transition(
        self,
        game_id: str,
        target: MatchState,
        event_type: str,
    ) -> GameSnapshot:
        game = await self.get(game_id)
        async with self._game_locks[game_id]:
            expected_revision = game.revision
            now = self._clock()
            if await self._expire_locked(game, now, expected_revision=expected_revision):
                raise ClockExpired(f"{game.timed_out_by.title()} lost on time.")
            game.transition(target, now=now)
            event = game.event(event_type, self._clock_payload(game, now), now=now)
            await self._record_action(game, [event], expected_revision)
            if target is MatchState.RUNNING:
                self._schedule_timeout(game)
            else:
                self._cancel_timeout(game_id)
            snapshot = game.snapshot(now=now)
            await self.broadcast(game, now=now)
            return snapshot

    async def expire_due_games(self) -> list[str]:
        expired: list[str] = []
        for game_id in tuple(self.games):
            game = await self.get(game_id)
            async with self._game_locks[game_id]:
                try:
                    if await self._expire_locked(game, self._clock()):
                        expired.append(game_id)
                except ConcurrentGameUpdate:
                    continue
        return expired

    async def _expire_locked(
        self,
        game: GameSession,
        now: datetime,
        *,
        expected_revision: int | None = None,
    ) -> bool:
        expected = game.revision if expected_revision is None else expected_revision
        if not game.expire_if_needed(now):
            return False
        payload = self._clock_payload(game, now)
        payload.update({"color": game.timed_out_by, "result": game.result})
        events = [
            game.event("clock.timeout", payload, now=now),
            game.event(
                "match.completed",
                {"result": game.result, "reason": "timeout"},
                now=now,
            ),
        ]
        await self._record_action(game, events, expected)
        self._cancel_timeout(game.id)
        await self.broadcast(game, now=now)
        return True

    def _schedule_timeout(self, game: GameSession) -> None:
        self._cancel_timeout(game.id)
        if not self._schedule_timeouts_enabled or self._closed:
            return
        deadline = game.deadline_at()
        if deadline is None:
            return
        self._timeout_tasks[game.id] = asyncio.create_task(
            self._timeout_after(game.id, game.revision, deadline)
        )

    def _cancel_timeout(self, game_id: str) -> None:
        task = self._timeout_tasks.pop(game_id, None)
        if task is not None and task is not asyncio.current_task():
            task.cancel()

    async def _timeout_after(
        self,
        game_id: str,
        expected_revision: int,
        deadline: datetime,
    ) -> None:
        delay = max(0.0, (deadline - self._clock()).total_seconds())
        try:
            await asyncio.sleep(delay)
            if self._closed:
                return
            game = await self.get(game_id)
            async with self._game_locks[game_id]:
                if game.revision != expected_revision:
                    self._schedule_timeout(game)
                    return
                try:
                    expired = await self._expire_locked(
                        game,
                        self._clock(),
                        expected_revision=expected_revision,
                    )
                except ConcurrentGameUpdate:
                    return
                if not expired:
                    self._schedule_timeout(game)
        except asyncio.CancelledError:
            return

    @staticmethod
    def _clock_payload(game: GameSession, now: datetime) -> dict[str, object]:
        clock = game.clock_snapshot(now)
        return {
            "white_remaining_ms": clock.white_remaining_ms,
            "black_remaining_ms": clock.black_remaining_ms,
            "deadline_at": clock.deadline_at,
        }

    async def _record_action(
        self,
        game: GameSession,
        events: list[MatchEvent],
        expected_revision: int,
    ) -> None:
        try:
            await self.store.record_action(
                game,
                events,
                expected_revision=expected_revision,
            )
        except ConcurrentGameUpdate:
            await self._reload(game.id)
            raise

    async def _reload(self, game_id: str) -> GameSession:
        game = await self.store.load_game(game_id)
        if game is None:
            self.games.pop(game_id, None)
            raise GameNotFound(game_id)
        self.games[game_id] = game
        self._schedule_timeout(game)
        return game

    @staticmethod
    def _move_payload(move) -> dict[str, object]:
        return {
            "generation": move.generation,
            "ply": move.ply,
            "uci": move.uci,
            "san": move.san,
            "actor": move.actor,
            "elapsed_ms": move.elapsed_ms,
            "white_remaining_ms": move.white_remaining_ms,
            "black_remaining_ms": move.black_remaining_ms,
        }
