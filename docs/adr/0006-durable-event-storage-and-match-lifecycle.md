# ADR 0006: Durable event storage and match lifecycle

- **Status:** Accepted
- **Date:** 2026-10-01
- **Owners:** CurtisTheConqueror

## Context

The Stage 1 process kept complete games in memory. A restart erased every match,
and an in-process lock could not prevent two API processes from writing different
moves from the same position. Reset also discarded the only copy of prior moves.

## Decision

PostgreSQL is the production system of record, accessed through async SQLAlchemy.
SQLite implements the same repository contract for tests and zero-setup native
development. Alembic owns production schema history.

The database stores a current `matches` projection, immutable `moves`, and an
append-only `match_events` stream. Events are unique and ordered per match. Reset
advances a generation instead of deleting historical moves or events.

Every durable mutation increments a match `revision`. Updates compare the expected
revision in the database transaction before inserting their move/event records. A
failed comparison reloads authoritative state and rejects the stale writer. Board
`position_version` remains a separate client-facing legality guard.

Match lifecycle is explicit: created, waiting, running, paused, completed, aborted,
or adjudicated. Domain rules, not route handlers, validate transitions.

## Consequences

- Games and replay data survive API restarts.
- Multiple API processes cannot silently overwrite the same match revision.
- Current reads remain efficient while the event stream preserves audit history.
- Reset no longer destroys evidence from the prior board generation.
- Schema changes require migrations and compatibility tests.
- PostgreSQL remains required for production-like deployment even though SQLite is
  intentionally supported for contributors and tests.

## Alternatives considered

- Serialize in-memory games to JSON: rejected because transactions, concurrency,
  indexing, and schema evolution would remain fragile.
- Store only events and rebuild every read: deferred because projections make live
  board reads inexpensive while events still preserve replay history.
- Use Redis as the primary store: rejected because Redis is better reserved for
  leases, queues, and transient fan-out than the durable match record.

## Verification

Tests restart a manager against the same database, compare restored FEN/PGN/moves,
verify reset event history, exercise every lifecycle boundary, and demonstrate that
the second of two stale writers is rejected and refreshed.
