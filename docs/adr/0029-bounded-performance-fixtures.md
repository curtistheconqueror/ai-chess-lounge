# ADR 0029: bounded generated-fixture performance discovery

Status: proposed implementation checkpoint, not hosted capacity acceptance.

## Decision

Keep a Linux benchmark CLI in the API package, with no arbitrary endpoint or
application database option. Use deterministic adapters and separate generated
SQLite/disposable CI PostgreSQL databases. Retain only aggregate hardware,
versions, latency/counts, workload limits and correctness outcomes. Do not perform
provider calls, introduce grants, or change operational admission policy.

Use the actual ASGI application and socket protocol, including coalesced snapshots.
Read durable events separately. Verify leases/fencing and exports using real stores;
use actual Stockfish when installed and explicitly skip absent engines. Cap each
scenario at 60 seconds and cap schedule length/concurrency. Task-group failures
drain siblings before store disposal; cleanup attempts cover all sockets/services.

## Consequences

In-process measurements isolate application overhead but do not include TCP/TLS,
proxy, browser rendering or deployment topology. Peaks are not memory leak proof.
Engine latency includes serialization and does not isolate service from queue time.
Thread-backed engine teardown and driver shutdown can outlast the scenario timer;
60 seconds bounds scenario work, not a guaranteed whole-process termination SLA.
Engine crash/timeout recovery, sustained/hosted load, database retry classification
and operator latency/resource targets remain explicit follow-up gates.

No schema, live quotas, identity/access, paid infrastructure or security change is
included. See PERFORMANCE_ACCEPTANCE.md for workloads and interpretation.
