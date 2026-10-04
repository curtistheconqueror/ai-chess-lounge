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
Correction CI 37220994565 / job 111491128151 passed on head
f5992ec8930f2ed0625969ef33c02f1820996e4f: 263 Python tests (2 engine skips),
3 SDK tests, 30 browser tests (70 intentional duplicate-viewport skips), both
migrations, lint, types and build. The identical test fix is propagated to 7C/7D.
This evidence names the tested head; the present follow-up only updates these notes.
No merge or deployment performed.

## Stage 7D draft PR21 verified; merge approval pending

Contributor: feat/stage-7d-comparison-metrics. Based on final 7C handoff
1e5b1acd57dddd76ac9496cfb33e0a052f273af2, with the same retry-test correction
subsequently published to PR19/PR20. Published draft PR: https://github.com/curtistheconqueror/ai-chess-lounge/pull/21
PR21 depends on PR20; both remain drafts.

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
Manager regression suite: 15 passed. Type/lint/build passed. CI 37221739158 /
job 111493280284 passed on code head 6d52f5b4653daacaf1902b03f8daa7534a82e938:
287 Python tests (2 engine skips), 3 SDK, 34 browser (76 intentional viewport skips),
SQLite/PostgreSQL migrations, lint/types/build. Artifact 11311015337 includes
metrics-desktop.png and metrics-phone.png; both inspected, wide tables contained,
board remains usable. Local Chromium is unavailable; CI supplied browser acceptance.
The selected-run guard prevents late metrics from another run appearing in the panel.
This follow-up updates documentation only; no merge/deployment or completed pickup.
Next after verified 7D: Stage 7E comparison reports and export bundles.

## Current validation and delivery target

PR20 correction head f2b4bc3c11225f152673408c64a0a3aa2c18de0a passed CI
37221279231 / job 111491962732: 276 Python (2 engine skips), 3 SDK,
34 browser (76 intentional viewport skips), migrations, lint/types/build.
Only source-branch synchronization resolved the pickup conflict; no PR was merged
into its target and main is unchanged. PR19's verified correction is recorded above.
Stage 7D source, eleven new regression cases, UI/types/build are locally verified;
its code-head CI/browser gate passed as recorded above. Final docs-head checks
remain a distinct required check; do not substitute historical code-head success.

Requested target: October 6, 2026 17:40 UTC / 12:40 PM America/Chicago.
Read DELIVERY_48H_PLAN.md for phased checkpoints, effort ranges, dependencies and
explicit deferred requirements. Stage 9 is eight unselected expansion candidates,
not an authorized fixed scope. Account/security/merge/deploy/spending decisions
remain gates; do not treat the date as approval or promise all stages will finish.

PR19 final pickup head ade6bb27523b9fc6709dee15d3837ebf148a853d also passed
CI 37221621195 / job 111492949368 after the evidence-only follow-up. PR19 and
PR20 current-head statuses are green at this checkpoint. All drafts remain unmerged.

## Stage 7E draft PR22 verified; merge approval pending

Contributor: feat/stage-7e-report-bundles, based on verified final 7D handoff
fa2e9a106bb47a5a60c083b9048b2fdebd2ae581. That final docs head passed
CI 37222067606; PR21 remains draft and unmerged. Draft PR: https://github.com/curtistheconqueror/ai-chess-lounge/pull/22
PR22 depends on PR21; all contributor branches remain retained.

Implemented bounded terminal-run report ZIP, immutable manifest/hash verification,
explicit public-data projection, exact initial-FEN PGN replay and honest no-results,
CSV formula neutralization, per-file checksums, optimistic revision validation and
size/move caps. Frontend pool filters and download controls pass typecheck/build and e2e test discovery.
Final local warning-strict suite passed 301 Python tests (3 PostgreSQL environment
skips); final focused export suite: 15 passed. Independent review added saved-match
lifecycle/outcome agreement with the job result, reusing authoritative result logic.
Ruff, TypeScript/build and 3 SDK tests pass. CI 37223412652 / job 111498088879
passed on published source head 64f7c2c08f7e09cdc33606ff6ca33168ca495c03:
302 Python (2 engine skips), 3 SDK, 34 browser (76 intentional viewport skips),
SQLite/PostgreSQL migrations, lint/types/build. Remote tree matches local 888f879.
Artifact 11311585438 includes desktop/phone metrics screenshots, visually inspected;
pool filters and full-run ZIP download controls remain contained and usable.
Browser acceptance downloaded ZIPs on both viewports. No live paid providers used.
This follow-up changes documentation only; verify its current-head checks separately.
See ADR0027. No target-branch merge, deployment or completed pickup is claimed.
After 7E acceptance, proceed to 8A read-only security assessment and approval-ready
account/deployment design; do not implement security/access expansion without approval.
DELIVERY_48H_PLAN.md remains the dated target with explicit Stage 9 scope decision.

