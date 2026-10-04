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

## Current continuation: Stage 7B draft PR19 retry-test correction; current CI pending

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

## Stage 7C draft PR20 verified; merge approval pending

Contributor: feat/stage-7c-tournaments, based on the 7B handoff
62ea9f012fc79cd474df574ff5672dff8a5ec91d (identical tree to local 13c234a).
Draft PR: https://github.com/curtistheconqueror/ai-chess-lounge/pull/20
Existing contributor branches remain intact. PR20 depends on PR19, which depends on
PR18. No merges are authorized; no completed pickup is claimed.

Implemented separate schema 2.0 tournament plans without changing v1 hashes;
round robin and gauntlet pairing; bounded knockout templates with winner-dependent
claims; blocked unresolved descendants; natural-results-only standings and local
provisional ratings separated by division/clock/protocol. UI adds format/anchor selection, bracket previews, and standings with unrated/no-result
disclosures. Thirteen tournament regressions pass, including a real three-game
knockout with the correct semifinal winners in its final and simultaneous final claims.
Final warning-strict Python gate passed 274 tests (3 PostgreSQL environment skips).
The earlier full make test also passed 3 SDK tests, Ruff and TypeScript.
Final CI run 37219539437 / job 111486895987 passed on published code head
14ef669560241e4b554e501fbab6577c3132d014: 275 Python tests (2 engine skips),
3 SDK tests, 34 browser tests (76 intentional duplicate-viewport skips), SQLite and
PostgreSQL migrations, format/lint/types/build. Remote tree matches local 36eb5a9.
Artifact 11309074209 contains tournament and tournament-report screenshots for both
desktop and phone; all four inspected. Wide tables stay contained, with no blocking
layout issue. Local Chromium is unavailable; CI supplied browser acceptance.
This final handoff is docs-only.

## Next target and limits

Stage 7D adds reliability/efficiency metrics and honest comparison uncertainty.
Branch from the final verified 7C handoff and keep the next PR dependent/draft.
Use existing public move metadata; missing usage/cost is unknown, not zero.
Do not imply repeated openings are independent evidence or that local ratings are
calibrated human Elo. Preserve the established v1/v2 manifest hashes.
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

## Retry-test follow-up (2026-10-04)

PR19 docs head 62ea9f0 failed CI 37218427567 after its earlier code-head success:
a fixed 600 ms wait read version 1 while the second retry move was still saving.
The correction waits for committed version 2 with a five-second deadline and adds
a slow-response regression. PR19 correction head f5992ec has CI 37220994565 pending.
This dependent branch carries the identical test correction (code head 161379f1).
Local warning-strict 7C suite: 273 passed, 5 environment-dependent skips.
Prior final 7C docs head 1e5b1ac passed CI 37219857364, but current corrected-head
CI and browser acceptance must be verified separately. No runtime code changed.
No merge, deployment or completed pickup is claimed.
## PR19 current-head verification correction (2026-10-04)

Docs-only head 62ea9f012fc79cd474df574ff5672dff8a5ec91d failed CI
37218427567 / job 111483628735: 261 passed, 2 skipped, one retry-test failure.
The earlier code-head success above remains historical evidence, not a green
check for that later head. Both migrations passed; browser/SDK/build were skipped.

The retry test observed engine.calls == 2 but read version 1 before the second
move committed. Its fixed 600 ms sleep allowed only 100 ms beyond the 500 ms
retry delay. Snapshot intentionally returns the last committed position while a
writer owns the lock. Both engine and lease-retry tests now wait for committed
version 2 under a five-second deadline, retaining exact attempt/move assertions.
A 200 ms engine-response case reliably covers the old timing assumption.
No runtime retry behavior changed. Local warning-strict suite: 260 passed,
5 environment-dependent skips; manager tests: 15 passed; Ruff/checks passed.
Published correction CI and browser acceptance are pending; do not call current
PR19 green until its final head is verified. Propagate the test fix to 7C/7D.
No merge or deployment performed.

## Stage 7D comparison metrics in progress

Contributor: feat/stage-7d-comparison-metrics. Based on final 7C handoff
1e5b1acd57dddd76ac9496cfb33e0a052f273af2, with the same retry-test correction
subsequently published to PR19/PR20. New publication must remain a dependent draft.

Implemented read-only comparison metrics from stored jobs, moves and public metadata:
chess results separated from no-results, illegal/failure/timeout events, accepted-move
latency/retries, usage/cost coverage, and matched effort comparisons. Unknown usage
is unknown, not zero. Exact opening FEN defines a block; repetitions/color swaps
do not increase independent evidence. Conditional 95% Hoeffding ranges require
complete natural-result fixed schedules, comparable pools and at least two blocks.
Knockout, incomplete, mixed-pool or unmatched conditions suppress intervals with reasons.
The UI explicitly loads/refreshes snapshots, discloses stale revision and assumptions,
and contains wide tables on mobile. No provider or engine call is made by metrics.
See ADR0026; original v1/v2 hashes remain unchanged.

Local warning-strict suite: 286 passed, 3 PostgreSQL environment skips. Eleven
metrics cases cover block dependence, interval suppression, paired effort matching,
Black-to-move attribution, unknown versus zero cost, metadata privacy and read-only API.
Manager regression suite: 15 passed. Type/lint/build and CI/browser evidence must
be recorded before completion; local Chromium is unavailable. No merge/deployment.
Next after verified 7D: Stage 7E comparison reports and export bundles.
