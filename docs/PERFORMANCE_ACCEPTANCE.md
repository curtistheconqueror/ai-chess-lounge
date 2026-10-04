# Stage 8C bounded performance acceptance preparation

Status: **Plan only. No capacity, hosted-load or full 8C completion claim.**
The 8B regression exercises 32 concurrent readiness requests and validates bounded
telemetry/shared-probe correctness. It is not a representative production load test.

## Fixture and safety contract

Use a new temporary database and synthetic games. Bind any test HTTP server to
loopback. Use deterministic scripted adapters, with live provider calls, subscription
bridges and outbound webhooks disabled. Engine tests use declared installed Stockfish
and configured UCI limits; a fake engine can validate harness logic but does not count
as engine performance evidence. No remote runners with active grants are introduced.
Never load the configured application database or restore a backup containing real
credentials. Native PostgreSQL load uses the explicit disposable test service, with
UUID fixture resources and guarded cleanup, as in ADR0028.

Initial harness bounds: at most 60 seconds per scenario, 100 synthetic spectator
connections, 32 concurrent HTTP requests and four queued worker leases globally.
These are harness caps, not supported production limits. Start below the caps, stop
on correctness failures or resource exhaustion, and release all connections/tasks.
Do not run a stress test on a production environment. Deployment-specific load and
provider spending still require their approved environment/budget.

## Scenarios and required evidence

| Scenario | Bounded workload | Correctness and resource checks |
| --- | --- | --- |
| HTTP/readiness | Step 1 → 8 → 32 concurrent requests on known fixture routes | Status distribution, p50/p95/max response latency; shared probe count; capped summary keys/ring; no match mutation or leaked inputs |
| Spectators/WebSockets | Step 1 → 10 → 50 → 100 synthetic clients on a deterministic game | Snapshot then ordered events, exact final revision/FEN, reconnect recovery, active count returning to zero, memory/backpressure behavior |
| Engine | Small declared UCI workload with separate match and spectator-analysis paths | Actual engine/version, configured limits, queue wait/service time, timeout/crash recovery, analysis does not delay/change player moves |
| Tournament queue | Generated color-swapped plan, concurrency 1 then 4 | Shared lease cap, stable game IDs, exact job count, no duplicate accepted ply, pause/cancel fencing and restart recovery |
| Database | Same generated workload against SQLite and disposable PostgreSQL | Read/write latency, lock/conflict/retry categories, event continuity, connection cleanup, exact persisted state/export agreement |

Record the exact commit, UTC timestamp, CPU/RAM/OS, Python/Node/database/Stockfish
versions, database mode, worker count, fixture size, scenario duration, concurrency,
sample count and load-generation method. Report failures and skipped scenarios.
Use public aggregate counts/timings only; exclude database URLs, credentials, raw
prompts, request bodies, user labels and real match IDs from retained evidence.
Capture pre/post resource measurements and verify cleanup even on failure.

## Acceptance and interpretation

Never infer network or multi-host capacity from an in-process ASGI test. In-process
results isolate application/DB overhead; loopback results add local transport; hosted
results require the chosen hardware, TLS/proxy, worker topology and identity controls.
Treat the first runs as baseline discovery. Owner/operator must select the release
latency/resource targets after representative measurements; no invented SLA or
provider-cost threshold is implied here.

A scenario fails correctness on missing/reordered state, duplicate accepted moves,
clock extension, assistance-division leakage, unbounded retained data or orphaned
resources. If performance degrades, identify the bottleneck and rerun only the affected
scenario plus its correctness gate. Do not optimize by bypassing arbiter validation,
lease fencing, provider retry/billing uncertainty or privacy boundaries.

The 8C checkpoint needs measured results across all five scenario areas and explicit
limits. Full beta acceptance additionally needs the chosen deployment/topology and
account/security controls. A single readiness benchmark cannot close 8C. Preserve
CI, restore and desktop/phone visual gates and the final integration buffer in
DELIVERY_48H_PLAN.md.
