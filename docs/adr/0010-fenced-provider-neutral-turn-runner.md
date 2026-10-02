# ADR 0010: Fenced provider-neutral turn runner

- **Status:** Accepted
- **Date:** 2026-10-01
- **Owners:** CurtisTheConqueror

## Context

The Stage 1 loop assumed White was human and Black was Stockfish. Hosted models,
local models, engines, remote agents, and subscription bridges need to occupy either
color without adding provider branches to the chess domain. Model calls may also last
longer than a database lease or race pause, timeout, reset, or another worker.

## Decision

Persist one versioned `PlayerConfiguration` for each color. The match runner resolves
only the current persisted seat, builds an immutable protocol-v1 `MoveRequest`, and
dispatches through an `AdapterRegistry`. An adapter returns a bound `MoveProposal`;
the server alone validates and commits it.

Every automated turn uses the existing durable position-fenced lease. Adapter work
runs without an open database transaction. The runner renews the lease during long
calls, caps the call by the authoritative remaining clock, and validates request ID,
match ID, position version, UCI legality, lease, and durable revision before commit.
Pause and other local control actions cancel the in-flight task; cross-process late
work fails the same durable fence.

Only allowlisted public metadata is stored. Raw responses, prompts, private reasoning,
credentials, and subscription sessions are excluded.

## Consequences

- Both colors can be automated through one orchestration path.
- Stockfish and deterministic tests exercise the same contract future providers use.
- Old matches remain readable through nullable seat metadata and legacy fallback.
- Provider-specific retries and error taxonomies remain Stage 3F work.
- The in-process task runner is sufficient for one-host proof; a durable queue becomes
  necessary when horizontally scaled match workers are introduced.

## Verification

Contract tests cover identity/version binding and invalid proposals. Integration tests
complete an unattended two-agent checkmate, reload public metadata, reject human input
on automated seats, and cancel an in-flight call on pause. Migration checks exercise
upgrade and downgrade around the previous concurrency schema.
