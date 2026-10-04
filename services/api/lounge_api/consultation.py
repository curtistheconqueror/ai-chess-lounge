"""Position-bound advice; only a separate human command can play a suggestion."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import datetime, timedelta
from time import perf_counter
from typing import TYPE_CHECKING
from uuid import uuid4

import chess
from sqlalchemy.exc import SQLAlchemyError

from .adapters import AdapterConfigurationError, AdapterError
from .domain import ClockExpired, MatchTransitionRejected, StalePosition
from .engine import EngineFailure
from .models import Consultation, ConsultationRequest, MatchState
from .persistence import ConcurrentGameUpdate, TurnLeaseUnavailable
from .player_protocol import MoveRequest
from .provider_reliability import ProviderRecoveryRequired

if TYPE_CHECKING:
    from .manager import GameManager

PROVIDERS = frozenset({"openai", "anthropic", "google", "openrouter", "ollama", "vllm"})
ADVISORS = PROVIDERS | {"stockfish", "scripted"}


class ConsultationService:
    def __init__(self, manager: GameManager):
        self.manager = manager
        self.tasks: dict[str, asyncio.Task] = {}

    async def request(self, game_id: str, command: ConsultationRequest):
        m = self.manager
        await m.get(game_id)
        async with m._game_locks[game_id]:
            game = deepcopy(await m._reload(game_id))
            now = m._clock()
            if game.revision != command.expected_revision:
                raise StalePosition("The match changed. Refresh before requesting advice.")
            if game.lifecycle is not MatchState.RUNNING or not game.active_player().is_human:
                raise MatchTransitionRejected("Advice requires a running human turn.")
            if await m._expire_locked(game, now, expected_revision=game.revision):
                raise ClockExpired("The human clock expired.")
            if any(item.status == "pending" for item in game.consultation_snapshots(now)):
                raise MatchTransitionRejected(
                    "A consultation is already thinking for this position."
                )
            if len(game.consultations) >= 1000:
                raise MatchTransitionRejected("This game has reached its consultation limit.")
            advisor = command.advisor.model_copy(deep=True)
            if advisor.adapter_id not in ADVISORS:
                raise AdapterConfigurationError(
                    "Choose Stockfish, a direct API or local model adviser."
                )
            if advisor.adapter_id == "stockfish" and advisor.division.value != "engine_assisted":
                raise AdapterConfigurationError("Stockfish advice must disclose engine assistance.")
            m.adapters.validate(advisor)
            color = "white" if game.board.turn else "black"
            if advisor.settings.get("color", color) != color:
                raise AdapterConfigurationError("The adviser profile belongs to the other color.")
            remaining = game.remaining_times(now)[0 if color == "white" else 1]
            timeout = min(30_000, remaining, advisor.settings.get("move_timeout_ms", 20_000))
            expected = game.revision
            game.revision += 1
            game.updated_at = now
            item = Consultation(
                id=str(uuid4()),
                color=color,
                advisor=advisor,
                position_version=game.version,
                revision=game.revision,
                after_ply=len(game.moves),
                status="pending",
                timestamp=now.isoformat(),
                deadline_at=(now + timedelta(milliseconds=timeout)).isoformat(),
            )
            game.consultations.append(item)
            await m._record_action(
                game,
                [game.event("consultation.requested", item.model_dump(mode="json"), now=now)],
                expected,
            )
            self.tasks[item.id] = asyncio.create_task(self._run(deepcopy(game), item.id, timeout))
            return game.snapshot(now=now)

    async def cancel(self, game_id: str, advice_id: str, expected_revision: int):
        m = self.manager
        await m.get(game_id)
        async with m._game_locks[game_id]:
            game = deepcopy(await m._reload(game_id))
            if game.revision != expected_revision:
                raise StalePosition("The match changed. Refresh before cancelling advice.")
            item = next((i for i in game.consultations if i.id == advice_id), None)
            if item is None or item.status != "pending":
                raise MatchTransitionRejected("There is no pending consultation to cancel.")
            item.status = "cancelled"
            game.revision += 1
            game.updated_at = m._clock()
            await m._record_action(
                game,
                [game.event("consultation.cancelled", {"id": item.id}, now=game.updated_at)],
                expected_revision,
            )
            task = self.tasks.get(advice_id)
            if task:
                task.cancel()
            return game.snapshot(now=m._clock())

    async def _run(self, game, advice_id: str, timeout_ms: int):
        m = self.manager
        item = next(i for i in game.consultations if i.id == advice_id)
        lease = None
        call = None
        started = perf_counter()
        try:
            current = await m.store.load_game(game.id)
            if current is None or current.revision != item.revision:
                return
            if m._clock() >= datetime.fromisoformat(item.deadline_at):
                await self._finish(game, item)
                return
            lease = await m.acquire_turn_lease(
                game.id, f"consult:{advice_id}", game.version, lease_ms=timeout_ms + 5000
            )
            # A human move may win between the initial read and lease acquisition.
            current = await m.store.load_game(game.id)
            if current is None or current.revision != item.revision:
                return
            if m._clock() >= datetime.fromisoformat(item.deadline_at):
                await self._finish(game, item)
                return
            request = MoveRequest(
                match_id=game.id,
                position_version=game.version,
                color=item.color,
                fen=game.board.fen(),
                moves_uci=[move.uci for move in game.moves],
                pgn=game.pgn(),
                legal_moves=None
                if item.advisor.division.value == "pure_reasoning"
                else [move.uci() for move in game.board.legal_moves],
                remaining_ms=game.remaining_times(m._clock())[0 if item.color == "white" else 1],
                move_deadline_ms=timeout_ms,
                division=item.advisor.division,
            )
            request._match_revision = item.revision
            adapter = m.adapters.get(item.advisor.adapter_id)
            method = (
                m._call_provider_adapter_with_policy
                if item.advisor.adapter_id in PROVIDERS
                else m._call_adapter_with_lease
            )
            call = asyncio.create_task(
                method(
                    adapter,
                    request,
                    item.advisor,
                    lease,
                    lease_ms=timeout_ms + 5000,
                    timeout_ms=timeout_ms,
                )
            )
            while not call.done():
                done, _ = await asyncio.wait({call}, timeout=0.2)
                if done:
                    break
                current = await m.store.load_game(game.id)
                if (
                    current is None
                    or current.revision != item.revision
                    or m._clock() >= datetime.fromisoformat(item.deadline_at)
                ):
                    call.cancel()
                    await asyncio.gather(call, return_exceptions=True)
                    if current is not None and current.revision == item.revision:
                        await self._finish(game, item)
                    return
            result = await call
            proposal = result[0]
            item.attempts = result[2] if len(result) == 3 else 1
            if (
                proposal.request_id != request.request_id
                or proposal.match_id != game.id
                or proposal.position_version != game.version
            ):
                raise AdapterError("Mismatched advice")
            try:
                move = chess.Move.from_uci(proposal.move)
            except ValueError:
                raise AdapterError("Invalid advice") from None
            if move not in game.board.legal_moves:
                raise AdapterError("Illegal advice")
            item.status = "ready"
            item.move, item.san = proposal.move, game.board.san(move)
            item.plan, item.threat, item.confidence = (
                proposal.plan,
                proposal.threat,
                proposal.confidence,
            )
            item.usage = proposal.usage
            item.latency_ms = max(0, round((perf_counter() - started) * 1000))
            await self._finish(game, item)
        except (AdapterError, EngineFailure, ProviderRecoveryRequired, TurnLeaseUnavailable):
            item.status = "failed"
            item.error = "Advice unavailable. You can still play or request again."
            item.latency_ms = max(0, round((perf_counter() - started) * 1000))
            await self._finish(game, item)
        except (ConcurrentGameUpdate, SQLAlchemyError):
            # Never retry a possibly billable consultation after an uncertain write.
            # Its persisted deadline permits explicit operator recovery.
            return
        finally:
            if call is not None and not call.done():
                call.cancel()
                await asyncio.gather(call, return_exceptions=True)
            if lease is not None:
                try:
                    await m.release_turn_lease(lease)
                except SQLAlchemyError:
                    pass
            self.tasks.pop(advice_id, None)

    async def _finish(self, original, item):
        try:
            await self._persist_finish(original, item)
        except (ConcurrentGameUpdate, SQLAlchemyError):
            # The original persisted deadline remains the recovery boundary.
            return

    async def _persist_finish(self, original, item):
        m = self.manager
        async with m._game_locks[original.id]:
            game = deepcopy(await m._reload(original.id))
            if game.revision != item.revision or game.version != item.position_version:
                return
            now = m._clock()
            if await m._expire_locked(game, now, expected_revision=game.revision):
                return
            if now >= datetime.fromisoformat(item.deadline_at):
                item.status = "failed"
                item.move = item.san = item.plan = item.threat = None
                item.error = "The consultation deadline expired. You can request again."
            expected = game.revision
            game.revision += 1
            item.revision = game.revision
            game.updated_at = now
            game.consultations = [item if c.id == item.id else c for c in game.consultations]
            try:
                await m._record_action(
                    game,
                    [
                        game.event(
                            "consultation." + item.status, item.model_dump(mode="json"), now=now
                        )
                    ],
                    expected,
                )
            except ConcurrentGameUpdate:
                return

    async def close(self):
        owned = set(self.tasks)
        tasks = list(self.tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        for game in list(self.manager.games.values()):
            for item in game.consultations:
                if item.id in owned and item.status == "pending":
                    cancelled = item.model_copy(update={"status": "cancelled"})
                    await self._finish(game, cancelled)
