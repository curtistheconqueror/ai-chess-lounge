# AI Chess Lounge contributor pickup

Updated: 2026-10-04. Read AGENTS.md, README.md, MASTER_PLAN.md and ADR 0021.

## Verified baseline — Stage 6B complete

PR #16: https://github.com/curtistheconqueror/ai-chess-lounge/pull/16
Merged at `655ce42154d59e97dd2d8db9ee0b2e8f0d3f280d`.
Immutable `pickup/stage-6b-complete` points to that exact verified merge.
Retained contributor: `feat/stage-6b-seat-takeover`; this final handoff is a
postmerge documentation commit on that branch. Start new work from the merge/main,
not from the contributor's pre-squash history. Do not repoint the pickup branch.
The prior Stage 6A merge was `ac22b7b5fa7faa5ac6041b1c4a6ca7302597d5c8`.

## Shipped

- Revision-bound, confirmed paused replacement of either human/AI seat and explicit resume.
- Persistent seat history, original/current PGN headers and at-ply annotations; migration 0008.
- Position/version/revision and lease fencing, including late old runner trust failures.
- Remote runner can return to its original seat with unchanged authorization budget/expiry.
- Player cards reset strategy/usage attribution at takeover; desktop/phone acceptance added.
- ADR 0021 and STAGE_6_HUMAN_PLAY.md describe contracts and scope.

## Verification

Published source `7efda78ae1647fc75f365ff44702c901f18942da` matches locally tested
commit `a0e1d16` exactly by tree diff; the merge has that identical tree.
Local make test/build and final pytest -W error passed: 215 Python tests,
2 environment/engine skips, 3 SDK tests, Ruff format/lint and web typecheck.
PR CI 37183260435 / job 111379904579 passed all gates, including SQLite and PostgreSQL
migration upgrade/downgrade and 23 browser tests (57 intentional duplicate-viewport skips).
Inspected the desktop and phone takeover screenshots: board, controls and history fit.
Independent backend review found a wrapped stale runner error escaping as a task
exception; CAS recovery was fixed and a real delayed-reservation regression added.
Local Chromium is absent; browser acceptance executed in CI.
Postmerge CI 37183451633 / job 111380466496 passed all gates as the final smoke run.

## Exact next target — Stage 6C consultation

Build an explicit human consultation request and suggestion card. Only the human
can submit the final move; a suggestion must never mutate the board automatically.
Bind requests/results to match, human seat, position version and revision. Reuse
adapter capability validation, public strategy summaries, provider limits and
cancellation; fence stale results after moves, reset, takeover and terminal actions.
Record disclosed assistance and usage without private reasoning or credentials.
Add targeted backend and desktop/phone acceptance; preserve a contributor branch
and create pickup/stage-6c-complete only after green CI and verified merge.

Stage 6 has four phases (6A–6D). 6A and 6B are complete; 6C is next. Multiuser
ownership/invitations in 6D remain final account/deployment work per owner direction.

## Boundaries

Loopback operator only; no account identity or seat ownership yet. No live provider
credits were needed for this phase. Handoffs are exhibitions and remain paused until
explicitly resumed. Runner grants do not transfer seats, reset, renew or expand.
Distributed runner delivery routing and negotiated draw offers remain deferred.
