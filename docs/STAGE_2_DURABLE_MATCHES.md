# Stage 2 — Durable Match Platform

## Current outcome

Sub-phases 2A through 2C turn the Stage 1 prototype into a restart-safe, timed match
service without adding any model-provider credential dependency.

| Sub-phase | Delivered |
| --- | --- |
| 2A Persistence | PostgreSQL Compose service, async SQLAlchemy repository, Alembic migration, durable matches and moves, and immutable ordered events |
| 2B State machine | Created, waiting, running, paused, completed, aborted, and adjudicated lifecycle states with validated transitions |
| 2C Clocks | Server-authoritative Fischer controls, durable turn anchors and deadlines, pause/resume semantics, and timeout results |
| 2D foundation | Durable match revision compare-and-swap, stale-writer rejection, current-generation resets, and startup recovery |

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
- Browser clocks are animated projections of server snapshots. Clients cannot award
  time or decide the result.

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

## Verification

```bash
make test
make build
make migrate
```

The test suite covers restart restoration, event ordering, reset history, lifecycle
rules, deterministic clock math, pause/resume, exact-deadline flag fall, background
timeout scheduling, WebSocket snapshots, Stockfish responses, and a two-manager race
against one database.

## Remaining Stage 2 work

- Complete 2D idempotency keys, turn leases, process-crash injection, and PostgreSQL
  integration coverage
- 2E minimal accounts, match visibility, and owner permissions
