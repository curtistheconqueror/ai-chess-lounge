# ADR 0009: Isolated spectator analysis

- **Status:** Accepted
- **Date:** 2026-10-01
- **Owners:** CurtisTheConqueror

## Context

The Lounge broadcast needs evaluation, a principal variation, and move-quality cues.
The playing Stockfish process may be deliberately strength-limited, while model and
human seats must remain the only sources of their submitted moves. Reusing an analysis
answer as a move would silently cross assistance divisions.

## Decision

Spectator analysis runs through a separate full-strength Stockfish service. The API
reconstructs committed positions from authoritative move history and returns a
versioned, White-perspective analysis snapshot. Results are cached by match,
generation, and position version and are invalidated by the next analyzed version. The
service rechecks the durable position marker before publishing a result; the client
also rejects analysis that does not exactly match the displayed generation and version.

Analysis output is never written as a match move or event and is never passed to the
playing engine or future provider adapters. The web client labels the PV as spectator
analysis and discloses that analysis is available in the human exhibition division.

The public engine summary omits local executable paths. Share exports include only the
public match snapshot and analysis contract.

## Consequences

- Playing strength and spectator depth can differ without contaminating the match.
- Analysis can be temporarily unavailable without stopping clocks or match play.
- Long games require repeated engine work; the current per-version cache is sufficient
  for the vertical slice, while a background analysis queue is deferred until measured
  spectator load justifies it.
- Move classifications are approximate centipawn-loss bands and must not be presented
  as provider reasoning or definitive coaching judgments.

## Verification

Tests cover analysis legality, PV production, version alignment, concurrent move
suppression, caching, move classification, and removal of server paths from public
snapshots. Browser smoke tests exercise the analysis surface independently from move
entry.
