# AI Chess Lounge contributor pickup

Updated 2026-10-04. Read AGENTS.md, README.md, MASTER_PLAN.md, STAGE_7_MODEL_LAB.md
and ADR 0023 before continuing.

## Verified baseline and authorization

Main and immutable pickup/stage-6c-complete are verified at
087c565bbba7e88473e36d17584d08ba6db230d4 (Stage 6C PR17).
The retained feat/stage-6c-consultation branch has its final handoff at fe596148.
Main was unchanged and the working tree clean before Stage 7A began.

Today's explicit continuation supersedes last night's stop. New work may be built,
tested and published as draft PRs. Do not merge, deploy, purchase services, create
credentials, expand access, or perform destructive operations without the relevant
approval. Parent supervisor handles monitoring; do not create duplicate monitors.

## Current work: Stage 7A implementation ready; CI and draft publication pending

Contributor: feat/stage-7a-experiment-builder, based on the exact main commit above.
No completed pickup branch is claimed until approved merge and verification.

Implemented immutable experiment plans and migration 0010; preview/save/list/read API;
2–8 direct/local entrants; supported effort variants; legal opening suites; repetitions,
color swaps, clocks, stop-limit configuration; deterministic schedule capped at 512
games; canonical SHA-256 manifest; provider effort mapping; mixed-division exhibition
labels. Model Lab UI previews/saves/reopens drafts. Saving never launches a match or
calls a provider. Duplicate save UUIDs replay the original body or reject conflicts.

Validation: make test passed 244 Python tests (2 environment/engine skips), 3 SDK tests,
Ruff and TypeScript. Production build passed. Thirteen new experiment regressions
cover deterministic expansion/hashes, effort mapping, invalid/terminal openings,
unsupported effort, oversized plans, idempotency, restart, no games created and
concurrent duplicate saves. Migration upgrade/downgrade test extended. Desktop/phone
browser acceptance added; CI and screenshot review remain required before merge.

## Next target and limits

Stage 7B durable scheduler: dispatch authorization, atomic durable jobs, concurrency
budgets, cancellation/resume, stop-rule enforcement and original-match recovery.
Can be developed on a dependent contributor branch while 7A awaits merge approval;
keep draft dependencies explicit. Do not run paid-provider batches without approval.

6D/2E account roles and invitations remain for the final hosted multiplayer rollout.
Remote/subscription grants currently cover one match only, not a batch. Plans use
supplied clock information and fixed effort; withheld/adaptive conditions are disabled.
Hash identity does not guarantee provider determinism or pin changing model aliases.
Local operator deployment only. No merge, deployment or security changes performed.
