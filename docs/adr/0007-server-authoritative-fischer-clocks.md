# ADR 0007: Server-authoritative Fischer clocks

- **Status:** Accepted
- **Date:** 2026-10-01
- **Owners:** CurtisTheConqueror

## Context

Human browsers, Stockfish processes, hosted models, and remote runners observe time
through machines with different clocks and network delays. A client-controlled clock
could be paused, reset, or reported inconsistently, and a process restart could erase
the active deadline. The Lounge needs one result even when multiple API processes
notice the same flag fall.

## Decision

The API owns each match clock. A time control stores an initial duration and Fischer
increment in milliseconds. The durable match projection stores both remaining times
and the UTC timestamp at which the active turn began. A deadline is derived from that
anchor and the side-to-move balance.

An accepted move first charges elapsed server time, then adds the mover's increment
and anchors the opponent's clock. Pausing charges elapsed time without adding an
increment and removes the deadline; resuming creates a new anchor. A balance of zero
at the deadline is an explicit timeout result, recorded through `clock.timeout` and
`match.completed` events in the same compare-and-swap write.

The browser receives remaining times, the turn anchor, deadline, and server snapshot
time. It anchors animation to the local receipt time instead of assuming the browser
and server wall clocks agree, but only a server snapshot or event can declare a
timeout. On startup the API restores active anchors, schedules future
deadlines, and adjudicates an already elapsed deadline on the next authoritative read.

## Consequences

- Clock and result behavior survives restarts and reconnects.
- Network clients cannot grant themselves time or decide that an opponent flagged.
- Competing timeout workers converge through the existing durable revision guard.
- Wall-clock adjustments remain an operational concern until a dedicated clock
  service or monotonic-plus-wall-clock strategy is introduced for distributed hosts.
- Every clock mutation and move must be tested with an injectable deterministic time
  source.

## Alternatives considered

- Browser-authoritative countdowns: rejected because clients are untrusted and drift.
- Persist the deadline only: rejected because pause/resume and increment accounting
  are clearer when remaining balances and the active-turn anchor are canonical.
- Run timers only in memory: rejected because restarts would lose flag-fall behavior.

## Verification

Domain tests cover elapsed-time charging, Fischer increments, exact-deadline flag
fall, and pause/resume. Repository and manager tests cover move balances, restart
recovery, elapsed deadlines, background scheduling, ordered timeout events, and
compare-and-swap behavior. API and UI checks cover custom controls and live clock
projections.
