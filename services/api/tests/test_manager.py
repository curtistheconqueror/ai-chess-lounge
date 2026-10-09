from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import chess
import pytest
from lounge_api.adapters import AdapterRegistry
from lounge_api.domain import MoveRejected
from lounge_api.engine import EngineAnalysis, EngineFailure, EngineMove, StockfishService
from lounge_api.manager import GameManager
from lounge_api.models import (
    CreateGameRequest,
    EngineSummary,
    GameStatus,
    MatchState,
    OpponentKind,
    TurnLease,
)
from lounge_api.persistence import DatabaseStore
from lounge_api.player_protocol import (
    AssistanceDivision,
    ConnectionMode,
    MoveProposal,
    MoveRequest,
    PlayerConfiguration,
    UsageMetrics,
)
from sqlalchemy.exc import OperationalError


class FakeEngine(StockfishService):
    def __init__(self) -> None:
        super().__init__()
        self.path = None  # This fixture must never launch an installed native engine.
        self.analysis_calls = 0

    @property
    def available(self) -> bool:
        return True

    async def summary(self, target_elo: int, move_time_ms: int) -> EngineSummary:
        return EngineSummary(
            name="Deterministic Test Engine",
            available=True,
            target_elo=target_elo,
            move_time_ms=move_time_ms,
            version="test-1",
        )

    async def choose_move(
        self, board: chess.Board, *, target_elo: int, move_time_ms: int
    ) -> EngineMove:
        return EngineMove(uci=sorted(move.uci() for move in board.legal_moves)[0], elapsed_ms=1)

    async def analyse_position(
        self,
        board: chess.Board,
        *,
        analysis_time_ms: int = 80,
    ) -> EngineAnalysis:
        del analysis_time_ms
        self.analysis_calls += 1
        legal = sorted(board.legal_moves, key=lambda move: move.uci())
        best = legal[0] if legal else None
        return EngineAnalysis(
            score_cp=0,
            mate=None,
            best_move=best.uci() if best else None,
            pv_san=(board.san(best),) if best else (),
            depth=12,
        )

    async def close(self) -> None:
        return None


class FakeClock:
    def __init__(self) -> None:
        self.current = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.current

    def advance(self, **kwargs: float) -> None:
        self.current += timedelta(**kwargs)


class FlakyEngine(FakeEngine):
    def __init__(self, response_delay: float = 0) -> None:
        super().__init__()
        self.calls = 0
        self.response_delay = response_delay

    async def choose_move(
        self, board: chess.Board, *, target_elo: int, move_time_ms: int
    ) -> EngineMove:
        self.calls += 1
        if self.calls == 1:
            raise EngineFailure("transient test failure")
        await asyncio.sleep(self.response_delay)
        return await super().choose_move(
            board,
            target_elo=target_elo,
            move_time_ms=move_time_ms,
        )


class BlockingAnalysisEngine(FakeEngine):
    def __init__(self) -> None:
        super().__init__()
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self._blocked = False

    async def analyse_position(
        self,
        board: chess.Board,
        *,
        analysis_time_ms: int = 80,
    ) -> EngineAnalysis:
        if not self._blocked:
            self._blocked = True
            self.started.set()
            await self.release.wait()
        return await super().analyse_position(
            board,
            analysis_time_ms=analysis_time_ms,
        )


class BlockingPlayerAdapter:
    adapter_id = "blocking"

    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    def list_models(self) -> list[str]:
        return ["blocking-v1"]

    def capabilities(self, model: str) -> dict[str, object]:
        return {"model": model, "credentials_required": False}

    def validate_configuration(self, player: PlayerConfiguration) -> None:
        assert player.model == "blocking-v1"

    async def choose_move(
        self,
        request: MoveRequest,
        player: PlayerConfiguration,
    ) -> MoveProposal:
        del player
        self.started.set()
        await self.release.wait()
        assert request.legal_moves
        return MoveProposal(
            request_id=request.request_id,
            match_id=request.match_id,
            position_version=request.position_version,
            move=request.legal_moves[0],
            usage=UsageMetrics(),
        )

    def normalize_usage(self, usage: object) -> UsageMetrics:
        del usage
        return UsageMetrics()

    async def healthcheck(self) -> bool:
        return True


class MismatchedPlayerAdapter(BlockingPlayerAdapter):
    adapter_id = "mismatched"

    async def choose_move(
        self,
        request: MoveRequest,
        player: PlayerConfiguration,
    ) -> MoveProposal:
        del player
        assert request.legal_moves
        return MoveProposal(
            request_id=request.request_id,
            match_id=request.match_id,
            position_version=request.position_version + 1,
            move=request.legal_moves[0],
        )


