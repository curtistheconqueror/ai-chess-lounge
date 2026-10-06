# ADR 0032: generated loopback transport discovery

Status: candidate; published native/browser CI acceptance pending.

## Decision

Complement in-process ASGI measurements with an opt-in `--loopback` scenario. Bind
one ephemeral socket to 127.0.0.1 only; accept no caller-provided host, endpoint or
application database. Own the app lifespan explicitly and disable Uvicorn's separate
lifespan task and process signal handlers. Generate isolated SQLite or guarded CI
PostgreSQL stores with scripted-only adapters. No grants or provider calls are used.

Keep the same 32-HTTP/100-spectator/four-schedule-level and 60-second scenario caps.
Use actual HTTP moves with idempotent replays, coalesced WebSocket snapshots, exact
final revision/FEN/moves, ordered durable event counts and reconnect recovery.
Client receive queue high-watermark is four frames and message size is 1 MiB;
clients send no application messages over the socket. This is not an inbound-flood
or hard-memory-cap test. The locked Uvicorn SansIO backend does not use the legacy
`ws_max_queue` setting, so the fixture does not claim that server queue guarantee.

Close all client connections, stop/drain the owned server task, close the listening
socket, then close app readiness/worker/stores in nested cleanup. Injected snapshot
validation failure verifies cleanup. Exceeding graceful-stop wait triggers owned
server cancellation; teardown can exceed the scenario timer and is not an OS-level
hard-kill guarantee. Source metadata records checked-out SHA plus clean/dirty state;
GitHub Actions tests a synthetic merge SHA, distinct from the PR source head.

## Measurement interpretation

HTTP readiness samples use a warmed readiness cache. The socket interval starts
before the final move request and ends at the fixture's final snapshot read; it
includes the accepted HTTP request, idempotent replay and snapshot draining. It is
not isolated propagation time, browser-render latency or a representative hosted
SLA. TLS/proxy/multi-host topology, sustained load, engine-pool supervision and
operator release targets remain separate acceptance gates.
