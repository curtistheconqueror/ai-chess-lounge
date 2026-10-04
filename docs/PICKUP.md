# AI Chess Lounge contributor pickup

Updated: 2026-10-04. Read AGENTS.md, README.md, MASTER_PLAN.md and ADR 0021.

## Verified baseline

Stage 6A merged as PR #15 at `ac22b7b5fa7faa5ac6041b1c4a6ca7302597d5c8`.
Immutable `pickup/stage-6a-complete` and retained `feat/stage-6a-human-controls`
remain. Final PR CI 37176580915 and postmerge CI 37176717656 passed, including
207 Python tests, 3 SDK tests and 20 browser tests (50 duplicate-viewport skips).

## Current work — Stage 6B

Contributor: `feat/stage-6b-seat-takeover`, created from the exact merge above.
Implementation complete; publication and CI gates are in progress. Do not mark
complete until merge and the immutable pickup checkpoint are verified.

- Revision-bound, confirmed paused replacement of either human/AI seat and explicit resume.
- Persistent seat history, original/current PGN headers and at-ply annotations; migration 0008.
- Position/version/revision and lease fencing, including late old runner trust failures.
- Remote runner can return to its original seat with unchanged authorization budget/expiry.
- Player cards reset strategy/usage attribution at takeover; desktop/phone acceptance added.
- ADR 0021 and STAGE_6_HUMAN_PLAY.md describe contracts and scope.

## Verification and remaining gates

Local make test passes; final pytest -W error passes 215 Python tests, with 2
environment/engine skips. Also passed: 3 SDK tests,
Ruff format/lint and web typecheck. Targeted takeover tests cover stale requests,
concurrent writes, old results/errors, restart/clock/PGN and runner grant retention.
Migration upgrade/downgrade includes 0008. Production build passed. Independent
review found a wrapped stale runner error escaping as a task exception; fixed the
CAS recovery and added real delayed-reservation coverage. Exact-head CI (including
PostgreSQL and desktop/phone browser smoke) is the remaining gate.
Local Chromium is absent; browser execution is required in CI before merge.

## Next target

Merge Stage 6B after green gates, create immutable pickup/stage-6b-complete at the
verified merge, retain this contributor branch and update this handoff with evidence.
Then Stage 6C: human consultation suggestions, with only the human submitting a move.
Stage 6 has four phases (6A–6D); multiuser ownership/invitations in 6D remain final
account/deployment work per owner direction.

## Boundaries

Loopback operator only; no account identity or seat ownership yet. No live provider
credits are needed for this phase. Handoffs are exhibitions and remain paused until
explicitly resumed. Runner grants do not transfer seats, reset, renew or expand.
Distributed runner delivery routing and negotiated draw offers remain deferred.