class SlowPlayerAdapter(BlockingPlayerAdapter):
    adapter_id = "slow"

    async def choose_move(
        self,
        request: MoveRequest,
        player: PlayerConfiguration,
    ) -> MoveProposal:
        del player
        await asyncio.sleep(0.16)
        assert request.legal_moves
        return MoveProposal(
            request_id=request.request_id,
            match_id=request.match_id,
            position_version=request.position_version,
            move=request.legal_moves[0],
        )


def scripted_player(name: str, *moves: str) -> PlayerConfiguration:
    return PlayerConfiguration(
        adapter_id="scripted",
        display_name=name,
        provider="Lounge Test Harness",
        model="deterministic-v1",
        connection_mode=ConnectionMode.LOCAL,
        division=AssistanceDivision.LEGAL_ASSIST,
        settings={"moves": list(moves)},
    )


def test_human_move_triggers_engine_reply() -> None:
    async def run() -> None:
        manager = GameManager(
            engine=FakeEngine(),
            store=DatabaseStore("sqlite+aiosqlite:///:memory:"),
        )
        await manager.start()
        try:
            game = await manager.create(
                CreateGameRequest(opponent=OpponentKind.STOCKFISH, stockfish_elo=1600)
            )
            snapshot = await manager.make_human_move(game.id, "e2e4", 0)

            assert len(snapshot.moves) == 2
            assert snapshot.moves[0].actor == "human:white"
            assert snapshot.moves[1].actor == "stockfish:black"
            assert snapshot.turn == "white"
            assert snapshot.version == 2
            assert snapshot.event_sequence == 4
        finally:
            await manager.close()

    asyncio.run(run())


def test_scripted_agents_complete_unattended_game_and_persist_metadata() -> None:
    async def run() -> None:
        manager = GameManager(
            engine=FakeEngine(),
            store=DatabaseStore("sqlite+aiosqlite:///:memory:"),
            schedule_timeouts=False,
        )
        await manager.start()
        try:
            game = await manager.create(
                CreateGameRequest(
                    opponent=OpponentKind.HUMAN,
                    white_player=scripted_player("White Script", "f2f3", "g2g4"),
                    black_player=scripted_player("Black Script", "e7e5", "d8h4"),
                )
            )
            snapshot = await manager.wait_for_automation(game.id, timeout=2)

            assert snapshot.status is GameStatus.CHECKMATE
            assert snapshot.result == "0-1"
            assert [move.uci for move in snapshot.moves] == [
                "f2f3",
                "e7e5",
                "g2g4",
                "d8h4",
            ]
            assert [move.actor for move in snapshot.moves] == [
                "scripted:white",
                "scripted:black",
                "scripted:white",
                "scripted:black",
            ]
            assert all(move.player_metadata is not None for move in snapshot.moves)
            assert snapshot.moves[-1].player_metadata is not None
            assert snapshot.moves[-1].player_metadata.plan
            assert snapshot.white_player.display_name == "White Script"
            assert snapshot.black_player.display_name == "Black Script"
            assert '[White "White Script"]' in snapshot.pgn
            assert '[Black "Black Script"]' in snapshot.pgn

            restored = await manager.store.load_game(game.id)
            assert restored is not None
            assert restored.black_player is not None
            assert restored.black_player.player_id == snapshot.black_player.player_id
            assert restored.moves[-1].player_metadata == snapshot.moves[-1].player_metadata
            events = await manager.events(game.id)
            assert [event.type for event in events].count("move.accepted") == 4
            assert events[-1].type == "match.completed"
        finally:
            await manager.close()

    asyncio.run(run())


def test_human_move_is_rejected_on_automated_seat() -> None:
    async def run() -> None:
        manager = GameManager(
            engine=FakeEngine(),
            store=DatabaseStore("sqlite+aiosqlite:///:memory:"),
            schedule_timeouts=False,
            schedule_agents=False,
        )
        await manager.start()
        try:
            game = await manager.create(
                CreateGameRequest(
                    opponent=OpponentKind.HUMAN,
                    white_player=scripted_player("White Script", "e2e4"),
                    black_player=PlayerConfiguration.human("black"),
                )
            )
            with pytest.raises(MoveRejected, match="controlled by an automated player"):
                await manager.make_human_move(game.id, "e2e4", 0)
            unchanged = await manager.snapshot(game.id)
            assert unchanged.version == 0
            assert unchanged.moves == []
        finally:
            await manager.close()

    asyncio.run(run())


