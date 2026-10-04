# Stage 8C bounded performance acceptance preparation

Status: **Generated-fixture harness implemented; native CI verification pending.
No capacity, hosted-load or full 8C completion claim.**
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
| Spectators/WebSockets | Step 1 → 10 → 50 → 100 synthetic clients on a deterministic game | Coalesced versioned snapshots plus separately read ordered durable events, exact final revision/FEN, reconnect recovery, active count returning to zero, memory/backpressure behavior |
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

## Implemented discovery checkpoint

Run `PYTHONPATH=services/api python -W error -m lounge_api.performance
--out /tmp/lounge-baseline.json --engine` on Linux. No endpoint or application
DB option exists. SQLite uses fresh UUID files in a disposable directory;
`--postgres-ci` is guarded to the existing loopback CI service and creates/drops
separate UUID databases. The default HTTP schedule is 1/8/32 (four waves each),
WS schedule 1/10/50/100 (four legal moves each), queue schedule 1/4 (eight
four-ply games each). A race of eight claimants checks the shared four-lease cap,
pause/cancel fencing, no duplicate ply and recovered state/report agreement.

The actual ASGI socket protocol may combine revisions. The harness validates
nondecreasing versions, final FEN/moves, durable event continuity and reconnect
state, rather than requiring one socket frame per event. `final_snapshot_wait`
is time spent draining snapshots **after all moves were committed**, not end-to-end
move-to-screen latency. Output queues have capacity four; high-water and active
connections after cleanup are reported. Task groups cancel/drain siblings on failure;
injected validation failure and successful pipelines check no owned tasks remain.
Peak RSS is a cumulative Linux high-water mark, not current memory or leak proof.

Real engine measurements use two separate serialized Stockfish services, each with
one thread, 16 MiB hash and 30 ms searches; four legal player proposals and four
analysis calls run together. Player latency includes serialized queue wait; requested
Elo is not independently calibrated. Missing Stockfish is explicitly skipped. This
checkpoint does **not** verify automatic engine crash/timeout recovery, prove analysis
has no CPU scheduling impact, measure a transport/proxy, establish sustained load,
or classify every database lock/retry. Those acceptance items remain open.

First exploratory local run: Linux x86_64, AMD EPYC 9V74, nine reported CPUs,
cgroup CPU quota eight cores, memory cap 8 GiB, Python 3.12.14/SQLite 3.53.1,
Stockfish 16. All schedules passed correctness. At 100 clients, post-commit final
snapshot drain p95 was 411.8 ms; eight games took 4.505 s at one lease and 1.688 s
at four. These are one-run discovery observations from the initial working harness,
not release targets or current published-commit acceptance. CI records source SHA,
hardware, both databases, workload, limits and skips in its aggregate JSON artifact.

Full 8C remains in progress. Hosted/representative measurements depend on approved
account/security/topology choices. Preserve final CI/browser/restore gates and the
October 6 17:40 UTC target's integration buffer.

Published draft PR26 source 3c84e1f passed CI 37230951795. Artifact 11313727043
contains measured SQLite 3.45.1/PostgreSQL17.11 fixtures on EPYC 7763, four CPUs,
~16GiB reported memory. At 100 spectators post-commit drain p95 was 386.6ms/615.6ms;
eight-game 1/4-lease times were 4.562/1.743s SQLite and 4.572/1.501s PG. Both
backends passed correctness/cleanup. CI explicitly skipped absent Stockfish; local
Stockfish16 is separate evidence. Artifact source SHA is the tested synthetic merge
a4996b5; PR source 3c84e1f is distinct. No production SLA/capacity is inferred.