Stage 8A read-only assessment has started while final 7E documentation checks run.
No credential files were read and no permissions/settings were changed. Current
tracked-source pattern scan and 632 reachable local-ref blobs (7,640,628 bytes,
up to 2 MiB/blob) had no key-pattern candidates. npm lockfile audits for web/SDK
and pip-audit 2.10.1 for 54 pinned Python records reported zero known advisories.
These are scoped, dated observations, not proof of security; trust-boundary review,
abuse tests and account/deployment decisions remain. Preserve detailed findings
privately per SECURITY.md. Parent continues to own monitoring and approvals.

## Stage 8A read-only assessment in progress

Contributor: docs/stage-8a-security-assessment, based on final 7E handoff
5baac32a098d21bf046d2c201daea25be7812097. Preserve all earlier branches.
Main was rechecked and remains 087c565. See STAGE_8_HARDENING.md for scoped
audit evidence and remaining validation; ACCOUNT_AND_RELEASE_DECISIONS.md is an
owner-review proposal, not approval to implement or enable security/account access.
No confidential exploit details or credential material belong in this public handoff.
Next safe independent work: 8B operational runbooks and offline fixture backup/restore
rehearsal, 8C bounded local load design, and 8D budget semantics. Do not mark 8A
complete until reviewed findings and authorized remediation are dispositioned.

PR22 final documentation head 5baac32a098d21bf046d2c201daea25be7812097
passed CI 37223844056. Its description now records source and final-head evidence.
Stage 7E implementation and browser acceptance are verified; merge remains gated.

## Stage 8B offline operations preparation in progress

Stage 8A assessment was published as dependent draft PR23:
https://github.com/curtistheconqueror/ai-chess-lounge/pull/23
Its source head is 786f8b70cdb12b29bf009e2214817c4c31e63494 (local b87cbbd
has the same tree). It remains an assessment/decision packet, not 8A completion.

Current contributor: test/stage-8b-restore-rehearsal, based on that published head.
Two offline generated-fixture SQLite recovery tests verify complete persisted data,
terminal game/run/report reconstruction and committed-versus-uncommitted WAL handling.
OPERATIONS_RUNBOOK.md tracks health/readiness, telemetry, alerting, backup/restore,
retention and incident/rollback deliverables honestly; production acceptance is pending.
No live data, credentials, security settings, paid providers or deployment changed.
Next: verify this branch's complete checks, publish a dependent draft, then bounded
local readiness/instrumentation and native PostgreSQL fixture recovery. Keep 8B open.

Local 8B checkpoint: 303 Python tests passed with warnings as errors (3 PostgreSQL
environment skips), including both restore rehearsals; Ruff format/check and
`git diff --check` passed. No PostgreSQL client/server binary is available locally;
native PostgreSQL backup/restore acceptance remains outstanding. Current-head CI
and published browser checks must be recorded separately after publication.

PR23 source head 786f8b7 passed CI 37224743392 / job 111501964970, including
both migrations, Python, SDK, web build and responsive browser gates. This verifies
the assessment branch's unchanged runtime, not completion of 8A remediation.

Published 8B preparation draft: https://github.com/curtistheconqueror/ai-chess-lounge/pull/24
Base is PR23 / docs/stage-8a-security-assessment. Source checkpoint f53c4922dbc672b068dc62e81bd073ab304d49ae
triggered CI 37225092974; status was pending at this documentation update. Verify
this follow-up's final head independently. The dated plan includes remaining effort
ranges and integration buffer; Stage 9 and release decisions are still unresolved.