def test_illegal_agent_proposal_pauses_without_mutating_board() -> None:
    async def run() -> None:
        manager = GameManager(
            engine=FakeEngine(),
            store=DatabaseStore("sqlite+aiosqlite:///:memory:"),
            schedule_timeouts=False,
        )
        await manager.start()
        try:
            game = await manager.create(
                CreateGameRequest(
                    opponent=OpponentKind.HUMAN,
                    white_player=scripted_player("Broken Agent", "a1a8"),
                    black_player=PlayerConfiguration.human("black"),
                )
            )
            snapshot = await manager.wait_for_automation(game.id, timeout=2)
            events = await manager.events(game.id)

            assert snapshot.lifecycle is MatchState.PAUSED
            assert snapshot.version == 0
            assert snapshot.moves == []
            assert [event.type for event in events][-2:] == [
                "agent.failed",
                "match.paused",
            ]
            assert events[-2].payload["reason"] == "illegal_move"
        finally:
            await manager.close()

    asyncio.run(run())


def test_stale_agent_proposal_pauses_without_mutating_board() -> None:
    async def run() -> None:
        adapter = MismatchedPlayerAdapter()
        manager = GameManager(
            engine=FakeEngine(),
            adapters=AdapterRegistry([adapter]),
            store=DatabaseStore("sqlite+aiosqlite:///:memory:"),
            schedule_timeouts=False,
        )
        await manager.start()
        try:
            player = PlayerConfiguration(
                adapter_id="mismatched",
                display_name="Mismatched Agent",
                provider="Test",
                model="blocking-v1",
                connection_mode=ConnectionMode.LOCAL,
                division=AssistanceDivision.LEGAL_ASSIST,
            )
            game = await manager.create(
                CreateGameRequest(
                    opponent=OpponentKind.HUMAN,
                    white_player=player,
                    black_player=PlayerConfiguration.human("black"),
                )
            )
            snapshot = await manager.wait_for_automation(game.id, timeout=2)
            events = await manager.events(game.id)

            assert snapshot.lifecycle is MatchState.PAUSED
            assert snapshot.version == 0
            assert snapshot.moves == []
            assert events[-2].type == "agent.failed"
            assert events[-2].payload["reason"] == "stale_or_mismatched_response"
        finally:
            await manager.close()

    asyncio.run(run())


def test_slow_agent_call_renews_turn_lease(monkeypatch: pytest.MonkeyPatch) -> None:
    async def run() -> None:
        adapter = SlowPlayerAdapter()
        manager = GameManager(
            engine=FakeEngine(),
            adapters=AdapterRegistry([adapter]),
            store=DatabaseStore("sqlite+aiosqlite:///:memory:"),
            schedule_timeouts=False,
            schedule_agents=False,
        )
        player = PlayerConfiguration(
            adapter_id="slow",
            display_name="Slow Agent",
            provider="Test",
            model="blocking-v1",
            connection_mode=ConnectionMode.LOCAL,
            division=AssistanceDivision.LEGAL_ASSIST,
        )
        request = MoveRequest(
            match_id="match-1",
            position_version=0,
            color="white",
            fen=chess.STARTING_FEN,
            moves_uci=[],
            pgn="",
            legal_moves=["e2e4"],
            remaining_ms=1_000,
            move_deadline_ms=500,
            division=AssistanceDivision.LEGAL_ASSIST,
        )
        lease = TurnLease(
            match_id="match-1",
            owner_id="worker-1",
            token="lease-1",
            position_version=0,
            acquired_at="2026-10-01T12:00:00+00:00",
            expires_at="2026-10-01T12:00:00.300000+00:00",
        )
        renewal_count = 0

        async def renew(current: TurnLease, *, lease_ms: int = 15_000) -> TurnLease:
            nonlocal renewal_count
            assert current == lease
            assert lease_ms == 300
            renewal_count += 1
            return current

        monkeypatch.setattr(manager, "renew_turn_lease", renew)

        proposal, renewed_lease = await manager._call_adapter_with_lease(
            adapter,
            request,
            player,
            lease,
            lease_ms=300,
            timeout_ms=500,
        )

        assert proposal.move == "e2e4"
        assert renewed_lease == lease
        assert renewal_count >= 1

    asyncio.run(run())


