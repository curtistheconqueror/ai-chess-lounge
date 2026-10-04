# ADR 0020: Versioned human terminal actions

Status: accepted for Stage 6A.

## Context

The existing bodyless resignation endpoint always chose White. Human Black could
therefore award the win to the wrong side. Promotion choices could outlive their
position, and claimable draws were not exposed to human players.

## Decision

Human UI terminal actions carry color (resign) and position version. The manager
checks seat kind and stale versions, the domain arbiter checks claim legality and
deadlines, and the existing database revision CAS serializes the final event/state
write. Resignation can interrupt the opposing agent only after preflight validation;
a raced rejection reschedules eligible automation. A claim belongs to the human side
to move and never executes its announced intended move. Claimed draws have a dedicated
persisted reason and completed lifecycle, distinct from operator adjudication.

The UI confirms terminal actions, clears stale dialogs on authoritative changes,
fences drag data with match/version/revision, and waits for a reconnect snapshot
before accepting input. Clocks continue during confirmation and promotion.

## Consequences

No provider or runner protocol change is required. Snapshot fields are additive;
legacy bodyless resignation infers the available human seat. Draw negotiation is not
part of this claim endpoint. This is local operator control, not identity-based seat
authorization. Migration 0007 adds a nullable draw-reason column to matches.
