from __future__ import annotations

import asyncio
import hashlib
from collections import defaultdict
from collections.abc import Callable
from copy import deepcopy
from datetime import UTC, datetime
from time import perf_counter
from uuid import uuid4

import chess
from fastapi import WebSocket
from sqlalchemy.exc import (
    DisconnectionError,
    InterfaceError,
    OperationalError,
    SQLAlchemyError,
)
from sqlalchemy.exc import (
    TimeoutError as SQLAlchemyTimeoutError,
)

from .adapters import (
    AdapterConfigurationError,
    AdapterError,
    AdapterRegistry,
    PlayerAdapter,
    RetryableAdapterError,
    ScriptedPlayerAdapter,
    StockfishPlayerAdapter,
)
from .anthropic_adapter import AnthropicMessagesAdapter
from .domain import (
    ClockExpired,
    GameSession,
    MatchTransitionRejected,
    MoveRejected,
    StalePosition,
)
from .engine import EngineAnalysis, EngineFailure, StockfishService
from .gemini_adapter import GeminiInteractionsAdapter
from .models import (
    AnalysisPoint,
    CreateGameRequest,
    GameAnalysis,
    GameSnapshot,
    MatchEvent,
    MatchState,
    OpponentKind,
    TurnLease,
)
from .ollama_adapter import OllamaChatAdapter
from .openai_adapter import OpenAIResponsesAdapter
from .openai_compatible_adapter import OpenRouterChatAdapter, VLLMChatAdapter
from .persistence import (
    ConcurrentGameUpdate,
    DatabaseStore,
    IdempotencyConflict,
    RunnerTrustError,
    TurnLeaseUnavailable,
)
from .player_protocol import MoveRequest as PlayerMoveRequest
from .player_protocol import PlayerConfiguration, PlayerMoveMetadata
from .provider_reliability import (
    ProviderRecoveryRequired,
    ProviderReliabilityController,
)
from .remote_runner import RemoteRunnerAdapter, RemoteRunnerBroker


class GameNotFound(KeyError):
    pass


class AnalysisSuperseded(RuntimeError):
    """Raised when a match keeps advancing before analysis can be published."""


RETRYABLE_DATABASE_ERRORS = (
    OperationalError,
    InterfaceError,
    DisconnectionError,
    SQLAlchemyTimeoutError,
)
RETRYABLE_AGENT_TURN_ERRORS = (
    RetryableAdapterError,
    EngineFailure,
    ConcurrentGameUpdate,
    TurnLeaseUnavailable,
    *RETRYABLE_DATABASE_ERRORS,
)
PROVIDER_RETRY_ADAPTERS = frozenset(
    {"openai", "anthropic", "google", "openrouter", "ollama", "vllm"}
)


