from __future__ import annotations

import asyncio
from collections import defaultdict

import chess
from fastapi import WebSocket

from .domain import GameSession, StalePosition
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
    ) -> None:
        self.engine = engine or StockfishService()
        self.store = store or DatabaseStore()
        self.games: dict[str, GameSession] = {}
        self._game_locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._listeners: defaultdict[str, set[WebSocket]] = defaultdict(set)

    async def start(self) -> None:
        await self.store.initialize()
        for game in await self.store.load_recoverable_games():
            self.games[game.id] = game
        for game in tuple(self.games.values()):
            if (
                game.lifecycle is MatchState.RUNNING
                and game.opponent is OpponentKind.STOCKFISH
                and game.board.turn is chess.BLACK
            ):
                try:
                    await self._complete_engine_turn(game)
                except RuntimeError:
                    # A recovered match remains valid and can be resumed when the engine returns.
                    continue

    async def create(self, request: CreateGameRequest) -> GameSession:
        game = GameSession(
            opponent=request.opponent,
            stockfish_elo=request.stockfish_elo,
            engine_move_time_ms=request.engine_move_time_ms,
        )
        if game.opponent is OpponentKind.STOCKFISH:
            game.engine_summary = await self.engine.summary(
                game.stockfish_elo, game.engine_move_time_ms
            )
        events = [
            game.event(
                "match.created",
                {
                    "opponent": game.opponent.value,
                    "stockfish_elo": game.stockfish_elo,
                    "engine_move_time_ms": game.engine_move_time_ms,
                },
            )
        ]
        game.start()
        events.append(game.event("match.started"))
        await self.store.create_game(game, events)
        self.games[game.id] = game
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

    async def make_human_move(self, game_id: str, uci: str, position_version: int) -> GameSnapshot:
        game = await self.get(game_id)
        async with self._game_locks[game_id]:
            expected_revision = game.revision
            move = game.apply_uci(
                uci,
                actor="human:white",
                position_version=position_version,
            )
            events = [game.event("move.accepted", self._move_payload(move))]
            if game.lifecycle is MatchState.COMPLETED:
                events.append(game.event("match.completed", {"result": game.result}))
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
            await self.broadcast(game)
            if (
                game.opponent is OpponentKind.STOCKFISH
                and game.lifecycle is MatchState.RUNNING
                and game.board.turn is chess.BLACK
            ):
                await self._complete_engine_turn(game)
            snapshot = game.snapshot()
            await self.broadcast(game)
            return snapshot

    async def reset(self, game_id: str) -> GameSnapshot:
        game = await self.get(game_id)
        async with self._game_locks[game_id]:
            expected_revision = game.revision
            game.reset()
            event = game.event("match.reset", {"generation": game.generation})
            await self._record_action(game, [event], expected_revision)
            snapshot = game.snapshot()
            await self.broadcast(game)
            return snapshot

    async def resign(self, game_id: str, color: str = "white") -> GameSnapshot:
        game = await self.get(game_id)
        async with self._game_locks[game_id]:
            expected_revision = game.revision
            game.resign(color)
            events = [
                game.event("match.resigned", {"color": color, "result": game.result}),
                game.event("match.completed", {"result": game.result}),
            ]
            await self._record_action(game, events, expected_revision)
            snapshot = game.snapshot()
            await self.broadcast(game)
            return snapshot

    async def pause(self, game_id: str) -> GameSnapshot:
        return await self._transition(game_id, MatchState.PAUSED, "match.paused")

    async def resume(self, game_id: str) -> GameSnapshot:
        snapshot = await self._transition(game_id, MatchState.RUNNING, "match.resumed")
        game = await self.get(game_id)
        if game.opponent is OpponentKind.STOCKFISH and game.board.turn is chess.BLACK:
            async with self._game_locks[game_id]:
                await self._complete_engine_turn(game)
                snapshot = game.snapshot()
                await self.broadcast(game)
        return snapshot

    async def abort(self, game_id: str) -> GameSnapshot:
        return await self._transition(game_id, MatchState.ABORTED, "match.aborted")

    async def adjudicate(self, game_id: str, result: str) -> GameSnapshot:
        game = await self.get(game_id)
        async with self._game_locks[game_id]:
            expected_revision = game.revision
            game.adjudicate(result)
            event = game.event("match.adjudicated", {"result": result})
            await self._record_action(game, [event], expected_revision)
            snapshot = game.snapshot()
            await self.broadcast(game)
            return snapshot

    async def events(self, game_id: str) -> list[MatchEvent]:
        events = await self.store.list_events(game_id)
        if events is None:
            raise GameNotFound(game_id)
        return events

    async def subscribe(self, game_id: str, websocket: WebSocket) -> None:
        game = await self.get(game_id)
        await websocket.accept()
        self._listeners[game_id].add(websocket)
        await websocket.send_json(
            {"type": "snapshot", "payload": game.snapshot().model_dump(mode="json")}
        )

    def unsubscribe(self, game_id: str, websocket: WebSocket) -> None:
        self._listeners[game_id].discard(websocket)

    async def broadcast(self, game: GameSession) -> None:
        message = {
            "type": "snapshot",
            "payload": game.snapshot().model_dump(mode="json"),
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
        await self.engine.close()
        await self.store.close()

    async def _complete_engine_turn(self, game: GameSession) -> None:
        expected_revision = game.revision
        engine_move = await self.engine.choose_move(
            game.board,
            target_elo=game.stockfish_elo,
            move_time_ms=game.engine_move_time_ms,
        )
        move = game.apply_uci(engine_move.uci, actor="stockfish:black")
        move.elapsed_ms = engine_move.elapsed_ms
        events = [game.event("move.accepted", self._move_payload(move))]
        if game.lifecycle is MatchState.COMPLETED:
            events.append(game.event("match.completed", {"result": game.result}))
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

    async def _transition(
        self,
        game_id: str,
        target: MatchState,
        event_type: str,
    ) -> GameSnapshot:
        game = await self.get(game_id)
        async with self._game_locks[game_id]:
            expected_revision = game.revision
            game.transition(target)
            event = game.event(event_type)
            await self._record_action(game, [event], expected_revision)
            snapshot = game.snapshot()
            await self.broadcast(game)
            return snapshot

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
        }
