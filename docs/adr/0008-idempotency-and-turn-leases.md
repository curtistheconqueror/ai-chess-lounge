# ADR 0008: Idempotent commands and fenced turn leases

- **Status:** Accepted
- **Date:** 2026-10-01
- **Owners:** CurtisTheConqueror

## Context

Remote players and browsers must be able to retry after a lost response without
submitting the same move twice. Multiple API or runner processes can also observe the
same turn and begin expensive engine or model work concurrently. Process-local locks
cannot coordinate those workers, and holding a database transaction open during
inference would create long-lived locks and fragile recovery.

## Decision

Move commands may carry an `Idempotency-Key`. The key, canonical request hash, applied
revision, and timestamp are committed in the same transaction as the match projection,
move, and events. Reusing the same key and payload returns current authoritative state
without applying another move. Reusing the key for different input is rejected.

The match row also holds one expiring turn lease containing an owner, opaque token,
position version, acquisition time, and deadline. Lease claims use one conditional
database update, can be renewed without holding a transaction across inference, and
are reclaimable after expiry. A leased proposal commit must present the current token
and position fence. Any accepted match mutation clears the lease.

Match mutations are built on detached in-memory candidates and replace the live cache
only after commit. Recoverable engine and database failures keep the authoritative
position pending and schedule a capped exponential retry rather than stranding the
turn.

Leases coordinate work; they do not grant match authorization and never contain a
provider credential. Position version, durable revision compare-and-swap, and the
server clock remain the final integrity checks.

## Consequences

- Network retries have at-most-once move effects across process restarts.
- Two workers do not intentionally compute the same Stockfish turn.
- A crashed worker releases the turn through lease expiry without manual cleanup.
- A rolled-back transaction cannot leave one process serving an uncommitted position.
- Transient Stockfish failures retry without asking the player to resubmit the move.
- Future model and remote runners can renew a lease during long work and submit with
  the same fencing contract.
- Authoritative HTTP reads and Stage 2 WebSockets refresh against the durable
  revision, so they observe another process's commits. Redis fan-out should replace
  socket polling when spectator scale makes it necessary.

## Alternatives considered

- Position version alone: prevents a second commit but turns a successful retry into
  an ambiguous conflict after the first response is lost.
- Database transaction held through inference: rejected because model calls may take
  seconds or fail, leaving scarce connections and locks occupied.
- Redis-only leases: deferred until Redis is introduced; the durable database already
  provides the atomic conditional update required by Stage 2.

## Verification

Tests cover same-key replay, conflicting reuse, process handoff, exclusive lease
claims, expiry/reclaim, fencing after a move, cross-instance snapshot refresh, and an
injected failure after transaction flush. CI also runs migration and concurrency
coverage against PostgreSQL in addition to the SQLite contributor path.
