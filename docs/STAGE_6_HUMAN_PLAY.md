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
Consultation is described below.

## Stage 6C — human consultation

During a running human turn, select an **Adviser model** and supported effort (or
Stockfish target strength), then **Request suggestion**. The human clock keeps
running. Advice never moves a piece automatically: **Review suggested move** opens
confirmation; **Confirm suggested move** submits your human move. You may cancel
that dialog or ignore the advice and move directly on the board.

The card shows the adviser, suggested SAN move, public plan/threat, latency and any
reported tokens/cost. History and PGN disclose Human-AI Team exhibition assistance,
including requests whose advice was not used. Advice survives reload, while stale
results cannot be played after another action changes the match. **Cancel consultation**
stops a pending request without pausing the match. Provider errors leave you able to play.

API: `POST /api/games/{id}/consultations` accepts `{advisor, expected_revision}` and
returns 202 with a pending snapshot; normal WebSocket snapshots deliver the result.
`POST /api/games/{id}/consultations/{advice_id}/cancel` accepts `{expected_revision}`.
The existing `/moves` endpoint accepts optional `consultation_id` and
`consultation_revision` for explicit use, alongside `move` and `position_version`.
The server rechecks the stored suggestion and current turn before applying it.

Apply migration `0009_consultations` before serving an existing database. Advice is
bounded by the remaining clock and a maximum 30-second request deadline. Graceful
shutdown cancels owned work; abrupt crashes leave no automatic billable retries.
Cancel a leftover pending request or wait until its original deadline to request again.
The snapshot renders expired/superseded pending advice stale; the browser refreshes
at the deadline. Reset clears the current consultation projection, not past audit events.

Available advisers: Stockfish, configured OpenAI/Anthropic/Google/OpenRouter providers,
Ollama/vLLM, and a credential-free deterministic practice adviser. The practice adviser
is a test harness, not a frontier model. Remote runner and subscription seats continue
to play games; adviser use is deferred until separate consultation authorization exists.
Only supported model/effort choices from the existing capability catalog are offered.
No private reasoning or raw provider errors are stored or displayed.

Stage 6C completes this evening's work. Stage 6D account roles/private invitations
remain deferred to the final multiplayer rollout; the next implementation target is
Stage 7A Model Lab experiment configuration when the owner resumes.
