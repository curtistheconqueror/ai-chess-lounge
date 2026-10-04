# Stage 6A — human-seat controls

The local operator can play either human seat. This remains a loopback application;
seat colors are not account identities. Remote ownership and invitations are later work.

## Playing

- Click or tap a piece and a legal target, or drag on desktop. Replay and disconnected
  boards reject input. Reconnect enables input only after a fresh server snapshot.
- Choose queen, rook, bishop or knight on promotion. Both colors display their own
  pieces. Escape cancels; keyboard focus stays inside the picker. Position changes,
  resets and replay close stale promotion choices.
- Each human seat has its own **Resign White/Black** control and confirmation dialog.
  Automated seats cannot resign through this human endpoint. A human can resign on
  either turn. The server rejects stale versions and settles the active clock without
  awarding increment. Expiration wins over a late action.
- **Claim draw** becomes available for threefold repetition or the fifty-move rule.
  If a legal intended move establishes the claim, choose it in the confirmation.
  That move is announced in the event history and is **not played**. The arbiter
  validates the claim, records the reason, stops the clock and persists the draw.
- Clocks continue while dialogs are open. Reload/permalink restores the server game;
  browser display time does not decide results.

## API

`POST /api/games/{id}/resign` accepts `{color, position_version}`. The UI always sends
both. Legacy bodyless clients select the sole human, or the human side to move when
both seats are human; an automated seat is never selected as a human action.

`POST /api/games/{id}/claim-draw` requires `position_version` and optionally
`intended_move` (UCI). Invalid claims return 422; stale versions and clock expiration
return 409. `can_claim_draw`, `draw_claim_moves` and `draw_reason` are additive snapshot
fields. Migration `0007_human_draws` stores the reason separately from adjudication.
Apply `alembic upgrade head` before serving an existing database.

## Scope and verification

Claims do not impose tournament penalty time for an invalid claim. Negotiated draw
offers/acceptance, including agent negotiation, remain unimplemented; the UI explicitly
says **Claim draw**. No draw is inferred from a model's public strategy text.

Tests cover announced repetition without a phantom ply, fifty-move claims, clock
expiration, stored draw recovery, stale requests, Black resignation, automated-seat
rejection, and migration upgrade/downgrade. Browser acceptance covers desktop/phone
move entry, both-color underpromotion, keyboard cancel, confirmations and reload.
The server remains authoritative for legality, time and terminal results.

The same phase fixes repeated WebSocket cancellation interrupting database cleanup.
A regression test holds an actual SQLAlchemy session through two cancellations and
asserts both child tasks finish and the pool has zero checked-out connections.
A second regression disconnects a real ASGI TestClient during an in-flight SQLite
driver query. Short runner database calls are shielded against AnyIO level cancellation;
model thinking and turn waits stay cancellable. CI treats Python warnings as errors.

Next: **Stage 6B**, explicit pause-safe human/AI seat takeover with immutable events
and stale agent-result fencing. Consultation follows in 6C; authenticated remote
ownership and invitations remain a final deployment-stage concern.