def test_pause_cancels_inflight_agent_without_accepting_late_move() -> None:
    async def run() -> None:
        adapter = BlockingPlayerAdapter()
        manager = GameManager(
            engine=FakeEngine(),
            adapters=AdapterRegistry([adapter]),
            store=DatabaseStore("sqlite+aiosqlite:///:memory:"),
            schedule_timeouts=False,
        )
        await manager.start()
        try:
            player = PlayerConfiguration(
                adapter_id="blocking",
                display_name="Blocking Agent",
                provider="Test",
                model="blocking-v1",
                connection_mode=ConnectionMode.LOCAL,
                division=AssistanceDivision.LEGAL_ASSIST,
            )
            game = await manager.create(
                CreateGameRequest(
                    opponent=OpponentKind.HUMAN,
                    white_player=player,
                    black_player=PlayerConfiguration.human("black"),
                )
            )
            await adapter.started.wait()
            paused = await manager.pause(game.id)
            adapter.release.set()
            await asyncio.sleep(0)
            final = await manager.snapshot(game.id)

            assert paused.lifecycle is MatchState.PAUSED
            assert final.lifecycle is MatchState.PAUSED
            assert final.version == 0
            assert final.moves == []
        finally:
            adapter.release.set()
            await manager.close()

    asyncio.run(run())


def test_pause_cancels_human_triggered_agent_reply() -> None:
    async def run() -> None:
        adapter = BlockingPlayerAdapter()
        manager = GameManager(
            engine=FakeEngine(),
            adapters=AdapterRegistry([adapter]),
            store=DatabaseStore("sqlite+aiosqlite:///:memory:"),
            schedule_timeouts=False,
        )
        await manager.start()
        try:
            player = PlayerConfiguration(
                adapter_id="blocking",
                display_name="Blocking Black Agent",
                provider="Test",
                model="blocking-v1",
                connection_mode=ConnectionMode.LOCAL,
                division=AssistanceDivision.LEGAL_ASSIST,
            )
            game = await manager.create(
                CreateGameRequest(
                    opponent=OpponentKind.HUMAN,
                    white_player=PlayerConfiguration.human("white"),
                    black_player=player,
                )
            )
            move_task = asyncio.create_task(manager.make_human_move(game.id, "e2e4", 0))
            await asyncio.wait_for(adapter.started.wait(), timeout=0.5)

            paused = await asyncio.wait_for(manager.pause(game.id), timeout=0.5)
            adapter.release.set()
            await asyncio.wait_for(move_task, timeout=0.5)
            final = await manager.snapshot(game.id)

            assert paused.lifecycle is MatchState.PAUSED
            assert final.lifecycle is MatchState.PAUSED
            assert final.version == 1
            assert [move.uci for move in final.moves] == ["e2e4"]
        finally:
            adapter.release.set()
            await manager.close()

    asyncio.run(run())


def test_spectator_analysis_is_versioned_cached_and_classifies_moves() -> None:
    async def run() -> None:
        engine = FakeEngine()
        manager = GameManager(
            engine=engine,
            analysis_engine=engine,
            store=DatabaseStore("sqlite+aiosqlite:///:memory:"),
            schedule_timeouts=False,
        )
        await manager.start()
        try:
            game = await manager.create(CreateGameRequest(opponent=OpponentKind.STOCKFISH))
            snapshot = await manager.make_human_move(game.id, "e2e4", 0)
            first = await manager.analysis(game.id)
            cached = await manager.analysis(game.id)

            assert first is cached
            assert engine.analysis_calls == 3
            assert first.position_version == snapshot.version == 2
            assert len(first.points) == 3
            assert first.points[0].classification is None
            assert first.points[1].classification is not None
            assert first.points[2].classification == "best"
            assert first.points[-1].pv_san
            assert first.engine_name == "Deterministic Test Engine"

            await manager.make_human_move(game.id, "d2d4", 2)
            extended = await manager.analysis(game.id)
            assert extended.position_version == 4
            assert len(extended.points) == 5
            assert engine.analysis_calls == 5
        finally:
            await manager.close()

    asyncio.run(run())


def test_spectator_analysis_restarts_when_position_advances() -> None:
    async def run() -> None:
        analysis_engine = BlockingAnalysisEngine()
        manager = GameManager(
            engine=FakeEngine(),
            analysis_engine=analysis_engine,
            store=DatabaseStore("sqlite+aiosqlite:///:memory:"),
            schedule_timeouts=False,
        )
        await manager.start()
        try:
            game = await manager.create(CreateGameRequest(opponent=OpponentKind.HUMAN))
            pending = asyncio.create_task(manager.analysis(game.id))
            await analysis_engine.started.wait()

            moved = await manager.make_human_move(game.id, "e2e4", 0)
            analysis_engine.release.set()
            result = await pending

            assert moved.version == 1
            assert result.position_version == 1
            assert len(result.points) == 2
            assert result.points[-1].fen == moved.fen
        finally:
            analysis_engine.release.set()
            await manager.close()

    asyncio.run(run())


