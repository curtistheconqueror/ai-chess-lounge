# Stage 6 — human play and takeover

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

Authenticated remote ownership and invitations remain a final deployment-stage concern.

## Stage 6B — mid-game takeover

1. Select **Pause match**. The server settles the active clock and cancels local thinking.
2. Choose the replacement in the White/Black seat selectors, then **Apply White/Black seat**.
3. Review and confirm the player, provider, effort and assistance division. The board,
   move history and remaining clocks carry over. The match stays paused.
4. **Resume match** starts the next turn. **Restore previous white/black player** offers
   the most recent controller with its saved configuration, including an eligible runner.

The seat-history panel and exported PGN disclose every substitution. Reload preserves
these records and the paused state. Public strategy/usage cards stop displaying the
previous controller's last move after a switch. These are exhibition games.

`POST /api/games/{id}/seats/{white|black}` requires `{expected_revision, player}`.
Stale requests, an unchanged player, wrong-color configuration or a running match
return 409; invalid/unavailable adapter configurations return 422. Snapshot
`seat_history` is additive. Pause/resume now accept `{expected_revision}`; legacy
bodyless requests remain supported. Apply migration `0008_seat_history` before serving.

A remote runner can return only to its original authorized match, generation and
color while its grant remains valid and has dispatch budget. Taking it out of the
seat blocks new dispatch and proposal submission. Returning it does not renew its
expiry or budget; a fresh pairing is needed for a different seat/match or reset.

Regression coverage includes revision races, late old proposals and trust errors,
clock/history recovery, PGN round-trip, runner-grant preservation, schema rollback,
and desktop/phone takeover, cancellation, restoration and stale-dialog dismissal.
Next: Stage 6C, human consultation with a human making the final move.
