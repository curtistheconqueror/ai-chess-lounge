# Stage 2 — Durable Match Platform

## Current outcome

Sub-phases 2A through 2D turn the Stage 1 prototype into a restart-safe, timed match
service without adding any model-provider credential dependency.

| Sub-phase | Delivered |
| --- | --- |
| 2A Persistence | PostgreSQL Compose service, async SQLAlchemy repository, Alembic migration, durable matches and moves, and immutable ordered events |
| 2B State machine | Created, waiting, running, paused, completed, aborted, and adjudicated lifecycle states with validated transitions |
| 2C Clocks | Server-authoritative Fischer controls, durable turn anchors and deadlines, pause/resume semantics, and timeout results |
| 2D Concurrency | Idempotent move retries, expiring fenced turn leases, stale-read refresh, crash rollback coverage, and PostgreSQL CI |

## Storage model

- `matches` is the current projection used for fast reads and optimistic writes.
- `moves` records every accepted move. A reset advances `generation` instead of
  deleting older records.
- `match_events` is append-only, ordered by `(match_id, sequence)`, and records
  creation, start, accepted moves, lifecycle changes, completion, and reset.
- `position_version` changes when the board/result changes. `revision` changes on
  every durable mutation, including pause and resume, so concurrent server
  processes cannot silently overwrite one another.

## Authoritative clocks

- A match stores its initial time, Fischer increment, both remaining balances, and
  the UTC start of the active turn.
- Every accepted move charges elapsed server time and then adds the mover's
  increment. Move records retain the resulting balances.
- Pause charges the current turn without adding increment and freezes both clocks;
  resume creates a fresh server-time anchor.
- A deadline scheduler handles flag fall during a live process. Startup recovery and
  authoritative reads also adjudicate deadlines that elapsed while the service was
  offline.
- Timeout is a terminal match result with a persisted losing color and ordered
  `clock.timeout` and `match.completed` events.
- Browser clocks are animated projections anchored when a server snapshot arrives,
  avoiding client/server wall-clock skew. Clients cannot award time or decide the
  result.

## Concurrency and recovery

- Move clients may send `Idempotency-Key`. The key and request hash commit atomically
  with the accepted move and events, so a lost-response retry cannot apply twice.
- Reusing a key for different input is rejected instead of guessing client intent.
- One database-backed turn lease coordinates expensive engine or future agent work.
  The lease is fenced by position version, expires after a bounded interval, and is
  cleared by any accepted mutation.
- Stockfish acquires the same lease contract future model adapters will use; another
  process can reclaim the turn after a crashed worker's lease expires.
- Mutations are prepared on detached match candidates and published to process memory
  only after the database transaction commits, so a rollback cannot poison the cache.
- Transient Stockfish or database failures release through the lease boundary and
  retry the still-pending engine turn with capped exponential backoff.
- Authoritative reads refresh from the database so one API process cannot indefinitely
  serve a position cached before another process committed.
- WebSockets watch the durable revision instead of relying only on process-local
  listeners, so a spectator connected to another API process still receives the move.
- PostgreSQL CI covers migrations, concurrent retries, and competing lease claims.

The API remains the only board authority. Database rows are never accepted as move
proposals; restored games are reconstructed by replaying persisted UCI moves and
checking every resulting FEN against the stored projection.

## Run

Docker is the production-like local path:

```bash
docker compose up --build
```

Compose starts PostgreSQL, waits for its health check, runs `alembic upgrade head`,
and starts the Lounge at <http://localhost:8000>.

Native development remains zero setup:

```bash
make setup
make dev
```

Without `DATABASE_URL`, native development uses the ignored
`.runtime/lounge.db` SQLite database. Set a PostgreSQL async URL to use PostgreSQL
outside Compose.

## Lifecycle API

| Action | Endpoint |
| --- | --- |
| Read ordered events | `GET /api/games/{game_id}/events` |
| Pause | `POST /api/games/{game_id}/pause` |
| Resume | `POST /api/games/{game_id}/resume` |
| Abort | `POST /api/games/{game_id}/abort` |
| Adjudicate | `POST /api/games/{game_id}/adjudicate` with `result` |

Existing create, move, reset, resign, fetch, and WebSocket routes remain compatible.
Snapshots now disclose lifecycle, durable revision, reset generation, ordered event
sequence, timestamps, and a clock projection containing balances, time-control
settings, active-turn anchor, deadline, server time, and timeout color.

`POST /api/games/{game_id}/moves` accepts an optional `Idempotency-Key` header using
8–128 URL-safe identifier characters. New clients send it on every move and retain the
same key when retrying that exact request.

## Verification

```bash
make test
make build
make migrate
```

The test suite covers restart restoration, event ordering, reset history, lifecycle
rules, deterministic clock math, pause/resume, exact-deadline flag fall, background
timeout scheduling, WebSocket snapshots, Stockfish responses, idempotent retries,
lease fencing and expiry, crash rollback, stale cross-instance reads, and PostgreSQL
multi-connection races. The crash test also retries in the same process to prove the
rolled-back candidate never escaped into the live cache.

## Remaining Stage 2 work

- 2E minimal accounts, match visibility, and owner permissions
