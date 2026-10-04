# AI Chess Lounge contributor pickup

Updated 2026-10-04. Read AGENTS.md, README.md, MASTER_PLAN.md, STAGE_7_MODEL_LAB.md
and ADRs 0023–0024 before continuing.

## Verified baseline and authorization

Main and immutable pickup/stage-6c-complete are verified at
087c565bbba7e88473e36d17584d08ba6db230d4 (Stage 6C PR17).
The retained feat/stage-6c-consultation branch has its final handoff at fe596148.
Main was unchanged and the working tree clean before Stage 7A began.

Today's explicit continuation supersedes last night's stop. New work may be built,
tested and published as draft PRs. Do not merge, deploy, purchase services, create
credentials, expand access, or perform destructive operations without the relevant
approval. Parent supervisor handles monitoring; do not create duplicate monitors.

## Current work: Stage 7A implementation ready; draft PR18 verified; merge approval pending

Contributor: feat/stage-7a-experiment-builder, based on the exact main commit above.
Draft PR: https://github.com/curtistheconqueror/ai-chess-lounge/pull/18
No completed pickup branch is claimed until approved merge and verification.

Implemented immutable experiment plans and migration 0010; preview/save/list/read API;
2–8 direct/local entrants; supported effort variants; legal opening suites; repetitions,
color swaps, clocks, stop-limit configuration; deterministic schedule capped at 512
games; canonical SHA-256 manifest; provider effort mapping; mixed-division exhibition
labels. Model Lab UI previews/saves/reopens drafts. Saving never launches a match or
calls a provider. Duplicate save UUIDs replay the original body or reject conflicts.

Validation: make test passed 245 Python tests (2 environment/engine skips), 3 SDK tests,
Ruff and TypeScript. Production build passed. Fourteen experiment regressions
cover deterministic expansion/hashes, effort mapping, invalid/terminal openings,
unsupported effort, null moves, oversized plans, idempotency, restart, no games created and
concurrent duplicate saves. Migration upgrade/downgrade test extended. Desktop/phone
browser acceptance passed on desktop/phone; screenshots inspected after UI polish.
CI run 37215467880 / job 111474957890 passed on published code head
5b931af33f0e753a790dea8a7a066f862c9709f4: 245 Python (2 skips), 3 SDK,
28 browser tests (67 intentional duplicate-viewport skips), SQLite/PostgreSQL
migrations, lint, types and build. Source tree matched local 50579a6 exactly.
This final handoff is docs-only. No merge or completed pickup is claimed.

## Current continuation: Stage 7B draft PR19 verified; merge approval pending

Contributor: feat/stage-7b-durable-scheduler, based on the verified Stage 7A handoff
023f928dfa4b94dbd15a191912ee9bb8005eec0a. Stage 7A remains draft PR18; main is unchanged.
Draft PR: https://github.com/curtistheconqueror/ai-chess-lounge/pull/19
The remote contributor branch is retained. No completed pickup is claimed.

Implemented migration 0011, durable run/job reservations, UUID-stable match identity,
shared four-game concurrency, explicit prepare/start/provider-use confirmation,
pause/resume/cancel controls, original wall deadlines, failure and ply limits,
opening-FEN execution and per-job match links. Cancellation and lease replacement
fence late move commits. Uncertain in-flight requests after a crash fail without
redispatch; only explicit batch pauses resume. Provider failures never auto-retry
through batch recovery. No live provider spending was used for acceptance.

Verification: initial local make test / pytest -W error passed 260 Python tests
(3 PostgreSQL environment skips), 3 SDK tests, Ruff/types and build. Independent
review added exact-claim fencing and conservative crash recovery. First CI caught
an unclosed aiosqlite connection during cancellation. Worker shutdown now drains
current database work; a sixteenth queue regression verifies cleanup. Full warning-
strict local suite passed again, with the new cleanup test passing separately.

Final CI run 37218094548 / job 111482645121 passed on remote code head
9767a4e0ee69d3c28e97b5c35f0cdbd4ff72e78d: 262 Python tests (2 engine skips),
3 SDK tests, 30 browser tests (70 intentional duplicate-viewport skips), SQLite and
PostgreSQL migrations, format/lint/types/build. Source tree matches local 14b0ca4.
Artifact 11309053916 includes batch-desktop.png and batch-phone.png; both visually
inspected with no blocking layout issue. PR18 description refreshed with verified
7A evidence. This final handoff is docs-only; no merge or deployment is claimed.

## Next target and limits

Stage 7C adds tournament formats, standings and division-specific provisional ratings.
Branch from this verified 7B contributor handoff; new PR must remain a dependent draft.
Preserve legacy plan hashes, cap bracket jobs, never count failed/limited games as
chess losses, and leave tied knockout series unresolved without inventing winners.
Keep draft dependencies explicit. Merge and deployment need separate approval.

6D/2E account roles and invitations remain for the final hosted multiplayer rollout.
Remote/subscription grants currently cover one match only, not a batch. Plans use
supplied clock information and fixed effort; withheld/adaptive conditions are disabled.
Global monetary and cross-process request-rate budgets remain Stage 8; batch concurrency
is bounded, and existing provider retry/rate controls remain process-local.
Hash identity does not guarantee provider determinism or pin changing model aliases.
Local operator deployment only. No merge, deployment or security changes performed.
