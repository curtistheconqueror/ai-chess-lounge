# AI Chess Lounge contributor pickup

## October 10 - targeted end/restart across tabs

Continues from `71654cfd9dab183b1e006ce3c9c883c4c05def42` (CI147 passed).
The reported screenshot displayed an aborted archive, while read-only server
and database inspection found one different paused Human/Stockfish match with
16 moves holding the table. This is a different blocking game, not evidence of
duplicate live games or a Tailscale cache fault. Current served assets matched
the prior build. Saved snapshots and a consistent SQLite backup preserve the
user's games before changes; no user game was ended to test recovery.

End match and End and start new are now beside the board. The dialog identifies
the exact match/players and pins its generation. Restart archives only that game
and requests normal single-game creation; a concurrent winner or older live
blocker is shown and preserved. Repeated aborts return the same terminal state.
Finished games cannot be revived through stale HTTP Reset/Resume requests.
Active Reset shares the creation lock and refuses a different live blocker.
Live discovery scans beyond five rows so expired entries cannot hide a paused
table. See ADR0038 for the single-process boundary and request compatibility.

Build/typecheck and Ruff passed. Backend lifecycle/API/persistence/private-network
regression:103 passed. Tablet multi-tab/recovery:28 passed. Five additional
isolated-browser-context checks passed, including moves after restart without
shared browser storage. Desktop regression:58 passed and one sound fixture
failed because earlier fixtures left other live games; isolating sound fixtures
resolved it, and all11 sound checks then passed. Private-serving evidence is
recorded in the local restart handoff; verify the new head's CI before any merge. Physical
iPad confirmation remains separate. Existing account access, workflows and public
hosting remain unchanged. PR36 stays draft.

## October 10 - fresh connections and iPad entry

