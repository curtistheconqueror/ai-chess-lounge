# ADR 0040: Display-only move preview and premoves

- Status: Accepted
- Date: 2026-10-10

## Context

The owner's target is chess.com-level board feel. Two things broke it:

- **Own moves waited for the server.** A human move appeared only after the HTTP
  round trip and server arbitration (50-200 ms+ over the private Tailscale link), and
  the board was disabled meanwhile.
- **No premoves.** Against Stockfish or a fast agent, the reply lands before a human
  can act, and the board is locked on the opponent's turn.

AGENTS.md requires that the server is the sole authority and that the web app does
not infer authoritative match state.

## Decision

**Preview (shipped).** On submit, the client renders a display-only preview of the
move, built from the current FEN placement (normal moves, castling, en passant,
promotion). It also plays the move sound immediately. The preview is pinned to
`{game id, generation, version}`, so any newer snapshot replaces it automatically.
A rejected request discards it, the board shows the server position again, and the
error is surfaced. The preview never enters `gameRef`, history, clocks, legality or
any request. The confirming snapshot is silent, so each move makes exactly one sound.

**Board motion keys on placement, not the full FEN.** A confirmation that only
refines FEN metadata must not interrupt a translation in progress.

**Premoves (next).** A premove is a client-held intent, never sent early. It's shown
on the board and cancellable. When a snapshot gives the player the move, the client
submits it through the normal path only if it's in that snapshot's `legal_moves`;
otherwise it's dropped silently. The server still validates the move as usual.

## Consequences

- A brief visual mismatch is possible on rejection. It reverts within one round trip.
- No API, protocol or persistence change.
- Tests cover the delayed confirmation, rejection rollback, and en passant preview
  parity with the confirmed position.