class GameManager:
    def __init__(
        self,
        engine: StockfishService | None = None,
        analysis_engine: StockfishService | None = None,
        store: DatabaseStore | None = None,
        clock: Callable[[], datetime] | None = None,
        adapters: AdapterRegistry | None = None,
        provider_reliability: ProviderReliabilityController | None = None,
        remote_runners: RemoteRunnerBroker | None = None,
        *,
        schedule_timeouts: bool = True,
        schedule_agents: bool = True,
    ) -> None:
        self.engine = engine or StockfishService()
        self.analysis_engine = analysis_engine or StockfishService()
        self.store = store or DatabaseStore()
        self._clock = clock or (lambda: datetime.now(UTC))
        self.remote_runners = remote_runners or RemoteRunnerBroker(
            self.store,
            clock=self._clock,
        )
        self.adapters = adapters or AdapterRegistry(
            [
                ScriptedPlayerAdapter(),
                StockfishPlayerAdapter(self.engine),
                OpenAIResponsesAdapter(),
                AnthropicMessagesAdapter(),
                GeminiInteractionsAdapter(),
                OpenRouterChatAdapter(),
                OllamaChatAdapter(),
                VLLMChatAdapter(),
                RemoteRunnerAdapter(self.remote_runners),
            ]
        )
        self.provider_reliability = provider_reliability or ProviderReliabilityController()
        self.games: dict[str, GameSession] = {}
        self._game_locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._schedule_timeouts_enabled = schedule_timeouts
        self._schedule_agents_enabled = schedule_agents
        self._timeout_tasks: dict[str, asyncio.Task[None]] = {}
        self._engine_retry_tasks: dict[str, asyncio.Task[None]] = {}
        self._engine_retry_attempts: defaultdict[str, int] = defaultdict(int)
        self._agent_tasks: dict[str, asyncio.Task[None]] = {}
        self._analysis_cache: dict[tuple[str, int, int], GameAnalysis] = {}
        self._position_analysis_cache: dict[str, EngineAnalysis] = {}
        self._analysis_locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._worker_id = str(uuid4())
        self._closed = False

    async def start(self) -> None:
        self._closed = False
        await self.store.initialize()
        for game in await self.store.load_recoverable_games():
            self.games[game.id] = game
            self._schedule_timeout(game)
        for game in tuple(self.games.values()):
            self._schedule_agent_runner(game)

    async def create(self, request: CreateGameRequest) -> GameSession:
        white_player = request.white_player or PlayerConfiguration.human("white")
        black_player = request.black_player or (
            PlayerConfiguration.stockfish(
                "black",
                target_elo=request.stockfish_elo,
                move_time_ms=request.engine_move_time_ms,
            )
            if request.opponent is OpponentKind.STOCKFISH
            else PlayerConfiguration.human("black")
        )
        self.adapters.validate(white_player)
        self.adapters.validate(black_player)
        remote_players = [
            p for p in (white_player, black_player) if p.adapter_id == "remote_runner"
        ]
        if len({p.player_id for p in remote_players}) != len(remote_players):
            raise AdapterConfigurationError("Each remote seat requires its own pairing.")
        for player in remote_players:
            await self.remote_runners.validate_new_match(player)
        legacy_opponent = (
            OpponentKind.STOCKFISH
            if white_player.is_human and black_player.adapter_id == "stockfish"
            else OpponentKind.HUMAN
        )
        stockfish_player = next(
            (player for player in (white_player, black_player) if player.adapter_id == "stockfish"),
            None,
        )
        stockfish_elo = (
            int(stockfish_player.settings.get("target_elo", request.stockfish_elo))
            if stockfish_player
            else request.stockfish_elo
        )
        engine_move_time_ms = (
            int(
                stockfish_player.settings.get(
                    "move_time_ms",
                    request.engine_move_time_ms,
                )
            )
            if stockfish_player
            else request.engine_move_time_ms
        )
        game = GameSession(
            opponent=legacy_opponent,
            stockfish_elo=stockfish_elo,
            engine_move_time_ms=engine_move_time_ms,
            initial_time_ms=request.initial_time_ms,
            increment_ms=request.increment_ms,
            white_player=white_player,
            black_player=black_player,
        )
        if stockfish_player is not None:
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
                    "white_player": white_player.model_dump(mode="json"),
                    "black_player": black_player.model_dump(mode="json"),
                },
                now=now,
            )
        ]
        game.start(now=now)
        events.append(game.event("match.started", self._clock_payload(game, now), now=now))
        await self.store.create_game(game, events)
        self.games[game.id] = game
        self._schedule_timeout(game)
        self._schedule_agent_runner(game)
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
        await self.get(game_id)
        if self._game_locks[game_id].locked():
            # Writers work on private copies and publish only after persistence.
            # Do not make spectators wait for the next model/remote turn: a host
            # may need this committed snapshot before it can submit that turn.
            # The writer/timeout task still owns terminal-state adjudication.
            return deepcopy(self.games[game_id]).snapshot(now=self._clock())
        async with self._game_locks[game_id]:
            game = deepcopy(await self._reload(game_id))
            try:
                await self._expire_locked(game, self._clock())
            except ConcurrentGameUpdate:
                game = self.games[game_id]
            return game.snapshot(now=self._clock())

    async def make_human_move(
        self,
        game_id: str,
        uci: str,
        position_version: int,
        idempotency_key: str | None = None,
    ) -> GameSnapshot:
        await self.get(game_id)
        agent_task: asyncio.Task[None] | None = None
        async with self._game_locks[game_id]:
            request_hash = self._move_request_hash(uci, position_version)
            if idempotency_key is not None:
                replay = await self._idempotent_snapshot(
                    game_id,
                    idempotency_key,
                    request_hash,
                )
                if replay is not None:
                    return replay
            game = deepcopy(await self._reload(game_id))
            expected_revision = game.revision
            now = self._clock()
            if await self._expire_locked(game, now, expected_revision=expected_revision):
                raise ClockExpired(f"{game.timed_out_by.title()} lost on time.")
            side = "white" if game.board.turn is chess.WHITE else "black"
            if not game.player_for_color(side).is_human:
                raise MoveRejected(f"The {side} seat is controlled by an automated player.")
            move = game.apply_uci(
                uci,
                actor=f"human:{side}",
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
                    idempotency_key=idempotency_key,
                    request_hash=request_hash if idempotency_key is not None else None,
                )
                self.games[game.id] = game
            except ConcurrentGameUpdate as exc:
                await self._reload(game_id)
                if idempotency_key is not None:
                    replay = await self._idempotent_snapshot(
                        game_id,
                        idempotency_key,
                        request_hash,
                    )
                    if replay is not None:
                        return replay
                raise StalePosition("The match changed while this move was submitted.") from exc
            self._schedule_timeout(game)
            await self.broadcast(game, now=now)
            if self._automation_due(game):
                self._schedule_agent_runner(game)
                agent_task = self._agent_tasks.get(game.id)
        if agent_task is not None:
            await agent_task
        return await self.snapshot(game_id)

    async def reset(self, game_id: str) -> GameSnapshot:
        self._cancel_agent_runner(game_id)
        await self.get(game_id)
        async with self._game_locks[game_id]:
            game = deepcopy(await self._reload(game_id))
            expected_revision = game.revision
            now = self._clock()
            game.reset(now=now)
            payload = {"generation": game.generation, **self._clock_payload(game, now)}
            event = game.event("match.reset", payload, now=now)
            await self._record_action(game, [event], expected_revision)
            self._schedule_timeout(game)
            self._schedule_agent_runner(game)
            snapshot = game.snapshot(now=now)
            await self.broadcast(game, now=now)
            return snapshot

    async def resign(self, game_id: str, color: str = "white") -> GameSnapshot:
        self._cancel_agent_runner(game_id)
        await self.get(game_id)
        async with self._game_locks[game_id]:
            game = deepcopy(await self._reload(game_id))
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
        self._cancel_agent_runner(game_id)
        return await self._transition(game_id, MatchState.PAUSED, "match.paused")

    async def resume(self, game_id: str) -> GameSnapshot:
        snapshot = await self._transition(game_id, MatchState.RUNNING, "match.resumed")
        game = await self.get(game_id)
        self._schedule_agent_runner(game)
        return snapshot

    async def retry_agent_turn(self, game_id: str) -> GameSnapshot:
        """Explicitly resume a paused automated turn as an operator recovery action."""

        self._cancel_agent_runner(game_id)
        await self.get(game_id)
        async with self._game_locks[game_id]:
            game = deepcopy(await self._reload(game_id))
            if game.lifecycle is not MatchState.PAUSED:
                raise MatchTransitionRejected("Only a paused match can retry an agent turn.")
            player = game.active_player()
            if player.is_human:
                raise MatchTransitionRejected("The active seat is human-controlled.")
            expected_revision = game.revision
            now = self._clock()
            self.provider_reliability.allow_manual_probe(player.adapter_id, player.model)
            game.transition(MatchState.RUNNING, now=now)
            events = [
                game.event(
                    "agent.retry_requested",
                    {
                        "player_id": player.player_id,
                        "adapter_id": player.adapter_id,
                        "position_version": game.version,
                    },
                    now=now,
                ),
                game.event("match.resumed", self._clock_payload(game, now), now=now),
            ]
            await self._record_action(game, events, expected_revision)
            self._schedule_timeout(game)
            snapshot = game.snapshot(now=now)
            await self.broadcast(game, now=now)
            self._schedule_agent_runner(game)
            return snapshot

    async def abort(self, game_id: str) -> GameSnapshot:
        self._cancel_agent_runner(game_id)
        return await self._transition(game_id, MatchState.ABORTED, "match.aborted")

    async def adjudicate(self, game_id: str, result: str) -> GameSnapshot:
        self._cancel_agent_runner(game_id)
        await self.get(game_id)
        async with self._game_locks[game_id]:
            game = deepcopy(await self._reload(game_id))
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

    def provider_reliability_status(self) -> dict[str, object]:
        policy = self.provider_reliability.policy
        providers: list[dict[str, object]] = []
        for entry in self.adapters.catalog():
            adapter_id = str(entry["adapter_id"])
            if adapter_id not in PROVIDER_RETRY_ADAPTERS:
                continue
            for model in entry["models"]:
                providers.append(
                    {
                        "adapter_id": adapter_id,
                        "model": model,
                        **self.provider_reliability.status(adapter_id, model),
                    }
                )
        return {
            "policy": {
                "max_attempts": policy.max_attempts,
                "base_delay_ms": policy.base_delay_ms,
                "max_delay_ms": policy.max_delay_ms,
                "requests_per_minute": policy.requests_per_minute,
                "outage_threshold": policy.outage_threshold,
                "outage_cooldown_ms": policy.outage_cooldown_ms,
            },
            "providers": providers,
        }

    async def analysis(self, game_id: str) -> GameAnalysis:
        async with self._analysis_locks[game_id]:
            for _ in range(2):
                snapshot = await self.snapshot(game_id)
                cache_key = (game_id, snapshot.generation, snapshot.version)
                cached = self._analysis_cache.get(cache_key)
                if cached is not None:
                    return cached
                board = chess.Board(snapshot.initial_fen)
                boards = [board.copy(stack=True)]
                for move_record in snapshot.moves:
                    move = chess.Move.from_uci(move_record.uci)
                    if move not in board.legal_moves:
                        raise RuntimeError("Stored match history contains an illegal move.")
                    board.push(move)
                    boards.append(board.copy(stack=True))
                evaluations: list[EngineAnalysis] = []
                for position in boards:
                    fen = position.fen()
                    evaluation = self._position_analysis_cache.get(fen)
                    if evaluation is None:
                        evaluation = await self.analysis_engine.analyse_position(position)
                        self._position_analysis_cache[fen] = evaluation
                        if len(self._position_analysis_cache) > 4_096:
                            self._position_analysis_cache.pop(
                                next(iter(self._position_analysis_cache))
                            )
                    evaluations.append(evaluation)
                marker = await self.store.load_position_marker(game_id)
                if marker != (snapshot.generation, snapshot.version):
                    continue
                points = self._analysis_points(snapshot.moves, boards, evaluations)
                summary = await self.analysis_engine.summary(3200, 80)
                analysis = GameAnalysis(
                    game_id=game_id,
                    generation=snapshot.generation,
                    position_version=snapshot.version,
                    engine_name=summary.name,
                    engine_version=summary.version,
                    points=points,
                )
                self._analysis_cache = {
                    key: value for key, value in self._analysis_cache.items() if key[0] != game_id
                }
                self._analysis_cache[cache_key] = analysis
                return analysis
        raise AnalysisSuperseded("The match advanced while spectator analysis was running.")

    async def revision(self, game_id: str) -> tuple[int, int]:
        revision = await self.store.load_revision(game_id)
        if revision is None:
            raise GameNotFound(game_id)
        return revision

    async def acquire_turn_lease(
        self,
        game_id: str,
        owner_id: str,
        position_version: int,
        *,
        lease_ms: int = 15_000,
    ) -> TurnLease:
        if not 100 <= lease_ms <= 120_000:
            raise ValueError("lease_ms must be between 100 and 120000.")
        await self.get(game_id)
        return await self.store.acquire_turn_lease(
            game_id,
            owner_id,
            position_version,
            now=self._clock(),
            lease_ms=lease_ms,
        )

    async def renew_turn_lease(
        self,
        lease: TurnLease,
        *,
        lease_ms: int = 15_000,
    ) -> TurnLease:
        if not 100 <= lease_ms <= 120_000:
            raise ValueError("lease_ms must be between 100 and 120000.")
        return await self.store.renew_turn_lease(
            lease,
            now=self._clock(),
            lease_ms=lease_ms,
        )

    async def release_turn_lease(self, lease: TurnLease) -> bool:
        return await self.store.release_turn_lease(lease)

    async def subscribe(self, game_id: str, websocket: WebSocket) -> GameSnapshot:
        snapshot = await self.snapshot(game_id)
        await websocket.accept()
        await websocket.send_json({"type": "snapshot", "payload": snapshot.model_dump(mode="json")})
        return snapshot

    def unsubscribe(self, game_id: str, websocket: WebSocket) -> None:
        # Database-backed socket polling needs no process-local registration.
        return None

    async def broadcast(self, game: GameSession, *, now: datetime | None = None) -> None:
        # WebSockets poll the durable revision, which also observes commits made by
        # another API process. Redis fan-out can replace this Stage 2 mechanism later.
        return None

    async def close(self) -> None:
        self._closed = True
        tasks = list(self._timeout_tasks.values())
        self._timeout_tasks.clear()
        tasks.extend(self._engine_retry_tasks.values())
        self._engine_retry_tasks.clear()
        self._engine_retry_attempts.clear()
        tasks.extend(self._agent_tasks.values())
        self._agent_tasks.clear()
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        await self.engine.close()
        if self.analysis_engine is not self.engine:
            await self.analysis_engine.close()
        await self.remote_runners.close()
        await self.store.close()

    async def _complete_agent_turn(self, game: GameSession) -> bool:
        game = deepcopy(game)
        retry_fallback = deepcopy(game)
        expected_revision = game.revision
        now = self._clock()
        if not self._automation_due(game):
            return False
        color = "white" if game.board.turn is chess.WHITE else "black"
        player = game.player_for_color(color)
        adapter = self.adapters.get(player.adapter_id)
        white_remaining, black_remaining = game.remaining_times(now)
        remaining_ms = white_remaining if color == "white" else black_remaining
        configured_timeout = player.settings.get("move_timeout_ms", remaining_ms)
        requested_timeout = (
            configured_timeout if isinstance(configured_timeout, int) else remaining_ms
        )
        move_deadline_ms = max(1, min(remaining_ms, requested_timeout))
        lease_ms = min(120_000, max(5_000, move_deadline_ms + 5_000))
        try:
            if await self._expire_locked(game, now, expected_revision=expected_revision):
                return False
            lease = await self.acquire_turn_lease(
                game.id,
                f"{self._worker_id}:{player.player_id}",
                game.version,
                lease_ms=lease_ms,
            )
        except TurnLeaseUnavailable:
            await self._recover_engine_turn(
                game.id,
                retry_fallback,
                delay=lease_ms / 1_000,
            )
            return False
        except RETRYABLE_AGENT_TURN_ERRORS:
            await self._recover_engine_turn(game.id, retry_fallback)
            return False
        try:
            provider_call_started = False
            attempt = 1
            try:
                legal_moves = [move.uci() for move in game.board.legal_moves]
                request = PlayerMoveRequest(
                    match_id=game.id,
                    position_version=game.version,
                    color=color,
                    fen=game.board.fen(),
                    moves_uci=[record.uci for record in game.moves],
                    pgn=game.pgn(),
                    legal_moves=(
                        None if player.division.value == "pure_reasoning" else legal_moves
                    ),
                    remaining_ms=remaining_ms,
                    move_deadline_ms=max(1, move_deadline_ms),
                    division=player.division,
                )
                request._match_revision = expected_revision
                started = perf_counter()
                provider_call_started = player.adapter_id in PROVIDER_RETRY_ADAPTERS
                if provider_call_started:
                    proposal, lease, attempt = await self._call_provider_adapter_with_policy(
                        adapter,
                        request,
                        player,
                        lease,
                        lease_ms=lease_ms,
                        timeout_ms=max(1, move_deadline_ms),
                    )
                else:
                    proposal, lease = await self._call_adapter_with_lease(
                        adapter,
                        request,
                        player,
                        lease,
                        lease_ms=lease_ms,
                        timeout_ms=max(1, move_deadline_ms),
                    )
                elapsed_ms = max(0, round((perf_counter() - started) * 1_000))
                if (
                    proposal.request_id != request.request_id
                    or proposal.match_id != game.id
                    or proposal.position_version != game.version
                ):
                    await self._pause_for_invalid_proposal(
                        game,
                        expected_revision,
                        player,
                        "stale_or_mismatched_response",
                    )
                    return False
                try:
                    proposed_move = chess.Move.from_uci(proposal.move)
                except ValueError:
                    proposed_move = None
                if proposed_move is None or proposed_move not in game.board.legal_moves:
                    await self._pause_for_invalid_proposal(
                        game,
                        expected_revision,
                        player,
                        "illegal_move",
                    )
                    return False
                now = self._clock()
                if await self._expire_locked(game, now, expected_revision=expected_revision):
                    return False
                metadata = PlayerMoveMetadata(
                    player_id=player.player_id,
                    adapter_id=player.adapter_id,
                    provider=player.provider,
                    model=player.model,
                    effort=player.effort,
                    division=player.division,
                    latency_ms=elapsed_ms,
                    plan=proposal.plan,
                    threat=proposal.threat,
                    confidence=proposal.confidence,
                    usage=proposal.usage,
                    attempt=attempt,
                )
                move = game.apply_uci(
                    proposal.move,
                    actor=f"{player.adapter_id}:{color}",
                    now=now,
                    player_metadata=metadata,
                )
                move.elapsed_ms = elapsed_ms
                events = [game.event("move.accepted", self._move_payload(move), now=now)]
                if game.lifecycle is MatchState.COMPLETED:
                    events.append(game.event("match.completed", {"result": game.result}, now=now))
                await self.store.record_move(
                    game,
                    move,
                    events,
                    expected_revision=expected_revision,
                    turn_lease=lease,
                    lease_now=now,
                )
                self.games[game.id] = game
                self._engine_retry_attempts.pop(game.id, None)
                self._schedule_timeout(game)
                await self.broadcast(game, now=now)
                return True
            except ProviderRecoveryRequired as exc:
                await self._pause_for_invalid_proposal(
                    game,
                    expected_revision,
                    player,
                    exc.reason,
                    details={
                        "category": exc.category,
                        "attempts": exc.attempts,
                        "retry_after_ms": exc.retry_after_ms,
                        "operator_action": "retry_agent_turn",
                    },
                )
                return False
            except RETRYABLE_AGENT_TURN_ERRORS:
                if provider_call_started:
                    try:
                        await self._pause_for_invalid_proposal(
                            retry_fallback,
                            expected_revision,
                            player,
                            "provider_turn_interrupted",
                            details={
                                "attempts": attempt,
                                "operator_action": "retry_agent_turn",
                            },
                        )
                    except (*RETRYABLE_DATABASE_ERRORS, ConcurrentGameUpdate):
                        # The provider call may already be billable. Never dispatch it
                        # again automatically just because recovery cannot be persisted.
                        pass
                    return False
                await self._recover_engine_turn(game.id, retry_fallback)
                return False
            except RunnerTrustError:
                # A revoke can win after proposal receipt but before commit. Reload
                # the unmodified board before pausing; never retain the tentative move.
                game = await self.store.load_game(game.id)
                if game is not None:
                    await self._pause_for_invalid_proposal(
                        game, game.revision, player, "runner_authorization_unavailable"
                    )
                return False
            except AdapterError:
                await self._pause_for_invalid_proposal(
                    game,
                    expected_revision,
                    player,
                    "adapter_error",
                )
                return False
        finally:
            try:
                await self.release_turn_lease(lease)
            except SQLAlchemyError:
                # The expiring lease is recoverable even when release cannot reach the DB.
                pass

    async def _call_provider_adapter_with_policy(
        self,
        adapter: PlayerAdapter,
        request: PlayerMoveRequest,
        player: PlayerConfiguration,
        lease: TurnLease,
        *,
        lease_ms: int,
        timeout_ms: int,
    ):
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout_ms / 1_000
        policy = self.provider_reliability.policy
        current_lease = lease
        attempts = 0
        failure_category = "transient"
        retry_after_ms: int | None = None

        while attempts < policy.max_attempts:
            remaining_ms = max(0, round((deadline - loop.time()) * 1_000))
            if remaining_ms <= 0:
                break
            try:
                self.provider_reliability.before_attempt(player.adapter_id, player.model)
            except ProviderRecoveryRequired as exc:
                if attempts == 0:
                    raise
                raise ProviderRecoveryRequired(
                    str(exc),
                    reason=exc.reason,
                    category=exc.category,
                    attempts=attempts,
                    retry_after_ms=exc.retry_after_ms,
                ) from exc
            attempts += 1
            try:
                proposal, current_lease = await self._call_adapter_with_lease(
                    adapter,
                    request,
                    player,
                    current_lease,
                    lease_ms=lease_ms,
                    timeout_ms=remaining_ms,
                )
            except RetryableAdapterError as exc:
                failure_category = exc.category
                retry_after_ms = exc.retry_after_ms
                if attempts >= policy.max_attempts:
                    break
                if retry_after_ms is not None and retry_after_ms > policy.max_delay_ms:
                    break
                delay_ms = policy.retry_delay_ms(attempts, retry_after_ms)
                remaining_after_delay_ms = round((deadline - loop.time()) * 1_000) - delay_ms
                if remaining_after_delay_ms < 100:
                    break
                if delay_ms:
                    await asyncio.sleep(delay_ms / 1_000)
                continue
            self.provider_reliability.record_success(player.adapter_id, player.model)
            return proposal, current_lease, attempts

        circuit_retry_after_ms = self.provider_reliability.record_failure(
            player.adapter_id,
            player.model,
        )
        if circuit_retry_after_ms is not None:
            retry_after_ms = max(retry_after_ms or 0, circuit_retry_after_ms)
        raise ProviderRecoveryRequired(
            "The provider retry budget was exhausted.",
            reason="provider_retry_exhausted",
            category=failure_category,
            attempts=attempts,
            retry_after_ms=retry_after_ms,
        )

    async def _call_adapter_with_lease(
        self,
        adapter: PlayerAdapter,
        request: PlayerMoveRequest,
        player: PlayerConfiguration,
        lease: TurnLease,
        *,
        lease_ms: int,
        timeout_ms: int,
    ):
        call = asyncio.create_task(adapter.choose_move(request, player))
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout_ms / 1_000
        current_lease = lease
        renewal_interval = max(0.1, lease_ms / 3_000)
        try:
            while True:
                remaining = deadline - loop.time()
                if remaining <= 0:
                    raise AdapterError("The player exceeded the authoritative move deadline.")
                try:
                    proposal = await asyncio.wait_for(
                        asyncio.shield(call),
                        timeout=min(remaining, renewal_interval),
                    )
                    return proposal, current_lease
                except TimeoutError:
                    if call.done():
                        return call.result(), current_lease
                    if loop.time() >= deadline:
                        raise AdapterError(
                            "The player exceeded the authoritative move deadline."
                        ) from None
                    current_lease = await self.renew_turn_lease(
                        current_lease,
                        lease_ms=lease_ms,
                    )
        finally:
            if not call.done():
                call.cancel()
                await asyncio.gather(call, return_exceptions=True)

    async def _pause_for_invalid_proposal(
        self,
        game: GameSession,
        expected_revision: int,
        player: PlayerConfiguration,
        reason: str,
        *,
        details: dict[str, object] | None = None,
    ) -> None:
        now = self._clock()
        game.pause(now=now)
        failure_payload: dict[str, object] = {
            "player_id": player.player_id,
            "adapter_id": player.adapter_id,
            "reason": reason,
        }
        if details:
            failure_payload.update(
                {key: value for key, value in details.items() if value is not None}
            )
        events = [
            game.event(
                "agent.failed",
                failure_payload,
                now=now,
            ),
            game.event("match.paused", self._clock_payload(game, now), now=now),
        ]
        await self._record_action(game, events, expected_revision)
        self._cancel_timeout(game.id)
        await self.broadcast(game, now=now)

    @staticmethod
    def _automation_due(game: GameSession) -> bool:
        return (
            game.lifecycle is MatchState.RUNNING
            and game.status.value == "active"
            and not game.active_player().is_human
        )

    def _schedule_agent_runner(self, game: GameSession) -> None:
        if self._closed or not self._schedule_agents_enabled or not self._automation_due(game):
            return
        existing = self._agent_tasks.get(game.id)
        if existing is not None and not existing.done():
            return
        self._agent_tasks[game.id] = asyncio.create_task(self._run_agent_turns(game.id))

    def _cancel_agent_runner(self, game_id: str) -> None:
        task = self._agent_tasks.pop(game_id, None)
        if task is not None and task is not asyncio.current_task():
            task.cancel()

    async def _run_agent_turns(self, game_id: str, *, max_plies: int = 512) -> None:
        task = asyncio.current_task()
        completed = 0
        try:
            while not self._closed and completed < max_plies:
                async with self._game_locks[game_id]:
                    game = await self._reload(game_id)
                    if not self._automation_due(game):
                        return
                    advanced = await self._complete_agent_turn(game)
                    if not advanced:
                        return
                    completed += 1
                    next_game = self.games[game_id]
                    delay_ms = next_game.active_player().settings.get("spectator_delay_ms", 0)
                if isinstance(delay_ms, int) and delay_ms > 0:
                    await asyncio.sleep(min(delay_ms, 2_000) / 1_000)
                else:
                    await asyncio.sleep(0)
            if completed >= max_plies:
                await self.pause(game_id)
        except (asyncio.CancelledError, GameNotFound):
            return
        finally:
            if self._agent_tasks.get(game_id) is task:
                self._agent_tasks.pop(game_id, None)

    async def wait_for_automation(self, game_id: str, *, timeout: float = 10.0) -> GameSnapshot:
        task = self._agent_tasks.get(game_id)
        if task is not None:
            await asyncio.wait_for(asyncio.shield(task), timeout=timeout)
        return await self.snapshot(game_id)

    async def _transition(
        self,
        game_id: str,
        target: MatchState,
        event_type: str,
    ) -> GameSnapshot:
        await self.get(game_id)
        async with self._game_locks[game_id]:
            game = deepcopy(await self._reload(game_id))
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
            async with self._game_locks[game_id]:
                game = deepcopy(await self._reload(game_id))
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
            async with self._game_locks[game_id]:
                game = deepcopy(await self._reload(game_id))
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

    def _schedule_engine_retry(self, game_id: str, delay: float | None = None) -> None:
        existing = self._engine_retry_tasks.get(game_id)
        if existing is not None and existing is not asyncio.current_task() and not existing.done():
            return
        self._engine_retry_attempts[game_id] += 1
        attempt = self._engine_retry_attempts[game_id]
        retry_delay = delay if delay is not None else min(10.0, 0.5 * (2 ** (attempt - 1)))
        task = asyncio.create_task(self._retry_engine_turn_after(game_id, retry_delay))
        self._engine_retry_tasks[game_id] = task

    async def _retry_engine_turn_after(self, game_id: str, delay: float) -> None:
        task = asyncio.current_task()
        try:
            await asyncio.sleep(delay)
            if self._closed:
                return
            async with self._game_locks[game_id]:
                game = await self._reload(game_id)
                if self._automation_due(game):
                    advanced = await self._complete_agent_turn(game)
                    if advanced:
                        self._schedule_agent_runner(self.games[game_id])
                else:
                    self._engine_retry_attempts.pop(game_id, None)
        except (asyncio.CancelledError, GameNotFound):
            return
        except RETRYABLE_DATABASE_ERRORS:
            if not self._closed:
                self._schedule_engine_retry(game_id)
        finally:
            if self._engine_retry_tasks.get(game_id) is task:
                self._engine_retry_tasks.pop(game_id, None)

    async def _recover_engine_turn(
        self,
        game_id: str,
        fallback: GameSession,
        *,
        delay: float | None = None,
    ) -> None:
        try:
            current = await self._reload(game_id)
        except RETRYABLE_DATABASE_ERRORS:
            current = fallback
        except GameNotFound:
            self._engine_retry_attempts.pop(game_id, None)
            return
        if self._automation_due(current):
            self._schedule_engine_retry(game_id, delay)
        else:
            self._engine_retry_attempts.pop(game_id, None)

    async def _idempotent_snapshot(
        self,
        game_id: str,
        idempotency_key: str,
        request_hash: str,
    ) -> GameSnapshot | None:
        persisted_hash = await self.store.get_idempotency_hash(
            game_id,
            "move",
            idempotency_key,
        )
        if persisted_hash is None:
            return None
        if persisted_hash != request_hash:
            raise IdempotencyConflict(
                "The idempotency key was already used for a different move request."
            )
        game = await self._reload(game_id)
        return game.snapshot(now=self._clock())

    @staticmethod
    def _move_request_hash(uci: str, position_version: int) -> str:
        normalized = f"human|{position_version}|{uci.strip().lower()}"
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

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
            self.games[game.id] = game
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
        payload = {
            "generation": move.generation,
            "ply": move.ply,
            "uci": move.uci,
            "san": move.san,
            "actor": move.actor,
            "elapsed_ms": move.elapsed_ms,
            "white_remaining_ms": move.white_remaining_ms,
            "black_remaining_ms": move.black_remaining_ms,
        }
        if move.player_metadata is not None:
            payload["player_metadata"] = move.player_metadata.model_dump(mode="json")
        return payload

    @staticmethod
    def _analysis_points(
        moves,
        boards: list[chess.Board],
        evaluations: list[EngineAnalysis],
    ) -> list[AnalysisPoint]:
        points: list[AnalysisPoint] = []
        for ply, (board, evaluation) in enumerate(zip(boards, evaluations, strict=True)):
            classification = None
            if ply > 0:
                previous = evaluations[ply - 1]
                move = moves[ply - 1]
                if previous.best_move == move.uci:
                    classification = "best"
                else:
                    loss = (
                        previous.score_cp - evaluation.score_cp
                        if ply % 2 == 1
                        else evaluation.score_cp - previous.score_cp
                    )
                    classification = GameManager._classify_loss(max(0, loss))
            points.append(
                AnalysisPoint(
                    ply=ply,
                    fen=board.fen(),
                    score_cp=evaluation.score_cp,
                    mate=evaluation.mate,
                    best_move=evaluation.best_move,
                    pv_san=list(evaluation.pv_san),
                    depth=evaluation.depth,
                    classification=classification,
                )
            )
        return points

    @staticmethod
    def _classify_loss(loss_cp: int) -> str:
        if loss_cp <= 20:
            return "excellent"
        if loss_cp <= 60:
            return "good"
        if loss_cp <= 120:
            return "inaccuracy"
        if loss_cp <= 250:
            return "mistake"
        return "blunder"