## Stage 8B local operations continuation in progress

PR24 final head fc7ea99b77d6409bfe907bfa195073d788e946ab passed
CI 37225178400; parent evidence was independently rechecked. Remote head matches
that SHA and its complete tree was already stored locally. Current environment
blocks direct GitHub network fetch; use GitHub connector reads and the previously
authorized publication UI, not alternate network routes. Preserve all branches.

Contributor: feat/stage-8b-local-operations, based exactly on PR24 final head.
Added compatible liveness plus bounded shared-probe readiness, local capped request
correlation/timing summaries and WebSocket counts. Privacy, slow-probe/single-flight,
worker staleness, shutdown, concurrency and unchanged-match tests pass locally.
Added explicit generated-only native PostgreSQL CI restore and event-accessor
validation. CI service supplies native tools; no local PostgreSQL/Docker tools exist.
Native recovery is NOT verified until published CI passes. ADR0028 records bounds
and limits. Full 8B tracing/metrics/alerts/retention/production backup acceptance remains
open; no access/security/account/deployment or paid-service action was performed.

Next: complete current-head checks and native CI restore, review and publish a
dependent draft with exact evidence. Continue bounded performance preparation and
budget reservation design while owner account/release decisions remain pending.

Local continuation verification: 309 Python tests passed with warnings as errors
(4 PostgreSQL infrastructure skips), Ruff format/check, web type/production build
and 3 SDK tests passed. Native PostgreSQL restore and final published browser checks
remain CI gates. No dependency or external service was added.

Independent read-only review found no route from the native fixture to a configured
application DB/provider. It prompted clearer quiescent-fixture versus production
recovery wording and nested cleanup so a close/dispose failure cannot skip attempted
disposal of the other resources, generated DB cleanup or admin-engine disposal.
Native tools run in the ephemeral CI service; Docker-client timeout is not a claim
of generic remote process termination. Native recovery verification still requires CI.

## Stage 8B local operations verified source checkpoint; phase still in progress

Dependent draft PR25: https://github.com/curtistheconqueror/ai-chess-lounge/pull/25
Contributor feat/stage-8b-local-operations is based on PR24's final fc7ea99.
Reviewed source head 2e3c150ac0d094486130b8f6e42dc197a0b4115e passed
CI 37226798676 / job 111507996632: 311 Python (2 engine skips), 3 SDK,
34 browser (76 intentional viewport skips), SQLite/PostgreSQL migrations and all
lint/type/build gates. Initial source 3d65fed also passed CI 37226694209.
Native PostgreSQL restore executed successfully, not skipped. Artifact 11312098665
contains secret-free fixture evidence: 13 tables, 14 rows, 31,864-byte custom archive,
0.3104 seconds including restore/validation; no production RPO/RTO claim.
The artifact's desktop/phone metrics/board screenshots were visually inspected; no
layout blocker found. No live provider call, production restore or deployment used.

This follow-up updates docs only; verify its final head separately. Retain every
contributor branch and draft. Main still 087c565; no target-branch merge or completed
pickup is claimed. OPERATIONS_RUNBOOK.md/ADR0028 specify implemented limits and
remaining 8B production tracing/metrics/alerts/retention/backups. PERFORMANCE_ACCEPTANCE.md
is bounded 8C preparation only, not measured capacity or 8C completion.

Exact next safe target: implement and measure the generated-fixture 8C harness
across HTTP/readiness, spectators/WebSockets, queue/database and real engine when
available, preserving correctness and cleanup gates. Continue 8D budget reservation
contract design; account/security/budget-owner/release policies remain decisions.
Keep the October 6 12:40 PM America/Chicago target and final integration buffer
visible; Stage 9 scope is still unresolved and 2E/6D requirements remain deferred.

## Stage 8C bounded performance continuation in progress

PR25 final docs head 076c82aabcaf77312389c99625c37ac955a313bf independently
passed CI 37227215973. Local retained 2836835 has the equivalent final tree;
remote/local browser-upload commit histories differ. Preserve both histories.
Contributor test/stage-8c-bounded-performance starts from that verified tree.
The harness exercises HTTP/readiness, coalesced spectators/reconnect, shared queue
claims/fencing/database recovery/report exports, plus real bounded Stockfish when
available. No live provider, account/security change, deployment or merge.

