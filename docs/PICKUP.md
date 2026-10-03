# AI Chess Lounge contributor pickup

Updated: 2026-10-03. Read AGENTS.md, README.md, MASTER_PLAN.md and ADR 0019.

## Verified baseline

Stage 5D merged as PR #13 at `12255ba8209162af8f78f2124f9d7a1ae23b81d7`.
`pickup/stage-5d-complete` remains at that exact merge. Keep
`feat/stage-5d-subscription-bridge` and all earlier pickup branches.
Postmerge CI 37071772590 passed. The real Codex subscription acceptance game is
recorded in `docs/verification/stage5d-live.md` and `.pgn`.

## Last completed phase — Stage 5E

PR #14: https://github.com/curtistheconqueror/ai-chess-lounge/pull/14
Verified merge/base: `59e9a7a360b55d251871a9f168bab62e277874e2`.
Immutable checkpoint: `pickup/stage-5e-complete` at that exact merge.
Retained contributor: `feat/stage-5e-trust-controls`.
Final published source: `0bd9ed651b537f05ee023eda713647027b01d8cd`.
The source and merge trees both exactly match the locally tested implementation.

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

## Verification

- Local `make test`: 197 Python passed, 2 PostgreSQL-environment skips; Ruff
  formatting/lint, 3 TypeScript SDK tests and web typecheck passed. `make build` passed.
- PR CI run `37152054950`, job `111287778098`: success on the exact published head.
- Postmerge CI run `37152192013`, job `111288180482`: completed successfully on the
  exact merge above. Both runs verified SQLite/PostgreSQL upgrade/downgrade, 197
  Python tests (2 missing-Stockfish skips), 3 SDK tests, production build, and 15
  browser tests (40 intentional viewport-duplicate skips).
- Local browser execution could not start because the required Chromium binary was
  absent; GitHub CI supplies the complete five-viewport browser gate.
- Independent review identified reset/pause-resume dispatch races. The fixes and
  cross-worker regression tests are included.

## Current work and exact next target

Stage 5E is merged and its checkpoint is preserved. No code work is in progress.

1. Before Stage 6A, investigate a non-failing aiosqlite/SQLAlchemy connection-cleanup
   warning observed in both CI runs (reported during the missing/invalid bearer API
   test). Do not claim it is fixed: a focused local API suite with SAWarning treated
   as an error passed all 15 tests, but did not reproduce the CI suite-order issue.
   Inspect WebSocket polling cancellation/connection lifetime under the full suite.
2. Start a dedicated contributor from the verified main merge, preserving all prior
   contributor and immutable pickup branches.
3. Stage 6A: human-seat polish and acceptance (promotion, resign/draw, reconnect and
   clocks), then Stage 6B explicit AI/human seat takeover. Human play already exists;
   build on it. Multiuser accounts/remote invitations stay at the final deployment stage.
4. Finish each phase with its own PR, CI/merge verification, immutable pickup, and
   retained contributor handoff.

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
