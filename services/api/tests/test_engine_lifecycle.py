import asyncio
import threading
from types import SimpleNamespace

import chess
import chess.engine
import pytest
from lounge_api.engine import EngineFailure, StockfishService


class FixtureUCI:
    id = {"name": "Generated UCI"}
    options = {}

    def __init__(self, failure=None, gate=None):
        self.failure, self.gate = failure, gate
        self.started = threading.Event()
        self.closed = self.quits = 0

    def play(self, board, limit):
        self.started.set()
        if self.gate is not None:
            assert self.gate.wait(5), "Fixture command barrier timed out"
        if self.failure:
            raise self.failure
        return SimpleNamespace(move=chess.Move.from_uci("e2e4"))

    def analyse(self, board, limit):
        self.started.set()
        if self.gate is not None:
            assert self.gate.wait(5)
        if self.failure:
            raise self.failure
        return {"score": chess.engine.PovScore(chess.engine.Cp(1), chess.WHITE), "pv": []}

    def quit(self):
        self.quits += 1
        self.closed += 1

    def close(self):
        self.closed += 1


def service(monkeypatch, engines):
    engine = StockfishService()
    engine.path = "generated-uci-fixture"
    engines = iter(engines)

    def start(path):
        value = next(engines)
        if isinstance(value, Exception):
            raise value
        return value

    monkeypatch.setattr(chess.engine.SimpleEngine, "popen_uci", start)
    return engine


@pytest.mark.parametrize("operation", ["play", "analyse"])
@pytest.mark.parametrize(
    "failure", [chess.engine.EngineTerminatedError("private"), OSError("private")]
)
def test_failed_command_is_sanitized_discarded_and_next_request_can_restart(
    monkeypatch, operation, failure
):
    bad, good = FixtureUCI(failure), FixtureUCI()
    engine = service(monkeypatch, [bad, good])

    async def run():
        try:
            with pytest.raises(EngineFailure) as error:
                if operation == "play":
                    await engine.choose_move(chess.Board(), target_elo=1600, move_time_ms=10)
                else:
                    await engine.analyse_position(chess.Board())
            assert "private" not in str(error.value)
            assert bad.closed == 1 and engine._engine is None
            result = await engine.choose_move(chess.Board(), target_elo=1600, move_time_ms=10)
            assert result.uci == "e2e4"
        finally:
            await engine.close()
        assert good.quits == 1 and engine._engine is None

    asyncio.run(asyncio.wait_for(run(), timeout=10))


@pytest.mark.parametrize("operation", ["play", "analyse"])
def test_repeated_cancellation_does_not_release_lock_while_thread_command_is_running(
    monkeypatch, operation
):
    gate = threading.Event()
    uci = FixtureUCI(gate=gate)
    engine = service(monkeypatch, [uci])

    async def run():
        command = (
            engine.choose_move(chess.Board(), target_elo=1600, move_time_ms=10)
            if operation == "play"
            else engine.analyse_position(chess.Board())
        )
        playing = asyncio.create_task(command)
        try:
            while not uci.started.is_set():
                await asyncio.sleep(0)
            playing.cancel()
            await asyncio.sleep(0)
            playing.cancel()
            closing = asyncio.create_task(engine.close())
            await asyncio.sleep(0.01)
            assert uci.quits == 0 and not closing.done()
            gate.set()
            with pytest.raises(asyncio.CancelledError):
                await playing
            await closing
            assert uci.quits == 1 and engine._engine is None
            await engine.close()
            assert uci.quits == 1
        finally:
            gate.set()
            await asyncio.gather(playing, return_exceptions=True)
            await engine.close()

    asyncio.run(asyncio.wait_for(run(), timeout=10))


def test_cancelled_startup_discards_created_process(monkeypatch):
    gate, started = threading.Event(), threading.Event()
    uci = FixtureUCI()
    engine = StockfishService()
    engine.path = "generated-uci-fixture"

    def start(path):
        started.set()
        assert gate.wait(5)
        return uci

    monkeypatch.setattr(chess.engine.SimpleEngine, "popen_uci", start)

    async def run():
        opening = asyncio.create_task(engine.summary(1600, 10))
        try:
            while not started.is_set():
                await asyncio.sleep(0)
            opening.cancel()
            gate.set()
            with pytest.raises(asyncio.CancelledError):
                await opening
            assert engine._engine is None and uci.closed == 1
        finally:
            gate.set()
            await asyncio.gather(opening, return_exceptions=True)
            await engine.close()

    asyncio.run(asyncio.wait_for(run(), timeout=10))


