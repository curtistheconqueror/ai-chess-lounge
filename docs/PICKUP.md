# AI Chess Lounge contributor pickup

Updated: 2026-10-03. Read AGENTS.md, README.md, MASTER_PLAN.md and ADR 0019.

## Verified baseline

Stage 5D merged as PR #13 at `12255ba8209162af8f78f2124f9d7a1ae23b81d7`.
`pickup/stage-5d-complete` remains at that exact merge. Keep
`feat/stage-5d-subscription-bridge` and all earlier pickup branches.
Postmerge CI 37071772590 passed. The real Codex subscription acceptance game is
recorded in `docs/verification/stage5d-live.md` and `.pgn`.

## Current work — Stage 5E implementation ready for CI

Contributor: `feat/stage-5e-trust-controls`, based on the verified Stage 5D merge.
No completed 5E pickup branch exists until merge and postmerge verification.

Implemented:
- Durable first-match, seat, reset-generation, expiry and turn-request grants.
- Session-row serialization of binding, revocation and final move commits.
- Credential-free append-only claim/authorization/dispatch/commit/revoke audit.
- HTTP/socket reconnects preserve delivery identity/deadline; internal lifecycle
  revision prevents old turns reviving after pause/resume.
- UI authorization bounds, bound-seat filtering, and revoke access control.
- Migration 0006, race/lifecycle/expiry/restart regression tests, browser revoke test.
- Clock-awareness experiment captured in MASTER_PLAN: fixed vs adaptive effort,
  clock snapshots, separate viewing delays, and measured behavior versus public claims.

Verification: local make test and make build passed, including the migration
upgrade/downgrade regression. The optional PostgreSQL tests require CI. Browser
acceptance is pending the five-viewport GitHub CI gate. Independent review identified
reset/pause-resume dispatch fencing; both are now covered by regression tests.

## Exact next actions

1. Publish this contributor, open a PR, verify the full CI gate on the exact head.
2. Merge only when green; verify postmerge CI and tree equality.
3. Create immutable `pickup/stage-5e-complete` at the verified merge and update this
   retained contributor handoff with final merge/CI evidence.
4. Next implementation: Stage 6A human-seat polish and acceptance (promotion,
   resign/draw, reconnect and clocks), then Stage 6B explicit seat takeover.
   Keep multiuser accounts/remote invitations for the final deployment stage.

## Known boundaries

Loopback-only: pairing, audit and revoke are operator actions, not account-level
multiuser authorization. No provider credentials enter the runner protocol.
Transport deliveries/receipts remain process-local; restart reconstructs a new
leased request while retaining grants/counts. Distributed routing is deferred.
First dispatch binds the session. Concurrent new games with the same pairing can
both be created, but only one can receive runner moves; the other pauses. Pair
separately for each game. A dispatch already in flight may arrive after revoke;
revocation fences commits, not already-sent network bytes. Reset needs a new pairing.
Request timeout pauses; chess-clock expiration uses arbiter timeout rules. Grant
expiry does not automatically forfeit a game or replenish on pause/heartbeat.
