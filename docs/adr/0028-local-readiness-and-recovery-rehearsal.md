# ADR 0028: Local readiness and isolated native recovery rehearsal

- Status: Proposed (Stage 8B dependent draft)
- Date: 2026-10-04

## Decision

Keep `/api/health` as compatible process liveness. Add `/api/ready`, which returns
200 only when application startup is complete, a database SELECT 1 probe is fresh
and successful, and the local batch worker has completed a tick within five seconds.
It returns 503 otherwise. Stockfish availability is reported but required only with
`require_engine=true`: human/reference/provider matches need not depend on Stockfish.
Availability does not mean an engine analysis, provider call or active game is healthy.
Responses contain booleans and version only, with no-store caching.

Each process shares at most one database probe. Caller wait is 250 ms; a result is
fresh for two seconds. A timed-out caller reports unavailable without cancelling
connection creation. Subsequent callers share the pending probe. Shutdown drains it
before database disposal. This avoids the earlier aiosqlite cancellation leak pattern.
The HTTP wait is bounded; database-driver/connection shutdown duration is not promised
as a strict 250 ms bound. Probes use ordinary read-only SELECT 1 and never initialize,
migrate, repair or manipulate games. Readiness is not admission control.

Local ASGI middleware generates opaque request IDs and counts request latency/status
families by method and matched route template. It stores at most 128 aggregate keys
and 100 recent timing summaries; overflow uses one fixed label. Unknown methods use
OTHER and unmatched routes use a fixed label. WebSocket connections contribute only
aggregate open/active counts. No raw path/query/body/header, match ID, provider prompt,
model response, credential or user-supplied correlation ID is retained. There is no
new telemetry download endpoint, collector, logging sink or external alert delivery.
Operators can inspect `application.state.operations.snapshot()` locally. This is a
process-local summary, not distributed metrics, full tracing or a production SLA.

## Recovery acceptance

Use generated terminal games and new disposable databases in the existing PostgreSQL
17 CI service. Native `pg_dump --format=custom` and `pg_restore --single-transaction`
run inside that service container. The test requires explicit restore opt-in, GitHub
Actions, the loopback lounge_test test URL and the declared service container ID.
It creates fresh UUID-named source/destination databases, closes all application/store
connections, and drops only databases whose creation succeeded in this test. No live
application database is backed up, restored or dropped.

Compare every public table's logical rows before application initialization, then
compare exact game position/result, event accessor output, queue state and stable
public export contents. Upload only a secret-free fixture evidence JSON (counts,
archive size and elapsed time), never the archive or raw rows. SQLite fixtures now
also check event accessor output. This does not establish production PostgreSQL PITR,
cluster roles/tablespaces, encryption, access, retention or RPO/RTO objectives.

## Consequences and remaining acceptance

Readiness can briefly report unavailable during startup, stale ticks or slow database
responses. A worker may be alive but not recently successful; that is intentionally
unready. Long-lived stream duration represents connection time, not time-to-first-byte.
Metrics reset on restart and cannot be summed as durable billing or audit records.

Production tracing/collectors, alert destinations/thresholds, backup storage, retention,
identity/roles and rollout need the existing decisions. Stage 8B remains open until
those deliverables and production acceptance are complete. No schema or protocol
breaking change is introduced; existing health/game/event responses remain compatible.