def test_real_terminated_stockfish_process_is_reaped_and_retry_returns_legal_move():
    engine = StockfishService()
    if not engine.available:
        pytest.skip("Installed Stockfish required; fake engine is not real recovery evidence")

    async def run():
        try:
            await engine.summary(1600, 30)
            original = engine._engine
            original.close()
            await asyncio.to_thread(original.returncode.result, 5)
            with pytest.raises(EngineFailure):
                await engine.choose_move(chess.Board(), target_elo=1600, move_time_ms=30)
            assert engine._engine is None
            move = await engine.choose_move(chess.Board(), target_elo=1600, move_time_ms=30)
            assert chess.Move.from_uci(move.uci) in chess.Board().legal_moves
            assert engine._engine is not original
        finally:
            await engine.close()

    asyncio.run(asyncio.wait_for(run(), timeout=20))


@pytest.mark.parametrize("failure", [OSError("private startup"), TimeoutError("private startup")])
def test_startup_failure_leaves_service_ready_for_new_request(monkeypatch, failure):
    good = FixtureUCI()
    engine = service(monkeypatch, [failure, good])

    async def run():
        try:
            with pytest.raises(EngineFailure) as error:
                await engine.choose_move(chess.Board(), target_elo=1600, move_time_ms=10)
            assert "private" not in str(error.value) and engine._engine is None
            assert (
                await engine.choose_move(chess.Board(), target_elo=1600, move_time_ms=10)
            ).uci == "e2e4"
        finally:
            await engine.close()
        assert good.quits == 1

    asyncio.run(asyncio.wait_for(run(), timeout=10))


def test_dead_process_quit_failure_falls_back_to_close_and_clears_state(monkeypatch):
    class DeadUCI(FixtureUCI):
        def quit(self):
            self.quits += 1
            raise chess.engine.EngineTerminatedError("Generated terminated process")

    uci = DeadUCI()
    engine = service(monkeypatch, [uci])

    async def run():
        await engine.summary(1600, 10)
        await engine.close()
        await engine.close()
        assert engine._engine is None and engine._version is None
        assert uci.quits == uci.closed == 1

    asyncio.run(asyncio.wait_for(run(), timeout=10))


@pytest.mark.parametrize("operation", ["play", "analyse"])
@pytest.mark.parametrize(
    "failure", [chess.engine.EngineTerminatedError("private"), OSError("private")]
)
def test_cancelled_command_that_then_fails_discards_stale_handle(monkeypatch, operation, failure):
    gate = threading.Event()
    bad, good = FixtureUCI(failure, gate), FixtureUCI()
    engine = service(monkeypatch, [bad, good])

    async def run():
        command = (
            engine.choose_move(chess.Board(), target_elo=1600, move_time_ms=10)
            if operation == "play"
            else engine.analyse_position(chess.Board())
        )
        playing = asyncio.create_task(command)
        try:
            while not bad.started.is_set():
                await asyncio.sleep(0)
            playing.cancel()
            await asyncio.sleep(0)
            gate.set()
            with pytest.raises(asyncio.CancelledError):
                await playing
            assert bad.closed == 1 and engine._engine is None
            move = await engine.choose_move(chess.Board(), target_elo=1600, move_time_ms=10)
            assert move.uci == "e2e4" and engine._engine is good
        finally:
            gate.set()
            await asyncio.gather(playing, return_exceptions=True)
            await engine.close()

    asyncio.run(asyncio.wait_for(run(), timeout=10))


@pytest.mark.parametrize(
    "failure", [chess.engine.EngineError("private startup"), OSError("private")]
)
def test_summary_startup_failure_is_sanitized_and_recoverable(monkeypatch, failure):
    engine = service(monkeypatch, [failure, FixtureUCI()])

    async def run():
        try:
            with pytest.raises(EngineFailure) as error:
                await engine.summary(1600, 10)
            assert "private" not in str(error.value) and engine._engine is None
            assert (await engine.summary(1600, 10)).version == "Generated UCI"
        finally:
            await engine.close()

    asyncio.run(asyncio.wait_for(run(), timeout=10))


@pytest.mark.parametrize("fail", [False, True])
def test_cancelled_shutdown_drains_quit_and_closes_on_later_failure(monkeypatch, fail):
    gate, started = threading.Event(), threading.Event()

    class SlowQuit(FixtureUCI):
        def quit(self):
            self.quits += 1
            started.set()
            assert gate.wait(5)
            if fail:
                raise chess.engine.EngineError("Generated quit failure")
            self.closed += 1

    uci = SlowQuit()
    engine = service(monkeypatch, [uci])

    async def run():
        await engine.summary(1600, 10)
        closing = asyncio.create_task(engine.close())
        try:
            while not started.is_set():
                await asyncio.sleep(0)
            closing.cancel()
            await asyncio.sleep(0)
            assert uci.closed == 0 and not closing.done()
            gate.set()
            with pytest.raises(asyncio.CancelledError):
                await closing
            assert uci.closed == uci.quits == 1 and engine._engine is None
        finally:
            gate.set()
            await asyncio.gather(closing, return_exceptions=True)
            await engine.close()

    asyncio.run(asyncio.wait_for(run(), timeout=10))
