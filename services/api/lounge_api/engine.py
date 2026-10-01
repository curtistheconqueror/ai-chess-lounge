from __future__ import annotations

import asyncio
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

import chess
import chess.engine

from .models import EngineSummary


@dataclass(frozen=True, slots=True)
class EngineMove:
    uci: str
    elapsed_ms: int


class StockfishService:
    """A serialized Stockfish UCI process shared by Stage 1 games."""

    def __init__(self) -> None:
        self.path = self._discover_path()
        self._engine: chess.engine.SimpleEngine | None = None
        self._lock = asyncio.Lock()
        self._version: str | None = None

    @staticmethod
    def _discover_path() -> str | None:
        configured = os.getenv("STOCKFISH_PATH")
        candidates = [
            configured,
            shutil.which("stockfish"),
            "/usr/games/stockfish",
            str(
                Path(__file__).resolve().parents[3]
                / ".runtime"
                / "stockfish-root"
                / "usr"
                / "games"
                / "stockfish"
            ),
        ]
        for candidate in candidates:
            if candidate and Path(candidate).is_file() and os.access(candidate, os.X_OK):
                return str(Path(candidate).resolve())
        return None

    @property
    def available(self) -> bool:
        return self.path is not None

    async def summary(self, target_elo: int, move_time_ms: int) -> EngineSummary:
        if self.available and self._version is None:
            await self._ensure_started()
        return EngineSummary(
            name="Stockfish" if self.available else "Stockfish unavailable",
            available=self.available,
            target_elo=target_elo,
            move_time_ms=move_time_ms,
            version=self._version,
            path=self.path,
        )

    async def choose_move(
        self, board: chess.Board, *, target_elo: int, move_time_ms: int
    ) -> EngineMove:
        if not self.available:
            raise RuntimeError(
                "Stockfish is not installed. Set STOCKFISH_PATH or use the Docker runtime."
            )
        async with self._lock:
            await self._ensure_started()
            assert self._engine is not None
            started = asyncio.get_running_loop().time()
            move = await asyncio.to_thread(
                self._play_sync,
                board.copy(stack=True),
                target_elo,
                move_time_ms,
            )
            elapsed_ms = round((asyncio.get_running_loop().time() - started) * 1000)
            return EngineMove(uci=move.uci(), elapsed_ms=elapsed_ms)

    def _play_sync(self, board: chess.Board, target_elo: int, move_time_ms: int) -> chess.Move:
        assert self._engine is not None
        options = self._engine.options
        configuration: dict[str, object] = {}
        if "UCI_LimitStrength" in options and "UCI_Elo" in options:
            elo_option = options["UCI_Elo"]
            minimum = int(elo_option.min or 1320)
            maximum = int(elo_option.max or 3190)
            configuration["UCI_LimitStrength"] = target_elo < maximum
            configuration["UCI_Elo"] = min(max(target_elo, minimum), maximum)
        elif "Skill Level" in options:
            configuration["Skill Level"] = max(0, min(20, round((target_elo - 800) / 120)))
        if configuration:
            self._engine.configure(configuration)
        result = self._engine.play(
            board,
            chess.engine.Limit(time=move_time_ms / 1000),
        )
        if result.move is None:
            raise RuntimeError("Stockfish returned no move.")
        return result.move

    async def _ensure_started(self) -> None:
        if self._engine is not None:
            return
        if not self.path:
            return
        self._engine = await asyncio.to_thread(chess.engine.SimpleEngine.popen_uci, self.path)
        name = self._engine.id.get("name", "Stockfish")
        self._version = name

    async def close(self) -> None:
        if self._engine is not None:
            engine, self._engine = self._engine, None
            await asyncio.to_thread(engine.quit)