Initial local discovery succeeded across all default schedules; regression tests
cover rejected unsafe bounds, non-CI PG refusal, real pipelines, sibling cancellation
and socket validation-failure cleanup. Native PG benchmark and final full/browser CI
remain publication gates. See PERFORMANCE_ACCEPTANCE.md/ADR0029 for measured
scope and gaps; no full 8C completion or hosted capacity claim.

Next safe work: publish dependent draft and verify exact current-head CI/artifacts;
continue 8D attempt reservation contract and symbolic-unit offline invariants. Keep
all contributor branches. Main remains 087c565. No immutable completed pickup before
approved merge. Account/budget/release decisions and Stage 9 selection remain open.
Target October 6 17:40 UTC with 8–9-hour integration buffer remains conditional.

Local source checkpoint 79aac08: 321 Python tests passed with warnings as errors,
4 PostgreSQL infrastructure skips; Ruff format/check passed. Default SQLite/ASGI/
queue plus actual Stockfish 16 benchmark succeeded with explicit limits.
Remote publication history differs; record its head and full CI separately.

Published dependent draft PR26:
https://github.com/curtistheconqueror/ai-chess-lounge/pull/26
Source head 3c84e1fe06bf3bb7a3c00ff9111da670eecae261 passed
CI 37230951795 / job 111520263552: 323 Python (2 missing-engine skips),
3 SDK, 34 browser (76 intentional viewport skips), both migrations/lint/types/build.
Native benchmark measured SQLite and PostgreSQL17.11; installed engine absent in CI
and explicitly skipped, while local Stockfish 16 measurement succeeded. Artifact
11313727043 records tested synthetic merge SHA a4996b50aa1926408bfacea6404964db055707cd
(the PR source SHA above is distinct), runner EPYC7763/four CPUs/~16GiB memory,
100-spectator post-commit drain p95 386.6ms SQLite/615.6ms PG, eight-game queue
1/4-lease times 4.562/1.743s SQLite and 4.572/1.501s PG. All fixture correctness and
cleanup checks passed; no hosted capacity claim. Native restore evidence remains
in the artifact. Desktop/phone screenshots inspected with no layout blocker found.
This documentation follow-up receives a separate current-head CI verification.

## Stage 8D reservation design and offline oracle in progress

Contributor docs/stage-8d-reservation-contract follows the Stage8C final docs tree
(local88745f9; published7b8f35b356a26cf7f129c37c98ae3488af5b0daf).
PR26 source3c84e1f passed CI 37230951795; final docs CI 37231366411 is running.
Do not describe a pending final head as green. Preserve all branches and drafts.

Added BUDGET_RESERVATION_CONTRACT.md/ADR0030 and a strictly test-only generated
SQLite oracle with symbolic units. Five local tests pass, including four spawned
processes competing for eight reservations, replay/recovery/uncertainty/evidence and
unknown-versus-zero/overage behavior. The application imports none of this fixture;
no schema/dispatch/permission/paid-call change. Rates, multiple scopes, PG locking,
rollover/adjustments and live integration remain open, as do owner policy decisions.

Next: independent review, full current-head CI, dependent draft publication and exact
pickup. Continue safe local recovery/acceptance work where approvals do not apply.
No merge/deployment/account/security/spending authorization is inferred. October 6
17:40 UTC remains conditional with final integration buffer; Stage 9 selection and
deferred 2E/6D are unchanged outstanding decisions.
Read-only review prompted an 8C correction: move startup under its cleanup guard,
bound fixture regression runs to20 seconds, and label persisted move/event agreement
as an invariant rather than a measured duplicate-submission rate. Declare Linux
resource units explicitly. These changes require a new source-head full CI check.

8D review corrections now reject invalid/null attempt IDs and changed fixture policy;
billing identity is source plus line-item ID, with multiple lines per source supported.
Tests explicitly cover symbolic reopen/recovery, not real process death or chess
commit fencing. Disposable proof tokens state release/recovery preconditions without
implementing actual authorization. Twelve focused tests pass, including both unique
and duplicate attempt races across four spawned processes. No production policy is
selected. Reviewed 8C head105eb2a CI 37231626012 is pending at this update; verify
before stating current-head green. Full 8D CI remains a separate publication gate.

