# AI Chess Lounge contributor pickup

Updated: 2026-10-04. Read AGENTS.md, README.md, MASTER_PLAN.md and ADR 0022.

## Verified baseline

Stage 6B merged in PR #16 at `655ce42154d59e97dd2d8db9ee0b2e8f0d3f280d`.
Immutable pickup/stage-6b-complete and retained feat/stage-6b-seat-takeover remain.
PR CI 37183260435 and postmerge CI 37183451633 passed: 215 Python, 3 SDK,
23 browser tests (57 intentional duplicate-viewport skips).

## Current work — Stage 6C

Contributor feat/stage-6c-consultation was created from that exact verified merge.
Implementation complete; final CI/publication gates are in progress. Do not label
complete until merged and the immutable pickup branch is verified.

- Human-turn-only adviser requests; never apply a move automatically.
- Background advice uses bounded existing adapter policy, deadline and lease; CAS
  rejects late results after any match revision change.
- Human confirmation includes consultation ID/revision; manual moves remain available.
- Migration 0009 persists advice/history; events and PGN disclose Human-AI Team assistance.
- Configured provider/local models, Stockfish strength and deterministic practice adviser UI.
- Cancellation, graceful shutdown recovery, deadline refresh and stale-dialog fencing.
- Provider errors are sanitized and do not pause a human turn.
- ADR 0022 and STAGE_6_HUMAN_PLAY.md cover contracts, recovery and boundaries.

## Verification gates

Sixteen consultation regressions cover no-auto-move, explicit human confirmation,
idempotency, saved history/PGN, restart, cross-worker supersession/cancellation,
duplicate requests, time expiry, provider retries and sanitized failures.
Local make test/build and pytest -W error passed: 231 Python tests, 2 environment/engine
skips, 3 SDK tests, Ruff lint/format and web typecheck. Independent backend review
found no remaining blocker after graceful shutdown recovery was tightened. Exact-head
CI is required before merge. Desktop/phone browser
acceptance covers reload, review/cancel/confirm, Black advice and stale confirmation.
Local Chromium is absent; CI supplies browser execution and visual artifacts.

## Stop and next target

The owner explicitly requested Stage 6C be the LAST phase tonight. Stop after its
verified merge, postmerge smoke and contributor/pickup handoff. Do not start more work.
When the owner resumes, Stage 7A Model Lab experiment configuration is the proposed
next target. Stage 6D account roles/invitations remain reserved for the final multiplayer
rollout, alongside Stage 2E accounts. Stage 6 has four phases; 6A–6C are implemented.

## Boundaries

Local operator only. Consultation request deadline <=30 seconds and remaining clock.
No automatic retry after abrupt crash; cancel pending advice or wait for its original
deadline. Graceful shutdown records cancellation only for this worker's owned requests.
Remote runner/MCP/subscription seat grants cannot be repurposed as adviser grants;
remote adviser authorization remains deferred. Provider budgets remain process-local.
No live provider credits are required by the deterministic acceptance suite.
