"""Single-host batch executor using durable queue and existing fenced turn runners."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from time import monotonic

from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from .domain import MatchTransitionRejected
from .experiment_queue import QueueConflict
from .experiments import ExperimentService, parse_configuration
from .manager import GameNotFound
from .models import CreateGameRequest
from .persistence import ConcurrentGameUpdate
from .player_protocol import PlayerConfiguration


class ExperimentWorker:
    def __init__(self, manager):
        self.manager = manager
        self.queue = manager.experiment_queue
        self.plans = ExperimentService(manager.store, manager.adapters)
        self.task = None
        self.jobs = {}
        self.closed = False
        self.last_success_at = None

    def start(self):
        self.closed = False
        self.last_success_at = None
        self.task = asyncio.create_task(self._loop())

    async def close(self):
        self.closed = True
        tasks = ([self.task] if self.task else []) + list(self.jobs.values())
        # Let current database transactions finish before disposing the store.
        # Cancelling aiosqlite during connection creation can leak its connection.
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self.jobs.clear()

    async def control(self, run_id, target, revision, allow_provider_calls=False):
        run = await self.queue.snapshot(run_id)
        if target == "running":
            saved = await self.plans.get(run["experiment_id"])
            plan = saved["document"]
            has_provider = any(
                v["player"]["connection_mode"] == "direct_api" for v in plan["variants"]
            )
            if has_provider and not allow_provider_calls:
                raise ValueError("Explicit provider-call authorization is required for this batch.")
            current = self.plans.preview(parse_configuration(plan["configuration"]))
            if current["configuration_hash"] != plan["configuration_hash"]:
                raise ValueError(
                    "Adapter configuration changed. Create a fresh plan before execution."
                )
        result = await self.queue.transition(
            run_id, "pausing" if target == "paused" else target, revision
        )
        if target in {"paused", "cancelled"}:
            await self._stop_games(result, pause=target == "paused")
            if target == "paused":
                try:
                    result = await self.queue.transition(run_id, "paused", result["revision"])
                except QueueConflict:
                    result = await self.queue.snapshot(run_id)
                    if result["state"] != "paused":
                        raise
        return result

    async def _stop_games(self, run, *, pause=False):
        for job in run["jobs"]:
            if not job["has_game"]:
                continue
            if await self.queue.state(run["id"]) != run["state"]:
                return
            try:
                game = await self.manager.get(job["id"])
                if game.lifecycle.value == "running" or (
                    not pause and game.lifecycle.value == "paused"
                ):
                    if pause:
                        await self.manager.pause(game.id, experiment_control=True)
                    else:
                        await self.manager.abort(game.id)
            except (GameNotFound, MatchTransitionRejected, ConcurrentGameUpdate):
                pass

    async def tick(self):
        now = datetime.now(UTC)
        for run_id in await self.queue.active_runs():
            await self.queue.expire(run_id, now=now)
            run = await self.queue.snapshot(run_id)
            if run["state"] != "running":
                await self._stop_games(run, pause=run["state"] in {"paused", "pausing"})
                if run["state"] == "pausing":
                    await self.queue.transition(run_id, "paused", run["revision"])
                continue
            while not self.closed:
                claim = await self.queue.claim(run_id, now=datetime.now(UTC))
                if claim is None or self.closed:
                    break
                prior = self.jobs.get(claim["id"])
                if prior is not None and not prior.done():
                    prior.cancel()
                    await asyncio.gather(prior, return_exceptions=True)
                self.jobs[claim["id"]] = asyncio.create_task(
                    self._work(claim, run["experiment_id"])
                )

    async def _loop(self):
        while not self.closed:
            try:
                await self.tick()
                self.last_success_at = monotonic()
            except (SQLAlchemyError, QueueConflict, ConcurrentGameUpdate):
                # Durable reservations survive; retry orchestration, never invent a new job ID.
                pass
            await asyncio.sleep(0.5)

    async def _work(self, claim, experiment_id):
        job_id, token = claim["id"], claim["lease_token"]
        task = asyncio.current_task()
        try:
            saved = await self.plans.get(experiment_id)
            plan = saved["document"]
            item = plan["schedule"][claim["number"] - 1]
            variants = {v["key"]: v["player"] for v in plan["variants"]}
            created = False
            try:
                game = await self.manager.get(job_id)
            except GameNotFound:
                config = plan["configuration"]
                try:
                    game = await self.manager.create(
                        CreateGameRequest(
                            white_player=PlayerConfiguration.model_validate(
                                variants[claim.get("white", item["white"])]
                            ),
                            black_player=PlayerConfiguration.model_validate(
                                variants[claim.get("black", item["black"])]
                            ),
                            initial_time_ms=config["initial_time_ms"],
                            increment_ms=config["increment_ms"],
                        ),
                        experiment_job=claim,
                        initial_fen=item["initial_fen"],
                    )
                    created = True
                except IntegrityError:
                    # Crash recovery or another claimant already persisted this exact game.
                    game = await self.manager.get(job_id)
            if not created and game.lifecycle.value == "running":
                # A crash may have happened after dispatch but before persistence.
                # Never infer that replaying this position is free or idempotent.
                await self.manager.abort(job_id)
            elif game.lifecycle.value == "paused":
                events = await self.manager.events(job_id)
                last_pause = next(
                    (
                        e
                        for e in reversed(events)
                        if e.type
                        in {"match.paused", "experiment.paused", "experiment.turn_stopped"}
                    ),
                    None,
                )
                if last_pause and (
                    last_pause.type == "experiment.paused"
                    or (
                        last_pause.type == "experiment.turn_stopped"
                        and last_pause.payload.get("reason") == "paused"
                    )
                ):
                    await self.manager.adopt_experiment_claim(job_id, token)
                    await self.manager.resume(job_id)
                # Provider/lease failure pauses are settled as failed below.

            while not self.closed:
                if not await self.queue.renew(job_id, token, now=datetime.now(UTC)):
                    return
                snapshot = await self.manager.snapshot(job_id)
                if snapshot.lifecycle.value in {"completed", "adjudicated", "aborted", "paused"}:
                    result = (
                        snapshot.result if snapshot.lifecycle.value == "completed" else "failed"
                    )
                    if snapshot.lifecycle.value == "aborted":
                        events = await self.manager.events(job_id)
                        if any(
                            e.type == "experiment.turn_stopped"
                            and e.payload.get("reason") == "ply_limit"
                            for e in events
                        ):
                            result = "limited"
                    await self.queue.finish(job_id, token, result, now=datetime.now(UTC))
                    return
                await asyncio.sleep(0.2)
        except (QueueConflict, ConcurrentGameUpdate, SQLAlchemyError):
            return
        except asyncio.CancelledError:
            raise
        except (ValueError, RuntimeError):
            # Never persist provider messages or raw exceptions in batch metadata.
            try:
                await self.queue.finish(job_id, token, "failed", now=datetime.now(UTC))
            except QueueConflict:
                pass
        finally:
            if self.jobs.get(job_id) is task:
                self.jobs.pop(job_id, None)