8D local reviewed source8f3383f: 334 Python tests passed with warnings as errors,
4 PostgreSQL infrastructure skips; complete Ruff format/check passed. Reviewed
8C correction is incorporated locally without discarding either contributor branch.
Publication base is PR26 reviewed 105eb2a7db08b0bdfe15e96e4adaaf673b591904;
its full current-head CI is still running at this documentation update.

## Stage 8D verified source checkpoint; full phase still in progress

Dependent draft PR27:
https://github.com/curtistheconqueror/ai-chess-lounge/pull/27
Source 969eb7cf22fc566e3fd583be7537b992d1cdd6ea passed
CI 37231957628 / job 111523407944: 336 Python (2 absent-engine skips),
3 SDK, 34 browser (76 intentional viewport skips), native performance/restore,
both migrations/lint/types/build. Artifact 11314172768 retains aggregate fixture
and browser evidence. No paid calls, production quota or deployment were used.
PR26 reviewed 105eb2a passed full CI  37231626012 (324 Python / 2 engine skips).
Review's 8D oracle blockers were corrected and independently rereviewed without a
remaining material flaw in the stated single-subject/static-symbolic-policy scope.

This follow-up changes docs only; verify its final current-head CI independently.
Retain all contributor branches/drafts. Main remains 087c565; no completed pickup
or merge. BUDGET_RESERVATION_CONTRACT.md/ADR0030 list implemented scope and
remaining shared-rate/multi-scope/PG/period/authority/live integration requirements.
Owner identity/budget/pricing/unknown-cost/kill-switch choices remain gates.

Next safe independent target: local UCI lifecycle/cancellation/failure recovery
regressions and bounded real-engine interruption evidence on a separate contributor
branch. No unrelated owner gate stops that work. Production 8A/8B/8C/8D acceptance,
8E hosted onboarding and deferred 2E/6D remain distinct; Stage 9 scope is unanswered.
October 6 17:40 UTC target remains conditional with the final 8–9-hour buffer.

## Stage 8C engine lifecycle recovery candidate in progress

Contributor fix/stage-8c-engine-recovery retains the 8D reviewed source tree
(local8f73e96, published969eb7cf22fc566e3fd583be7537b992d1cdd6ea).
PR26 reviewed 105eb2a passed fullCI 37231626012; PR27 source 969eb7c passed
fullCI 37231957628. Published counts/artifact evidence are recorded separately at
its checkpoint. No merge/deployment or completed pickup is claimed.

Startup summary/shutdown now serialize with UCI commands. Thread work is drained
on cancellation; failed or cancelled-and-failed handles are discarded; cancelled
startup closes its newly created process. Later requests can restart without an
engine-service move replay. Twenty-one focused engine tests pass, including a real
installed Stockfish termination/reap/fresh legal move; the performance fixture adds
explicit interrupted-service restart evidence. ADR0031 records boundaries. Full
current candidate suite/CI and review are still gates; no hosted capacity claim.

Next: verify latest cancellation/error corrections, full suite and real benchmark,
finish source review, publish dependent draft and verify exact CI/browser artifacts.
8C sustained/hosted load and operator targets remain open. 8D production money/rate
integration requires owner policy; 8B production operations/8A reviewed remediation,
8E hosted onboarding and2E/6D identity/release choices remain outstanding. Stage 9
scope is still unselected; October6 17:40UTC target preserves integration buffer.

Engine reviewed candidate 2e1996f: 353 Python passed with warnings as errors,
4 local PG-infrastructure skips; complete Ruff format/check passed. Real Stockfish 16
fixture interruption/reap/explicit restart succeeded; artifact is local fixture evidence,
not hosted capacity. Independent review found no remaining material defect in the
corrected lifecycle scope. Publication base is PR27 final docs c2670561a685dc93151ef86ded4269b51cff8b74
(local 70df473 equivalent doc tree); CI 37232631478 is still pending at this update.
New engine source needs its own complete published CI/browser check.