Continues from `687101c6f7fc1aed2ff236ec5b698b5db1695b4d`, verified green
[CI146](https://github.com/curtistheconqueror/ai-chess-lounge/actions/runs/38026332867).
Curtis clarified the device is an iPad and requested reliable entry on every
connection. Root entry previously preferred a locally remembered game over the
server's current table, including old terminal games. Root now discovers only
the server's running/paused table, ignores stale saved-game storage, and shows
an explicit start button when the table is empty. Deliberate game deep links
still preserve archive review. Missing links offer the current table; a new-game
409 opens and explains the existing table without ending it. Blocked storage
does not break snapshot acceptance. API requests and service-worker navigation
bypass HTTP cache; the worker still only serves generic offline content offline.

No connection automatically starts or resumes any game or agent. Paused games
need Resume play, finished games remain archived, and reconnect waits for a fresh
snapshot. Use the private origin root `/` for a new connection or home-screen
launch; do not distribute the old aborted game's deep link as the start URL.

Tablet Chromium/WebKit at820x1180 and1180x820:66 passed, two existing Windows
native-audio skips. Eight entry cases cover fresh/empty tables, stale saved IDs
and cache data, paused and active tables, touch moves after rotation, intentional
terminal review, concurrent new-game conflict, unavailable deep links, background
pause/abort, blocked storage and failed-lookup recovery. Existing tap/drag,
large controls, audio, foreground and offline tests also run in the tablet config.
Use `npm run e2e:tablet`; no workflow changes are included.

Phone matrix:99 passed, three Windows native-audio skips. Desktop regression:
54 passed and one obsolete saved-ID storage assertion failed; that assertion now
checks the selected match displayed on screen. After the final loading/empty-table
label correction,32 tablet entry checks, six phone entry/label checks and ten
desktop entry/navigation checks passed. Build/typecheck and diff checks passed.

Real private HTTPS checks passed in all four tablet profiles with zero mutation
requests and no page errors. The original game was verified unchanged. The
private frontend is refreshed; server and access rules are unchanged. This is
browser emulation, not physical iPad acceptance. Curtis must confirm the start
URL on his iPad. PR36 remains draft; no merge or public deployment.

## October 10 - phone paused/aborted board recovery

Baseline `327b19b6c83c2821cb336a961dccd2fcb06a1206` passed
[CI145](https://github.com/curtistheconqueror/ai-chess-lounge/actions/runs/38020934236).
Curtis reported that the iPhone private board stayed on its first move even after
Abort. Read-only evidence showed the shared practice game had been paused, a New
match attempt returned409 while it was live, and Abort then returned200. The game
was correctly terminal at version1/revision6 with e2e4 saved; retaining its final
board looked like a failed action because recovery controls were far below it.
The served bundle was current, the worker caches only a generic offline page,
and real HTTPS/WebSocket mutation tests succeeded. No gesture or transport failure
was reproduced; actual iPhone acceptance still needs Curtis's confirmation.

Board-adjacent controls now explain paused, aborted, replay, reconnecting and
side-to-move states. Resume play and Play a new match provide direct recovery;
Abort explicitly explains the saved final position. Action completion returns
the view to these controls, and failures appear there. Runner403 responses stop
the unavailable pairing panel/poll instead of repeating every3seconds; access
checks remain unchanged. Existing browser selectors now distinguish the original
New match/LIVE controls from the new board-adjacent alternatives.

New regressions:18 passed across mobile Chromium/WebKit at320/390/430px,
including resume→touch move→abort→new match, archive preservation, denied runner
polling and visible failed-resume feedback. Error mocking blocks service workers
only for that mocked-response case; real worker/play acceptance remains enabled.
Existing mobile compatibility: 33 passed, three Windows native-audio skips. The
responsive aggregate had 138 passed, 95 viewport-scope skips and two ambiguous
selector errors; both affected tests passed after exact-selector corrections.
Build/typecheck and diff check passed. Real private HTTPS mobile-WebKit acceptance
passed the complete flow on two newly created fixture games; only those fixtures
were ended. The user's original FEN, history, status, version and revision were
verified unchanged (timestamps compared by instant, not timezone spelling).

The private static frontend was refreshed without restarting the backend or
changing Serve, access rules or data. Reload once on the phone, then use Play a
new match for the already-aborted game, or Resume play for a paused one. Archived
games are never silently reset or revived. No workflow changes, paid calls,
production migration, merge or public deployment. Local handoff evidence lives
in phone-state-mobile.xml and phone-fix-private-verification.json with an updated
phone-original-aborted-fixed.png. Check this new head's CI before any merge.

## October 10 - app-only publication and approved private HTTPS

Curtis approved publishing ordinary app changes separately from the CI workflow.
This increment starts at verified remote `1c3d468c6803094d848b188c354937352bc41a42`
(green CI144), applies the tested phone code and checklist, and leaves
`.github/workflows/ci.yml` byte-identical to that base. The original commits
`46813c1794c5a61a432329630abfe18c631a64a3` and
`e0d9711c6a5877e8c1c4e5897b59638592740788` are preserved on local
`saved/phone-with-mobile-ci-e0d9711` and in a verified recovery bundle.
The earlier push containing workflow edits was rejected for missing `workflow`
scope. No credential/access changes, force-push or shared-history rewrite.
The mobile CI patch is saved separately; ordinary CI runs the existing responsive
suite, not the new Chromium/WebKit mobile matrix. Local mobile evidence remains
valid; Linux WebKit native audio is still an explicit outstanding gate.

The final six screenshot/board-detail captures passed in both browsers at all
three widths. See PHONE_ACCEPTANCE.md for all passed/skipped/manual gates.
[Stage 3 checklist](HOSTED_NEXT_CHECKLIST.md) records Supabase/Cloudflare access,
runtime, invites and provider funding decisions only. After separate explicit
approval, private HTTPS Serve was activated for the existing account on port8444
to a loopback-only backend8001 and a separate practice database. Existing Serve443
and8443 routes were verified unchanged. HTTPS frontend/API/PWA assets returned200;
Chrome rendered64 squares, persisted e2e4 and received3 secure-WebSocket frames.
The practice game was left paused; wrong-origin and runner-admin requests returned403.
No invitation, ACL/firewall expansion, Funnel, purchase or new credential occurred.
The foreground Serve/runtime has no new autostart and requires the host to stay on.
Remote-device and physical-phone acceptance remain. PR36 stays draft; check this
new app-only commit's CI before merge, and obtain separate authorization to publish
the saved mobile workflow patch if desired. No merge or public deployment.

## October 10 - Stage 2 phone support

Continues from Stage 1 `1c3d468c6803094d848b188c354937352bc41a42`, verified
on the remote PR36 head and green [CI144](https://github.com/curtistheconqueror/ai-chess-lounge/actions/runs/38018779066).
PR36 remains draft on `feat/wooden-move-audio`; no merge or deployment is authorized.
Pointer/tap input, safe-area padding, 44px controls with a square-entry alternative,
home-screen manifest/icons, offline-only service worker, touch audio unlock and
foreground socket resynchronization are implemented. Approved pieces/audio and
all hosted/security guards remain in place. See PHONE_ACCEPTANCE.md for evidence.

Mobile local gate: 33 passed, 3 Windows WebKit native-audio skips at
320/390/430px. Existing five-viewport suite: 125 passed, 95 existing scope skips;
no failures. Build passed. Lighthouse: 73 performance, 100 accessibility,
100 best practices, 63 SEO; indexing is intentionally blocked and performance
findings remain. Physical install/audio/safe-area and two-user Tailscale tests
remain unverified. Linux WebKit native audio is required in CI.

Read-only host verification corrects the earlier restricted daemon check:
Tailscale is Running/Automatic, connected, with zero service exit codes. Existing
private Serve listeners occupy 443 and 8443; no Funnel exposure was reported.
Do not start/reinstall the service or overwrite those listeners. Activation still
requires the colleague identity, reviewed access policy and a separately approved
unused HTTPS port. That preparation changed no network settings; later approved
activation is recorded above. Next: complete the phone
CI/manual gates and use the Stage 3 checklist before considering paid hosting.

## October 10 - Stage 1 trusted Tailscale preparation

Curtis's current direction replaces tonight's hosted rollout with two-person
private practice; paid hosting/Supabase integration is deferred. Baseline
`8de33355290de6b85cf3944421a8a7142c92870c` passed CI143/38009452464.
New `python -m lounge_api.serve` launcher defaults to loopback; explicit direct
Tailscale mode validates exact source peers and bind address. Loopback Serve mode
allows at most two exact Tailscale login headers. Both modes independently check
Host/Origin for HTTP and WebSockets, block administrative/credential/batch routes,
and leave the hosted startup guard intact. See PRIVATE_TAILSCALE.md and ADR0037.

Stage 1 local gate passed: focused 57 passed/four Windows symlink privilege skips;
compatible API suite 402 passed/13 environment skips. Two Unix-only performance
modules remain excluded on Windows. Ruff format/check, diff check and the guide's
real --check command passed. A secret canary stayed absent from catalog, health,
game/event and socket responses. Tailscale 1.102.2 CLI help confirms Serve flags,
but status could not reach its daemon. No installation, sign-in, invite, ACL,
firewall, Serve activation or two-device connection was performed. Those need
approval and live verification; no public exposure or provider calls occurred.
Next phase: pointer/tap input, safe areas, home-screen assets, sound/foreground
recovery, mobile Chromium/WebKit and Lighthouse; physical phones remain a user gate.

## October 10 - keep new-match navigation stable

Continues from `5edf9b97fc6291cbfef71292a403ae5ef8adb478` on
`feat/wooden-move-audio`, draft PR36. CI142 (run38007377223) passed Linux
backend (443 passed, six skipped), SQLite/PostgreSQL migrations, performance,
TypeScript SDK and web build, but failed responsive browser setup: a late
snapshot from the previous match restored its URL after New match succeeded.

Snapshot acceptance now permits a different match only for explicit creation;
ordinary HTTP/socket updates remain bound to the selected match. Socket handlers
also check current socket identity, selected match and effect cleanup, and the
new match waits for its own authoritative socket snapshot before enabling moves.
Generation/revision checks, public-file containment and hosted startup guards
remain in force. No browser assertion, timeout or retry was weakened.

The deterministic regression retained the previous real socket, delivered a late
snapshot/error after switching, and reproduced the old URL failure before the fix.
It now passes at all five viewports, checking URL, saved selection and a legal move
in the new match. A second regression holds the socket pending and checks disabled
moves and viewport containment. It reproduced a 21px tablet overflow from the
longer connecting label; the toolbar now wraps to its available width. The remote
pairing fixture explicitly selects its newly created runner so retained runners
from a previous run/retry cannot change its payload. Credential-exclusion checks
are preserved. Typecheck/build and diff checks passed. The full Windows/Chrome run
passed 124 tests, skipped 95 and exposed that one retained-runner fixture failure;
after its correction the final focused run passed 16 with four viewport skips,
covering both regressions, the original viewport gate and runner credential
exclusion. No application failure remains from those runs. An earlier run also
had a Windows worker exit (3221226505); it did not recur in the full rerun.
Next gate: verify the corrected head's CI before review/merge. Hosted readiness
and the exact Auth patch transfer blockers below remain unchanged.

## October 10 - public-file containment and hosted startup safeguards

Continues from `cdf8abb62256e3911ce56a6cdfd9fb3b5d70f01f` on the same PR36 branch.
A read-only fixture showed the SPA returning the public repository README via
encoded parent traversal. Public paths now reject parent/absolute/drive/stream
forms and require resolved containment, including symlinks, index fallback and
asset-root mounting. Normal assets and game permalinks remain supported.

Hosted or malformed deployment modes now stop before app/manager/worker startup
and database initialization. The container defaults to hosted (blocked in this
unfinished build); loopback Compose explicitly uses local mode. Container startup
no longer runs Alembic. Read-only schema validation checks every revision head,
all mapped tables/columns and caller-specified future ownership columns without
creating or stamping anything. These are safeguards, not playable hosted Auth.
See ADR0036 for integration requirements and limitations.

Focused tests: 29 passed, four Windows file-symlink privilege skips. Actual Windows
directory-junction escapes were tested and denied. File-symlink cases remain in
Linux CI. Aggregate compatible API suite: 374 passed, 13 environment skips
(four native-engine tests without STOCKFISH_PATH in that invocation, five native
PostgreSQL/restore cases, four file-symlink cases). Full collection was blocked by
two Unix-only performance modules importing resource; they were explicitly excluded
from the compatible run, not reported passing. Ruff/format/diff checks passed.
The running loopback app now returns 404 for the original encoded escape, serves
the board with 200, and still reports native Stockfish19. Original saved-game FEN,
version8, already-timeout status and move history remain unchanged. New head needs
its own CI result. No container build was run because Docker is unavailable here.

Recovery status changed: the parent cloud task recovered exact patch a766a78,
24990 bytes, SHA256 a8fc654d45dd851632d02c2c4817bc14b0cc5bfb55d2f1db1f7c9d523b8666e7.
It has NOT been installed or applied on this Windows checkout. The current Library
helper fails applying metadata because native Windows Python lacks os.setxattr.
Both installed Python versions lack it. WSL inspection returned E_ACCESSDENIED;
no retry/bypass. Browser control fails before startup with HRESULT 0x80070003
(missing Windows platform directory). No Supabase connector/CLI or authenticated
Cloudflare configuration/session was verified. Preserve the recovered foundation's
deny boundary when merging; the present guards deliberately block hosted startup.

## October 9 - single-game agent advice stage

Base `19deddeffaa8df225aa714e63a2a3886d794ec7b` is pushed on
`feat/wooden-move-audio`, PR36. Stockfish strength CI140/38004749469 passed;
native Stockfish19 advertises UCI_Elo 1320-3190. Its local runtime proof and
engine tests remain separate from credential-free model fixture acceptance.

This stage adds paused human-to-AI legal move suggestions through board dragging
or square selection. Advice survives reload, does not move a piece, and is passed
as optional context when the AI resumes. Position/revision/seat checks fence stale
advice. The model may choose differently. Existing AI-to-human advice remains.
PGN, events, move metadata and comparison exclusions disclose assistance. Uses the
existing consultation JSON projection; no database migration or runner protocol
change. Stockfish and remote runner advice remain unavailable by design.

Lounge creation opts into one-live-game checks within the local API process;
start-paused enables inspection before dispatch. Independent provider/model/effort
selectors are preserved. Game/per-move usage shows known subtotals and coverage,
keeps missing values unknown and does not double-count reasoning. OpenRouter
reported finite nonnegative response cost is retained. No paid inference was run.

Validation: 134 backend checks passed, one PostgreSQL environment skip, covering
advice, persistence, lifecycle, both advice directions, two independent fixture
agents through checkmate, provider payloads, cost normalization and comparison
behavior. Ten new/strength browser checks passed across all five widths; a tablet
drag fixture initially needed explicit board scrolling, corrected before the full
ten-check rerun passed. Build/typecheck, Ruff and diff checks passed. Additional
desktop/phone compatibility checks passed 11 cases, with three existing desktop-only
skips. New head needs its
own CI; do not attribute CI140 to these later changes.

See SINGLE_GAME_AGENTS.md and ADR0035 for bounds and next gates. The preview has
native Stockfish/practice agents; direct providers report credentials_missing and
Ollama/vLLM have no configured models. Next: select an already authorized model
path, verify its current effort metadata and approve bounded live inference if
paid. Live catalog discovery, complete retry/cancellation billing and enforceable
monetary budgets remain follow-up work; the display is not a spend cap. Existing
Model Lab/legacy API concurrency is unchanged, not a production one-game quota.

Shared hosted play remains blocked on exact a766a78 patch recovery, ownership,
seat/runner authorization, sign-in/isolation acceptance and approved external
hosting. Transcript-only ADR0034/HOSTED_PRIVATE_BETA copies are evidence, not
recovered patch bytes. No credentials, access, migration, deployment or merge.

## October 9 - native Stockfish strength controls

Curtis requested the complete supported strength range, then optional 25-Elo slider
steps and proof the runtime is real Stockfish. The previous selector had five
hard-coded choices, always reset to 1600 after reload, and did not explain its
next-match scope. The UCI adapter silently clamped requests and disabled the Elo
limit at the maximum. These behaviors are corrected.

The local preview now uses the official portable Stockfish 19 Windows engine,
verified against the release archive SHA-256. Its actual UCI handshake advertises
1320-3190 inclusive. `/api/engine/strength` publishes the installed runtime's limits.
The UI offers exact integer entry, a collapsible slider with 1/25-Elo increments
and both endpoints, and a separate Full strength option. Rated 3190 keeps
UCI_LimitStrength enabled; Full strength disables it and resets Skill Level to its
advertised maximum. Values outside the runtime range return validation errors.

The chosen next-match setting persists locally. Current match strength is shown
separately; existing games require the established pause/apply-seat workflow.
Full-strength flags persist in player settings, engine summaries and comparison
conditions without a database migration. Approved pieces, selected original
single-tap sound, board colors and the user's original match are preserved.

Verification: 106 backend/API/persistence/lifecycle/identity checks passed, with
two environment skips (native-process recovery without STOCKFISH_PATH in that
test invocation and PostgreSQL without TEST_POSTGRES_URL). Separate tests against
the real Stockfish19 executable passed all three engine checks, including both
Elo boundaries and full strength. Thirteen focused strength tests passed, including
reset persistence and paused-seat validation. Five browser checks passed across
all viewport widths, including exact input, optional 25-Elo steps, reloads, new
matches and unchanged active configurations. Build/typecheck, Ruff and diff checks
passed. See `STOCKFISH_STRENGTH.md` for runtime provenance and behavior.

The actual app also completed a disposable 3100-target match turn: e2e4 received
native Stockfish c7c5, with runtime version19 and108ms latency. This was a separate
test game; the user's existing match was not reset. Contributor remains
`feat/wooden-move-audio`, draft PR36. Baseline97b9c43 passed CI139; this change
requires a fresh CI result. Hosted beta remains blocked on the exact patch.

## October 9 - approved pieces applied to the actual board

Curtis approved the proposed original SVG set, confirmed the knight is recognizable,
and explicitly renewed the request to apply it to the actual board with the chosen
single-tap sound, then push. `ChessBoard` and `ChessPiece` now default to the exact
approved classic set; the promotion picker inherits the same renderer. The SVG
paths, selected original wood WAV and board colors are unchanged. Previous pieces
remain available only in the studio's explicit comparison. No Git main merge or
hosted deployment is authorized or performed.

The existing local match's position, version, status and move history were verified
unchanged across the frontend rebuild. It was already timed out; it was not reset.
Actual board: `http://127.0.0.1:8000/games/aa665dea-b888-499a-a4e7-3eabc55bb59a`.
Refresh an existing tab with Ctrl+Shift+R to load the new built assets. Test sound
plays the selected single tap; a new match is needed to continue playing after a
timeout. This remains a local preview, not a hosted beta release.

Production build/typecheck and 67 focused browser checks passed: 65 sound/board/
piece checks across five viewports plus both-color promotion, underpromotion and
keyboard cancellation on desktop and phone. A reload-layout assertion initially
ran before the live connection; it now waits for that readiness state, and the
entire 65-check suite passed again without retries. Approved SVG and audio bytes
remain unchanged; desktop board and phone promotion screenshots were inspected.

The preceding review-only commit `5b00edf5bd23263fb56f91f2c5e334ec373184e1`
passed full Linux CI run138/38000111473. The actual-board adoption commit needs
its own CI result. Hosted-beta exact-patch recovery is still blocked.

## October 9 - original piece comparison ready for review

Audio/default/mute and four-board preview commit
`d5ab254196a6e6fc6f7f1b69a9902533c9ca7903` passed full Linux CI run137,
37999350235. This closes the prior mute failure; both migrations, API/domain,
performance, SDK, build and responsive browser steps succeeded.

Curtis then requested clearer pieces. The original SVG set in `ClassicPiece.tsx`
is review-only at `/board-studio?pieces=compare`, alongside the current set.
The knight has a long side-profile muzzle, single dominant ear and concave throat;
the full set shares outlines and stepped bases. No proprietary assets were copied
and no Figma tooling was used. `ChessPiece` and `ChessBoard` accept an optional
design, defaulting to the existing set; the live game and promotion picker retain
their current appearance. Audio and board finishes are preserved.

The studio shows all 12 proposed pieces on both square colors at 32, 40 and 64 px,
with all four board finishes and a silhouette toggle. Ten board/piece browser
checks passed across five viewports, with no skips/failures/retries; production
build and diff checks passed. Desktop, silhouette and minimum-phone screenshots
were inspected. This later artwork commit requires its own CI result; do not
attribute the earlier green run to a different head. Next: Curtis reviews the
proposed piece set before changing the live game. Exact hosted-beta patch recovery
remains blocked, independently of these visual changes.

## October 9 - selected original tap, mute fix and board comparison (in progress)

Curtis selected the supplied original single-tap WAV, Sound 13, as the normal
move baseline. It is now the default for moves, captures and Test sound. The
four-tap demo repeats exactly the same PCM tap four times at identical gain;
it is not used by the game. Existing candidates 1-12 and completed variants
14-19 are preserved. Further sound expansion has stopped.

PR36's previous head `d6c84446619b7eedf0703328a8c71557b147e24c` failed the mute
assertion in Linux CI run 37997688759. The implementation now cancels gain
automation, sets gain to zero immediately and stops active sources. The original
assertion remains, with a new native suspended-clock regression test.

The `/board-studio` route compares current, wood, glass-inspired and metallic
boards with shared position, flip and highlight controls. Live board appearance
has not changed; Curtis's selection is pending. See `BOARD_SOUND.md` for details.

Local production build and 60 focused Chrome checks passed across five viewports
with no skips, failures or retries. Desktop and minimum-phone screenshots were
inspected. Current-head Linux CI must be verified separately from this local
result and the earlier failed run. Continue on `feat/wooden-move-audio`, draft
PR36, based on PR35 source `ccef4d7d58edc599995bcece1bf06dec0435adbe`.

Hosted beta remains blocked: exact patch `a766a78` bytes have not been recovered
and hash-verified. Do not reconstruct or claim hosted completion. No merge,
deployment, production migration, credential/access changes or spend occurred.
The entries below record earlier checkpoints and their then-current defaults.

## October 9 — wooden move audio and audition dashboard

Contributor `feat/wooden-move-audio` starts from verified PR35 source
`ccef4d7d58edc599995bcece1bf06dec0435adbe`. Curtis prioritized local sound and
then requested twelve numbered wood-contact auditions. Existing code had no audio.
The branch adds original live move/capture audio, gesture unlock, mute/volume,
an explicit test button and `/sound-lab`; Sound 1 remains the board default.
Auditioning does not change that default. Other candidates are new original
variants, not copies or claimed matches of the unidentified earlier reference.
See `BOARD_SOUND.md` for behavior, test instructions and boundaries.

Local production build/typecheck and 30 native Chrome audio/browser checks pass
across all five viewports; desktop and minimum-phone screenshots were inspected.
Distinguish browser signal measurements from actual owner listening.
Published-head CI must be checked independently. No merge
or hosted-beta completion is claimed. Exact beta patch recovery remains pending;
the local preview uses a fresh SQLite database and is bound to loopback only.
Keep the external/non-OpenAI hosting requirement and all live-release approvals.

Published draft PR36: https://github.com/curtistheconqueror/ai-chess-lounge/pull/36
Source `5277f3fd19a0b6a0f52fb88ce6c8da7abcb16861` was pushed and its GitHub ref
verified exactly. Five additional dashboard checks with explicit single-active-
source assertions also passed. This publication-note commit changes docs only;
full current-head CI remains a separate gate. Retain this contributor branch.

## Current integration checkpoint — October 8, 2026

GitHub `main` is `3b2cb0bd9bf02e130f56d19e6a2995cbf52424dc`. The
stacked PR18–32 chain is in its ancestry, including Stage 7A–7F and the local
Stage 8 assessment/operations/performance/budget-design/beta packet. PR33 and
PR34 then added external pairing instructions, OS trust store support, explicit
pause/end reasons, operator controls and first-visit live spectating. PR34 code
head `de7daa41e51d5be3d2b5d90030b6adf2e896a56f` passed CI run
37461481011 / job 112261864401, including migrations, Python, generated
performance fixtures, SDK, build and browser steps. Its tree is identical to
current `main`; the merge commit has no PR-triggered workflow run. Local
`make test` on that tip passed 382 Python tests (5 environment/engine skips),
3 TypeScript SDK tests, Ruff and web typecheck after excluding this workspace's
injected SOCKS proxy from the test process. Without that adjustment, the SDK TLS
unit test failed during HTTPX construction because optional `socksio` is absent;
the other 381 tests passed. `make build` passed the SDK and web production builds.
Disposable SQLite migration upgraded through `0012_comparison_games`, reported
head, and downgraded to base. No local PostgreSQL or browser executable is
available at this checkpoint; PR34's identical-tree CI ran those gates. The old
sections below are historical checkpoints, not current draft/merge status.

Contributor branch `chore/reconcile-current-main-20261008` starts at that exact
main commit. The previous local branches, the retained remote contributor branches,
and the old divergent local `main` were left untouched. There are no remote
`pickup/stage-7*` or `pickup/stage-8*` branches at the initial check. The immutable
`pickup/stage-7-complete` branch was then created at verified integration merge
`9a262675b124936b5f9b10cfdbb99442da67681e`, which contains the Stage 7A–7F
chain. Do not move it. Stage 8 has no complete hosted-stage pickup; create further
phase completion points only after verifying their exact integrated commits. This
documentation reconciliation is not a new feature or hosted acceptance.

The first-playable local AI-vs-AI/human/Stockfish/BYO experience, Model Lab and
opt-in leaderboards are integrated. Stage 8 hosted identity/isolation (deferred
2E/6D), Supabase project/access, API/WebSocket/queue/engine hosting, production
quotas/budgets, recovery/load acceptance, paid route validation and deployment are
still open. Stage 9's eight candidates remain unselected. Human and bot access
remains free; players fund their own inference, and the owner funds infrastructure.
The October 6 target passed without a hosted release. Next: verify current-main
tests/build and durable pickup evidence, then resolve the concrete account, policy,
runtime, scope and release decisions before hosted integration. No new account,
credential, paid call, access-policy change, deployment or merge was performed here.

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
8E hosted onboarding and 2E/6D identity/release choices remain outstanding. Stage 9
scope is still unselected; October 6 17:40 UTC target preserves integration buffer.

Engine reviewed candidate 2e1996f: 353 Python passed with warnings as errors,
4 local PG-infrastructure skips; complete Ruff format/check passed. Real Stockfish 16
fixture interruption/reap/explicit restart succeeded; artifact is local fixture evidence,
not hosted capacity. Independent review found no remaining material defect in the
corrected lifecycle scope. Publication base is PR27 final docs c2670561a685dc93151ef86ded4269b51cff8b74
(local 70df473 equivalent doc tree); CI 37232631478 is still pending at this update.
New engine source needs its own complete published CI/browser check.

## Stage 8C engine lifecycle verified source checkpoint

Dependent draft PR28:
https://github.com/curtistheconqueror/ai-chess-lounge/pull/28
Source 603c21652e2fa1982a4c2f11c97a31ff831bae45 passed
CI 37233085222 / job 111526705162: 354 Python (3 absent-Stockfish skips),
3 SDK, 34 browser (76 intentional viewport skips), native fixtures/restore,
both migrations and all lint/type/build gates. Artifact 11314985275 retained.
Local 353 Python/4 PG infrastructure skips and 21 focused engine tests passed;
real local Stockfish 16 termination/reap/explicit restart evidence is committed
in docs/verification/stage8c-engine-local.json at source fd0ee8a. CI has no engine;
its skips are not substituted with fake engine performance evidence.
PR27 final docs c267056 passed CI 37232631478. No merge or deployment.

This documentation-only follow-up has a distinct current-head check; verify it
independently before claiming final-head green. Retain all contributor branches;
full 8C hosted/sustained performance and hard process supervision remain open.
The next safe target is the generated loopback transport rehearsal, separate from
in-process overhead and hosted/TLS/proxy/browser measurements. Preserve cleanup
and native/browser/restore gates. Owner account/budget/release decisions and Stage 9
selection remain unanswered; October 6 17:40 UTC target keeps final 8–9-hour buffer.

## Stage 8C loopback transport candidate in progress

Contributor test/stage-8c-loopback-performance is based on PR28 final docs
5f560eaa64679d5ffd0c47a151df0878ddd0b8dd (local 032ff54 equivalent tree).
PR28 source 603c216 passed CI 37233085222; its final docs CI 37233840243 is pending
at this update. Local source 98f86cf adds bounded generated-only loopback TCP across
HTTP/readiness and spectators, four actual idempotent command replays per game,
exact revision/FEN/event continuity/reconnect and owned server/socket/lifespan cleanup.
No provider calls, grants, external endpoint, public exposure, permissions or deployment.

Three focused loopback tests and 16 combined performance tests pass; the default local
100-spectator ramp succeeded. Independent read-only review found no material issue.
Queue/protocol and metric wording were checked against locked dependency source;
actual client receive high-watermark is disclosed, no server inbound-queue/flood or
hard-memory-cap claim. CLI source metadata now marks dirty trees. ADR0032 records
scope. Full current suite/native CI/browser gates and exact clean-source measurement
remain before source acceptance. Retain all branches/drafts; no completed pickup.

Exact next safe target: publish/review full loopback/native acceptance and retained
aggregate evidence, then reconcile the release-readiness packet with the verified
local scope. Actual hosted performance, ownership, account/access/security changes,
monetary enforcement, paid validation, deployment and Stage 9 selection remain external
decision gates. Main remains 087c565. October 6 17:40 UTC target preserves the final
8–9-hour integration buffer and does not waive these decisions or quality gates.

Local loopback reviewed checkpoint b4dab469d808d3626900d303a7acd37b6b88313e:
356 Python passed with warnings as errors (4 local PG-infrastructure skips), full
Ruff format/check passed; actual default SQLite/ASGI/queue/loopback/Stockfish
scenarios all measured successfully. Source tree was clean. Retained loopback
evidence is docs/verification/stage8c-loopback-local.json; no hosted capacity claim.
PR28 final5f560ea independently passed CI 37233840243. Native PostgreSQL
loopback and this contributor's published full/browser CI remain new gates.

## Stage 8C loopback published source verified

Draft PR29: https://github.com/curtistheconqueror/ai-chess-lounge/pull/29
Source e6c2e409189fcdd3f23f62aa9387d9231db58e16 passed CI 37234869427 /
job111531856822:357 Python/3 absent-engine skips,3 SDK,34 browser/76 intentional
viewport skips, SQLite/PostgreSQL migrations, native restore/performance and all
format/lint/type/build gates. Artifact11314774765 was inspected: SQLite/PostgreSQL
loopback scenarios reached32 concurrent HTTP requests and100 spectators, verified
four idempotent replays, persisted position/event continuity, reconnect, zero active
connections and closed owned listener. Desktop/phone metric screenshots inspected.
These are bounded generated measurements, not hosted capacity or a sustained SLA.
Installed Stockfish evidence remains the clean local artifact; CI explicitly skips it.
PR28 final5f560ea passed CI 37233840243 and PR27 finalc267056 passed CI 37232631478.
This documentation follow-up receives its own distinct check; no merge/deployment.

Next safe target: Stage8E preparation-only beta readiness packet, retaining all open
production/account/budget/performance and Stage 9 decisions. Main remains 087c565;
all contributor branches/draft dependencies are preserved. Completed pickup branches
remain gated on approved verified merges. Deadline Oct6 17:40UTC keeps final8–9h
integration/review/CI/restore/visual buffer; external decisions can exceed this window.

## Stage8E preparation packet in progress

Contributor docs/stage-8e-beta-readiness starts from the verified PR29 source plus
its documentation handoff. docs/BETA_READINESS.md separates the local no-credential
reference exhibition, supported connection acceptance, hosted integration sequence,
feedback/incident intake, deferred requirements and all eight unselected Stage 9 areas.
This is preparation only: no hosted beta, new account/access/security/budget change,
paid connection call, deployment or complete Stage8E claim. No runtime behavior changed.

Exact next target after publication/current-head verification: owner decisions in
ACCOUNT_AND_RELEASE_DECISIONS.md and approved integration. Actual 2E/6D ownership,
production operations/remediation, global paid-call enforcement, representative hosted
load and onboarding require those decisions. No independent fixture work is claimed to
replace them. Keep draft/contributor branches; do not merge or deploy without approval.

Published dependent draft PR30:
https://github.com/curtistheconqueror/ai-chess-lounge/pull/30
Preparation source 5a920a46db63dea655a88d62388a3e565cef5e6c; runtime unchanged.
Current-head CI is pending and must be checked independently; no beta completion.
PR29 final documentation4ac5fc3d3862d36fac3e42f88bfdc411c630ed6e likewise has
its separate run37235709129 pending; source run37234869427 remains verified green.
The next genuine dependency is the owner release/account/budget/topology/deferred
scope decision packet. Do not repeat fixture tests or create another monitor as a
substitute for those decisions. Preserve all quality gates and draft pickup branches.

## BYO agent economics clarification in progress

Contributor docs/byo-agent-cost-ownership starts from PR30 final 00c96f4c51d6f9f444ea5ef91f3efeceb868efb8
(local f38eb34 equivalent tree). Final PR30 CI 37235916209 / job 111534858353 passed;
source 5a920a4 passed CI 37235866015. PR29 final 4ac5fc3 passed CI 37235709129.
These supersede historical publication-time pending notes above. Main remains 087c565.

Owner funds Lounge infrastructure; players fund their own agents/API/subscriptions.
No owner-funded shared model key by default. Human/bot Lounge access is free for now.
Supabase is the selected backend direction; account/project/plan/access remain
unverified and no purchase/deployment authorization is inferred. Account/budget/beta/plan docs now distinguish
external inference from Lounge-dispatched player-paid calls and owner compute.
Inspected existing SDK/MCP/bridge and remote adapter: player credentials already stay
local; pairing remains required and match/seat grants unchanged. No duplicate adapter,
monetary prototype, new access control, provider call, merge or deployment.

Removed blocker: funding responsibility ambiguity/owner inference-budget prerequisite
for external BYO routes. Safe next work: verify existing BYO fixture contracts and
publish this narrow documentation checkpoint. Remaining actual choices: hosted route
scope, identity/admin/visibility/invites, Supabase account/project/plan/access,
application runtime host and infrastructure limits/topology,
abuse/request/compute quotas, player paid-call policy if Lounge dispatches, approved
merge/release, purpose/distributed/deferred scope and Stage 9. No blanket stop on safe
work, but no public BYO launch or all-stage completion claimed without these gates.

Existing BYO capability verification: 73 warning-strict tests passed across remote
runner/trust/cleanup, Python SDK, MCP and subscription bridge. No provider request
or new credentials. Exposed tool metadata contains no Supabase capability or tool
search; no account/session probing, login or setup occurred. Claude access is not
evidence of this session access. HOSTED_RELEASE_PATH.md records what is playable,
what is unmerged, real runtime requirements, setup timing and conditional estimates.

Published dependent draft PR31:
https://github.com/curtistheconqueror/ai-chess-lounge/pull/31
Source 678dc6511246bc4ac71d03bed88322a5fa0e8c38; full current-head CI pending.
This pickup follow-up is documentation only and has its own check. Main unchanged;
all contributor branches retained. No completed pickup until approved verified merge.
After this head's check, the next real target is approved Supabase/account/runtime
integration under HOSTED_RELEASE_PATH.md. Safe existing BYO acceptance is verified;
no duplicate adapters or owner inference-budget decision is required. No payment
subsystem is needed for free access. Quota/access/paid-dispatch policies remain open.
Stage9 selection and the Oct6 17:40UTC target with final integration buffer remain.


## Stage 7F AI leaderboards — implementation in progress (2026-10-05 UTC)

Contributor `feat/stage-7f-ai-leaderboards` starts from local PR31-equivalent a4ecd92;
remote PR31 final 293b97664ba5e061d215538a4a1cef9d973a45dc passed CI37240469753.
Main remains 087c565. No merge/deploy/account/credential/paid-call/security approval.
Read STAGE_7F_LEADERBOARDS.md and ADR0033. Preserve this branch and the earlier draft
stack. Parent owns notifications; the hourly monitor remains paused.

Implemented optional identity declarations, additive migration0012, transactional
per-generation snapshots/outcomes and bounded conditions-aware leaderboards. New UI
and tests are in progress. Publication/final acceptance is not yet claimed. Next:
full warning-strict tests, migration/data compatibility, SDK/build, draft publication,
source/final-head PostgreSQL and desktop/phone browser CI, visual inspection and
precise handoff. Routine fixture failures must be fixed before completion claims.
Free human/bot access and BYO inference funding unchanged; no owner directory.
Supabase account/runtime/deferred rollout and Stage9 remain explicit external gates.


### Stage 7F draft PR32 source verified; final follow-up gate

PR32 https://github.com/curtistheconqueror/ai-chess-lounge/pull/32 is Draft, based on
PR31 branch `docs/byo-agent-cost-ownership`. Source remote6ebff8d151d3418701c7a8b2d9ebb134e457543e
passed CI37248389001 / job111570790115: 374 Python tests (3 engine skips), SQLite/PG
migrations, native comparison history/CAS/reset, PG restore14tables/15rows, performance,
3 SDK tests, production build and36 browser passes/79 intentional skips. All33 changed
source files matched local31e8bd0 tree hashes; screenshots reviewed desktop/phone.
This supersedes source-publication pending notes above. Original main remains087c565.

Local follow-up3715269 refreshes UCI engine evidence at reset without rewriting older
identity; 32 targeted tests pass/1PG skip. A bounded real localStockfish16 check confirms
separate1600/2500 rows with null unfinished rates. Mobile cards/readable evidence labels
and retry-independent generated browser fixture IDs are included in the final follow-up.
Engine color-swap cohorts preserve both colors while keeping strength separate;
local serving connectors do not imply underlying providers. Final19 identity tests
pass/1PG skip. Final published-head acceptance must cover these changes: inspect PR32's latest head
and checks; final PR description carries exact final SHA/run/evidence. Publication-time
pending is not a final green claim. Preserve contributor branch; no completed pickup
branch until an approved, verified merge. No credentials/accounts/paid calls/merges,
public deployment or access-policy changes. Monitor remains paused; parent notifies.

Exact next target: finish final-head CI, inspect desktop/phone artifacts and report
verified local7F checkpoint. If acceptance fails, repair within scope and rerun affected
full gates. After verification, remain at hosted decisions in HOSTED_RELEASE_PATH.md:
Supabase account/project/plan/access plus runtime host, identity/visibility/quota policies,
merge/release approval, deferred2E/6D/etc and Stage9 choice. Free human/bot access;
player-funded BYO inference and owner-funded infrastructure unchanged. Added7F work
uses the Oct6 17:40UTC delivery window; do not convert conditional hosted estimates
or integration buffer into an all-stage completion promise.


### Latest checkpoint — Stage 7F local acceptance verified; Draft PR32 retained

Implementation head b95b51f81d50917084d159ddadaa17238f7a13fd passed
CI37249535756 / job111574151986: 377 warning-strict Python tests, 3 unavailable-engine
skips; SQLite/PG upgrades/downgrades; native snapshot/reset/CAS; generated PG restore;
performance fixtures; 3 SDK tests; production web/SDK builds; 36 browser passes and
79 intentional viewport skips. All33 changed files matched local80d4892 blob hashes.
Latest desktop/phone artifacts reviewed; stacked phone cards have no horizontal/page
overflow. The final doc-only checkpoint has its own current-head CI check; fetch PR32's
actual latest SHA/checks and final PR evidence before any integration. Earlier pending
entries above are chronological publication-time notes superseded by these passes.

Local7F candidate is ready in `feat/stage-7f-ai-leaderboards` (Draft PR32, dependent
on PR31). No merge/deployment is claimed and no completed-pickup branch is created
before an approved, verified merge. Schema0012 preserves legacy match/settings data,
adds no fabricated backfill, and keeps history immutable. Unknown/declarations/observed
response labels remain distinct; no invented catalog or universal effort equivalence.
Record cap5000 explicitly exposes truncation; rates are descriptive, not calibrated
Elo/intelligence. Default names/owners/IDs are absent; aliases are opt-in. No owner
directory or public profile is implemented. Free/BYO economics remain unchanged.

Next target after final doc-head verification: wait for authorized hosted/account/
runtime, policy and merge/release decisions under HOSTED_RELEASE_PATH.md, or a new
explicit local feature task. Stage9 selection and deferred2E/6D/etc remain unresolved;
do not resume blocked public setup, spend, fetch credentials, expand permissions or
merge. Parent owns notifications; hourly monitor remains paused. Preserve all drafts
and this contributor branch for pickup. Oct6 17:40UTC remains a conditional delivery
target, not a guaranteed all-stage release; keep integration/test buffer explicit.
