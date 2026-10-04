# AI Chess Lounge contributor pickup

Updated: 2026-10-04. Read AGENTS.md, README.md, MASTER_PLAN.md and ADR 0020.

## Last completed phase — Stage 6A

PR #15: https://github.com/curtistheconqueror/ai-chess-lounge/pull/15
Verified merge/base: `ac22b7b5fa7faa5ac6041b1c4a6ca7302597d5c8`.
Immutable checkpoint: `pickup/stage-6a-complete` at that exact merge.
Retained contributor: `feat/stage-6a-human-controls`.
Final published source: `688275462a5ab03a93cbc4ca780c1b9656cb87a9`.
The source and merge trees exactly match the locally tested implementation.

Prior Stage 5E: PR #14, `59e9a7a360b55d251871a9f168bab62e277874e2`.
Keep `pickup/stage-5e-complete`, `feat/stage-5e-trust-controls` and all earlier
contributor/checkpoint branches. Never repoint immutable pickup branches.

Implemented:
- Explicit human-color resignation, confirmation, stale-version rejection and clock settlement.
- Durable threefold/fifty-move claims, including announced intended moves without a phantom ply.
- Desktop drag, phone tap, both-color promotion, stale dialog/drag fencing and reconnect input guard.
- Migration 0007, domain/API/store tests, desktop/phone browser acceptance.
- Runner cleanup handles repeated native cancellation and AnyIO level cancellation.
  Short database operations finish cleanup; turn waiting and model thinking remain cancellable.
- CI treats Python warnings as errors.
- ADR 0020 and STAGE_6_HUMAN_PLAY.md describe API behavior and boundaries.

## Verification

- Local `make test`: 207 Python passed, 2 PostgreSQL-environment skips; Ruff format/lint,
  3 TypeScript SDK tests and web typecheck passed. `make build` passed.
- Full local pytest with warnings treated as errors: 207 passed, 2 skipped.
- Final PR CI `37176580915`, job `111360326145`: success on the published source above.
- Postmerge CI `37176717656`, job `111360741456`: success on the exact merge above.
  Both verified SQLite/PostgreSQL upgrade/downgrade, 207 Python tests (2 missing-Stockfish
  skips), 3 SDK tests, production build, and 20 browser tests (50 intentional
  viewport-duplicate skips). No Python database cleanup warnings.
- Desktop and minimum-phone CI screenshots were inspected: board square, no horizontal
  overflow, readable pieces and controls. Local Chromium is absent; CI supplies the
  browser execution gate.
- Independent backend review found no terminal-action correctness issues. Migration
  0007 add/remove coverage was included after review.
- The initial CI run exposed an additional cleanup warning despite green tests. The
  follow-up shields short ASGI database calls. A real TestClient disconnect during a
  slow SQLite driver query hung when that shield was removed (20-second bounded
  subprocess); with the fix, teardown finishes and the pool has zero checked-out
  connections. The separate double-native-cancel regression also checks cleanup.

## Current work and exact next target

Stage 6A is merged and its checkpoint is preserved. No code work is in progress.

1. Create a dedicated Stage 6B contributor branch from the verified main merge above.
2. Implement explicit pause-safe AI-to-human and human-to-AI seat takeover. Persist
   seat changes and append immutable events; preserve the position and settled clocks.
3. Fence in-flight proposals and old turn leases across takeover. Runner grants cannot
   silently rebind to a new seat; require an appropriate pairing when needed.
4. Verify takeover in both directions, restart recovery, concurrent updates and stale
   results, plus UI acceptance. Then PR, CI/merge verification, immutable pickup and
   retained contributor handoff.
5. Stage 6C adds human consultation. Multiuser ownership/invitations remain at the final
   deployment stage; do not expose the current loopback operator app publicly.

## Boundaries

Local operator controls are not identity-based seat permissions. Draw claims are
supported; negotiated draw offers and agent acceptance remain deferred. Legacy
bodyless resign infers a human seat; the new UI always sends explicit color/version.
Clocks continue in dialogs. Runner grants remain bound to one match/seat/generation;
distributed delivery routing and multiuser authentication remain later work.
