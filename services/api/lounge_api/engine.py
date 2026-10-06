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


@dataclass(frozen=True, slots=True)
class EngineAnalysis:
    score_cp: int
    mate: int | None
    best_move: str | None
    pv_san: tuple[str, ...]
    depth: int | None


class EngineFailure(RuntimeError):
    """Raised when Stockfish cannot complete a requested turn."""


async def _engine_thread(operation, *args, discard_cancelled_result=None, on_cancelled_error=None):
    """Keep the service lock until threaded UCI work really ends on cancellation."""
    task = asyncio.create_task(asyncio.to_thread(operation, *args))
    interrupted = False
    while True:
        try:
            result = await asyncio.shield(task)
            break
        except asyncio.CancelledError:
            if task.cancelled():
                raise
            interrupted = True
        except Exception:
            if interrupted:
                if on_cancelled_error is not None:
                    on_cancelled_error()
                raise asyncio.CancelledError from None
            raise
    if interrupted:
        if discard_cancelled_result is not None:
            discard_cancelled_result(result)
        raise asyncio.CancelledError
    return result


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
        async with self._lock:
            if self.available and self._version is None:
                try:
                    await self._ensure_started()
                except (chess.engine.EngineError, OSError, TimeoutError) as exc:
                    self._discard_failed_engine()
                    raise EngineFailure("Stockfish startup could not be completed.") from exc
        return EngineSummary(
            name="Stockfish" if self.available else "Stockfish unavailable",
            available=self.available,
            target_elo=target_elo,
            move_time_ms=move_time_ms,
            version=self._version,
        )

    async def analyse_position(
        self,
        board: chess.Board,
        *,
        analysis_time_ms: int = 80,
    ) -> EngineAnalysis:
        if not self.available:
            raise EngineFailure(
                "Stockfish is not installed. Set STOCKFISH_PATH or use the Docker runtime."
            )
        async with self._lock:
            try:
                await self._ensure_started()
                assert self._engine is not None
                return await _engine_thread(
                    self._analyse_sync,
                    board.copy(stack=True),
                    analysis_time_ms,
                    on_cancelled_error=self._discard_failed_engine,
                )
            except (chess.engine.EngineError, OSError, TimeoutError) as exc:
                self._discard_failed_engine()
                raise EngineFailure("Stockfish analysis could not be completed.") from exc

    async def choose_move(
        self, board: chess.Board, *, target_elo: int, move_time_ms: int
    ) -> EngineMove:
        if not self.available:
            raise EngineFailure(
                "Stockfish is not installed. Set STOCKFISH_PATH or use the Docker runtime."
            )
        async with self._lock:
            try:
                await self._ensure_started()
                assert self._engine is not None
                started = asyncio.get_running_loop().time()
                move = await _engine_thread(
                    self._play_sync,
                    board.copy(stack=True),
                    target_elo,
                    move_time_ms,
                    on_cancelled_error=self._discard_failed_engine,
                )
            except (chess.engine.EngineError, OSError, TimeoutError) as exc:
                self._discard_failed_engine()
                raise EngineFailure("Stockfish could not complete the turn.") from exc
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
            raise EngineFailure("Stockfish returned no move.")
        return result.move

    def _analyse_sync(self, board: chess.Board, analysis_time_ms: int) -> EngineAnalysis:
        assert self._engine is not None
        if "UCI_LimitStrength" in self._engine.options:
            self._engine.configure({"UCI_LimitStrength": False})
        info = self._engine.analyse(
            board,
            chess.engine.Limit(time=analysis_time_ms / 1_000),
        )
        pov_score = info["score"].pov(chess.WHITE)
        score_cp = pov_score.score(mate_score=100_000) or 0
        mate = pov_score.mate()
        pv = list(info.get("pv", []))[:8]
        best_move = pv[0].uci() if pv else None
        pv_board = board.copy(stack=True)
        pv_san: list[str] = []
        for move in pv:
            if move not in pv_board.legal_moves:
                break
            pv_san.append(pv_board.san(move))
            pv_board.push(move)
        depth = info.get("depth")
        return EngineAnalysis(
            score_cp=score_cp,
            mate=mate,
            best_move=best_move,
            pv_san=tuple(pv_san),
            depth=int(depth) if depth is not None else None,
        )

    async def _ensure_started(self) -> None:
        if self._engine is not None:
            return
        if not self.path:
            return
        self._engine = await _engine_thread(
            chess.engine.SimpleEngine.popen_uci,
            self.path,
            discard_cancelled_result=lambda engine: engine.close(),
        )
        name = self._engine.id.get("name", "Stockfish")
        self._version = name

    def _discard_failed_engine(self) -> None:
        engine, self._engine = self._engine, None
        self._version = None
        if engine is not None:
            engine.close()

    async def close(self) -> None:
        async with self._lock:
            if self._engine is not None:
                engine, self._engine = self._engine, None
                self._version = None
                try:
                    await _engine_thread(engine.quit, on_cancelled_error=engine.close)
                except (chess.engine.EngineError, OSError, TimeoutError):
                    engine.close()
