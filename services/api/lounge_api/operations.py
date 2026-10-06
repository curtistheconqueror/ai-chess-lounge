"""Bounded, process-local operational signals. No external telemetry or raw inputs."""

from __future__ import annotations

import asyncio
from collections import deque
from time import monotonic
from uuid import uuid4

from sqlalchemy import text


class Readiness:
    """One shared DB probe, with bounded caller wait and no connection cancellation."""

    def __init__(self, manager, worker, *, wait_seconds=0.25, freshness_seconds=2.0):
        self.manager = manager
        self.worker = worker
        self.wait_seconds = wait_seconds
        self.freshness_seconds = freshness_seconds
        self.started = False
        self.probe = None
        self.checked_at = None
        self.database_ok = False

    async def _probe(self):
        try:
            async with self.manager.store.engine.connect() as connection:
                self.database_ok = await connection.scalar(text("SELECT 1")) == 1
        except Exception:
            # Exception text may contain URLs, queries or driver details.
            self.database_ok = False
        finally:
            self.checked_at = monotonic()

    async def check(self, *, require_engine=False):
        if self.started and (
            self.checked_at is None or monotonic() - self.checked_at > self.freshness_seconds
        ):
            if self.probe is None or self.probe.done():
                self.probe = asyncio.create_task(self._probe())
            try:
                # A timeout returns unavailable without cancelling aiosqlite connection
                # creation. Subsequent callers share this same task until it settles.
                await asyncio.wait_for(asyncio.shield(self.probe), self.wait_seconds)
            except TimeoutError:
                pass
        database = bool(
            self.started
            and self.database_ok
            and self.checked_at is not None
            and monotonic() - self.checked_at <= self.freshness_seconds
        )
        worker = bool(
            self.started
            and not self.worker.closed
            and self.worker.task is not None
            and not self.worker.task.done()
            and self.worker.last_success_at is not None
            and monotonic() - self.worker.last_success_at <= 5.0
        )
        engine = bool(self.manager.engine.available)
        return {
            "ok": database and worker and (engine or not require_engine),
            "checks": {"database": database, "worker": worker, "engine": engine},
            "engine_required": require_engine,
        }

    async def close(self):
        self.started = False
        if self.probe is not None:
            # Drain the sole probe before store disposal; do not orphan a connection.
            await asyncio.gather(self.probe, return_exceptions=True)


class LocalOperations:
    """Fixed-capacity request summaries, accessible only through application state."""

    def __init__(self):
        self.http = {}
        self.recent = deque(maxlen=100)
        self.active_websockets = 0
        self.opened_websockets = 0

    def record(self, scope, status, elapsed_ms, request_id):
        method = scope.get("method", "")
        if method not in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}:
            method = "OTHER"
        route = getattr(scope.get("route"), "path", "<unmatched>")
        family = status // 100 if 100 <= status <= 599 else 5
        key = (method, route, family)
        if key not in self.http and len(self.http) >= 127:
            key = ("OTHER", "<overflow>", 0)
        row = self.http.setdefault(key, {"count": 0, "total_ms": 0.0, "max_ms": 0.0})
        row["count"] += 1
        row["total_ms"] += elapsed_ms
        row["max_ms"] = max(row["max_ms"], elapsed_ms)
        self.recent.append(
            {
                "request_id": request_id,
                "method": key[0],
                "route": key[1],
                "status_family": key[2],
                "duration_ms": elapsed_ms,
            }
        )

    def snapshot(self):
        return {
            "schema_version": "1.0",
            "scope": "process_local",
            "http": [
                {"method": key[0], "route": key[1], "status_family": key[2], **row}
                for key, row in self.http.items()
            ],
            "recent": [dict(row) for row in self.recent],
            "websockets": {"active": self.active_websockets, "opened": self.opened_websockets},
        }


class OperationsMiddleware:
    def __init__(self, app, operations):
        self.app = app
        self.operations = operations

    async def __call__(self, scope, receive, send):
        if scope["type"] == "websocket":
            accepted = False

            async def tracked_socket_send(message):
                nonlocal accepted
                if message["type"] == "websocket.accept" and not accepted:
                    accepted = True
                    self.operations.active_websockets += 1
                    self.operations.opened_websockets += 1
                await send(message)

            try:
                await self.app(scope, receive, tracked_socket_send)
            finally:
                if accepted:
                    self.operations.active_websockets -= 1
            return
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request_id, started, status = str(uuid4()), monotonic(), 500

        async def tracked_send(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                headers = [
                    (k, v) for k, v in message.get("headers", []) if k.lower() != b"x-request-id"
                ]
                message = {**message, "headers": headers + [(b"x-request-id", request_id.encode())]}
            await send(message)

        try:
            await self.app(scope, receive, tracked_send)
        except BaseException:
            status = 500
            raise
        finally:
            self.operations.record(scope, status, (monotonic() - started) * 1000, request_id)
