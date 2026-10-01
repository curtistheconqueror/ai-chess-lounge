# ADR 0002: Append-only match events as the replay source

- **Status:** Accepted
- **Date:** 2026-09-30
- **Owners:** CurtisTheConqueror

## Context

The product must replay games, audit takeovers and retries, recover interrupted
matches, explain results, and generate reliable experiment bundles. A mutable row
containing only the latest board position cannot explain how that state was reached.

## Decision

Every accepted domain transition emits an immutable event with match ID, ordered
sequence, type, schema version, timestamp, actor, and validated payload. Events cover
moves, clock actions, pauses, resumes, retries, seat takeovers, connection changes,
forfeits, adjudications, and terminal results.

Relational match and move tables are query projections. The ordered event history is
the source for replay and audit. Secrets and private chain-of-thought are excluded.

## Consequences

- Finished games and interrupted matches can be reconstructed.
- Schema evolution and projection rebuilding must be designed explicitly.
- Event payloads require strict redaction and compatibility tests.
- Storage grows monotonically and needs a documented retention policy.

## Alternatives considered

- Mutable match documents: simpler initially but inadequate for audit and replay.
- Store provider transcripts as the event log: rejected because transcripts may be
  sensitive, unstable, and unnecessarily large.

## Verification

A test must rebuild the same state, clocks, result, PGN, and public summaries from the
event sequence after clearing all derived projections.
