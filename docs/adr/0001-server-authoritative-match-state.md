# ADR 0001: Server-authoritative match state

- **Status:** Accepted
- **Date:** 2026-09-30
- **Owners:** CurtisTheConqueror

## Context

Humans, hosted models, local models, remote runners, MCP clients, and Stockfish can
all submit moves over transports with different latency and failure behavior. Letting
any client mutate board state would permit illegal positions, duplicate moves, clock
disagreement, and unreliable replays.

## Decision

The Python API owns the authoritative game aggregate. `python-chess` validates every
move and derives FEN, PGN, turn, check state, and terminal results. Clients and player
adapters submit proposals tied to a position version. The server applies at most one
valid proposal for that version in a transaction and advances the version.

Server time determines clocks and deadlines. Browser state is a projection and can
always be rebuilt from a snapshot plus ordered events.

## Consequences

- The same integrity rules govern human, engine, and model seats.
- Reconnect and replay behavior is deterministic.
- Offline or optimistic UI moves remain provisional until server acceptance.
- The API and persistence layer require careful concurrency and clock tests.

## Alternatives considered

- Client-authoritative state: rejected because participants are untrusted and can
  disagree.
- Provider-specific match loops: rejected because they fragment legality and recovery
  behavior.

## Verification

Contract and concurrency tests must prove that illegal, duplicate, stale, and
simultaneous proposals cannot corrupt a position or produce two accepted moves.
