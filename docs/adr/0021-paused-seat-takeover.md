# ADR 0021: Paused, revision-fenced seat takeover

Status: accepted for Stage 6B.

## Decision

A local operator can replace either seat only while the match is paused. The command
carries the expected revision and a public PlayerConfiguration; all existing adapter
capability checks still apply. A successful handoff stays paused and increments both
revision and position version, even though FEN is unchanged. Database compare-and-swap
atomically persists the replacement, clears the old turn lease and appends seat.changed.
Old human commands, AI results and remote deliveries cannot cross that boundary.
A late runner trust error may pause only the revision that requested that turn.

Seat history is persisted as a snapshot projection (migration 0008); immutable events
remain authoritative audit records. PGN retains original player headers, adds current
players and seat-change count, and annotates handoffs at their actual ply. Reset clears
the current generation's projection but preserves prior events. Player cards use only
moves made since that seat's latest handoff for strategy and usage attribution.

Remote authorization remains bound to match, generation and color. A previously
paired runner may return to its original seat with its remaining grant, without
resetting expiration or dispatched-turn count. Dispatch and submission also check
that the runner currently occupies that seat. New seats require a distinct pairing.

## Consequences

Human/AI and AI/AI substitutions are explicit exhibition events. No provider protocol
change or additional per-move approval is needed. The UI confirms a revision-bound
replacement and requires an explicit resume; replay, disconnect and stale snapshots
cannot initiate it. Pause/resume accept optional revision guards for compatibility;
the current UI always supplies them. Account ownership and remote invitations remain
final deployment work; these endpoints are local operator controls.