@pytest.mark.parametrize("response_delay", [0, 0.2])
def test_transient_engine_failure_retries_the_pending_turn(response_delay: float) -> None:
    async def run() -> None:
        engine = FlakyEngine(response_delay)
        manager = GameManager(
            engine=engine,
            store=DatabaseStore("sqlite+aiosqlite:///:memory:"),
            schedule_timeouts=False,
        )
        await manager.start()
        try:
            game = await manager.create(CreateGameRequest(opponent=OpponentKind.STOCKFISH))
            pending = await manager.make_human_move(game.id, "e2e4", 0)

            assert pending.version == 1
            assert pending.turn == "black"

            # Retry starts after 500 ms; engine response and commit can take longer.
            # Observe the committed position rather than assuming a runner speed.
            async with asyncio.timeout(5):
                while True:
                    recovered = await manager.snapshot(game.id)
                    if recovered.version >= 2:
                        break
                    await asyncio.sleep(0.02)

            assert engine.calls == 2
            assert recovered.version == 2
            assert recovered.turn == "white"
            assert len(recovered.moves) == 2
        finally:
            await manager.close()

    asyncio.run(run())


def test_transient_lease_claim_failure_retries_the_pending_turn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def run() -> None:
        manager = GameManager(
            engine=FakeEngine(),
            store=DatabaseStore("sqlite+aiosqlite:///:memory:"),
            schedule_timeouts=False,
        )
        await manager.start()
        original_acquire = manager.store.acquire_turn_lease
        attempts = 0

        async def fail_once(*args, **kwargs):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise OperationalError("UPDATE matches", {}, OSError("temporary outage"))
            return await original_acquire(*args, **kwargs)

        monkeypatch.setattr(manager.store, "acquire_turn_lease", fail_once)
        try:
            game = await manager.create(CreateGameRequest(opponent=OpponentKind.STOCKFISH))
            pending = await manager.make_human_move(game.id, "e2e4", 0)

            assert pending.version == 1
            assert pending.turn == "black"

            # Retry starts after 500 ms; engine response and commit can take longer.
            # Observe the committed position rather than assuming a runner speed.
            async with asyncio.timeout(5):
                while True:
                    recovered = await manager.snapshot(game.id)
                    if recovered.version >= 2:
                        break
                    await asyncio.sleep(0.02)

            assert attempts == 2
            assert recovered.version == 2
            assert recovered.turn == "white"
        finally:
            await manager.close()

    asyncio.run(run())


def test_manager_persists_timeout_and_completion_events() -> None:
    async def run() -> None:
        clock = FakeClock()
        manager = GameManager(
            store=DatabaseStore("sqlite+aiosqlite:///:memory:"),
            clock=clock,
            schedule_timeouts=False,
        )
        await manager.start()
        try:
            game = await manager.create(
                CreateGameRequest(
                    opponent=OpponentKind.HUMAN,
                    initial_time_ms=1_000,
                    increment_ms=0,
                )
            )
            clock.advance(seconds=1)

            assert await manager.expire_due_games() == [game.id]
            snapshot = await manager.snapshot(game.id)
            events = await manager.events(game.id)

            assert snapshot.status is GameStatus.TIMEOUT
            assert snapshot.result == "0-1"
            assert snapshot.clock.timed_out_by == "white"
            assert [event.type for event in events][-2:] == [
                "clock.timeout",
                "match.completed",
            ]
            assert events[-2].payload["white_remaining_ms"] == 0
            assert events[-2].timestamp == clock.current.isoformat()
        finally:
            await manager.close()

    asyncio.run(run())


def test_background_deadline_task_broadcasts_timeout() -> None:
    async def run() -> None:
        manager = GameManager(store=DatabaseStore("sqlite+aiosqlite:///:memory:"))
        await manager.start()
        try:
            game = await manager.create(
                CreateGameRequest(
                    opponent=OpponentKind.HUMAN,
                    initial_time_ms=100,
                    increment_ms=0,
                )
            )
            # Await the background commit, not a scheduler-dependent fixed sleep.
            timeout_task = manager._timeout_tasks[game.id]
            await asyncio.wait_for(asyncio.shield(timeout_task), timeout=2)
            snapshot = await manager.snapshot(game.id)
            assert snapshot.status is GameStatus.TIMEOUT
        finally:
            await manager.close()

    asyncio.run(run())
