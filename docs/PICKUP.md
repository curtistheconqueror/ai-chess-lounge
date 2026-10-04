# AI Chess Lounge contributor pickup

Updated: 2026-10-04. Read AGENTS.md, README.md, MASTER_PLAN.md and ADR 0022.

## Verified baseline

Stage 6C merged in PR #17: https://github.com/curtistheconqueror/ai-chess-lounge/pull/17
Merge commit: `087c565bbba7e88473e36d17584d08ba6db230d4`.
Immutable `pickup/stage-6c-complete` is verified at that exact commit.
Retain `feat/stage-6c-consultation`; its final docs-only handoff is newer than the merge.
The published PR head `b73cdbf4719868b7f369b781dcb9ad455442e2db` and merge tree
were both verified identical to local tested implementation `ce6ceb7`.
Stage 6B remains available at pickup/stage-6b-complete (655ce42).

## Completed work — Stage 6C

Human AI consultation shipped. No active implementation remains for tonight.

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
found no remaining blocker after graceful shutdown recovery was tightened.
PR CI 37185382233 / job 111386097146 passed on the exact published head:
231 Python tests (2 environment/engine skips), 3 SDK tests, 26 browser tests
(64 intentional duplicate-viewport skips), SQLite/PostgreSQL upgrade/downgrade,
lint, typecheck and production build. Desktop and phone screenshot artifacts were
visually inspected with no blocking layout defect. Browser acceptance covers reload,
review/cancel/confirm, Black advice and stale confirmation.
Postmerge CI 37185612478 / job 111386767719 passed all the same gates on main.
The phase is complete; the next stage has NOT been started.

## Stop and next target

The owner explicitly requested Stage 6C be the LAST phase tonight. Stop after its
verified merge, postmerge smoke and contributor/pickup handoff. Do not start more work.
Resume by fetching main and this retained contributor branch, reading this handoff,
and branching from the verified merge above; do not repoint any pickup branch.
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
