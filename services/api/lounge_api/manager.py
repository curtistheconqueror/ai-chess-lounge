from __future__ import annotations

import asyncio
from collections import defaultdict

import chess
from fastapi import WebSocket

from .domain import GameSession
from .engine import StockfishService
from .models import CreateGameRequest, GameSnapshot, OpponentKind


class GameNotFound(KeyError):
    pass


class GameManager:
    def __init__(self, engine: StockfishService | None = None) -> None:
        self.engine = engine or StockfishService()
        self.games: dict[str, GameSession] = {}
        self._game_locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._listeners: defaultdict[str, set[WebSocket]] = defaultdict(set)

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
        self.games[game.id] = game
        return game

    def get(self, game_id: str) -> GameSession:
        try:
            return self.games[game_id]
        except KeyError as exc:
            raise GameNotFound(game_id) from exc

    async def make_human_move(
        self, game_id: str, uci: str, position_version: int
    ) -> GameSnapshot:
        game = self.get(game_id)
        async with self._game_locks[game_id]:
            game.apply_uci(
                uci,
                actor="human:white",
                position_version=position_version,
            )
            await self.broadcast(game)
            if (
                game.opponent is OpponentKind.STOCKFISH
                and game.status.value == "active"
                and game.board.turn is chess.BLACK
            ):
                engine_move = await self.engine.choose_move(
                    game.board,
                    target_elo=game.stockfish_elo,
                    move_time_ms=game.engine_move_time_ms,
                )
                game.apply_uci(
                    engine_move.uci,
                    actor="stockfish:black",
                )
                game.moves[-1].elapsed_ms = engine_move.elapsed_ms
            snapshot = game.snapshot()
            await self.broadcast(game)
            return snapshot

    async def reset(self, game_id: str) -> GameSnapshot:
        game = self.get(game_id)
        async with self._game_locks[game_id]:
            game.reset()
            snapshot = game.snapshot()
            await self.broadcast(game)
            return snapshot

    async def resign(self, game_id: str, color: str = "white") -> GameSnapshot:
        game = self.get(game_id)
        async with self._game_locks[game_id]:
            game.resign(color)
            snapshot = game.snapshot()
            await self.broadcast(game)
            return snapshot

    async def subscribe(self, game_id: str, websocket: WebSocket) -> None:
        self.get(game_id)
        await websocket.accept()
        self._listeners[game_id].add(websocket)
        await websocket.send_json(
            {"type": "snapshot", "payload": self.get(game_id).snapshot().model_dump(mode="json")}
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
