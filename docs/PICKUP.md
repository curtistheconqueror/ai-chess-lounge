# AI Chess Lounge contributor pickup

Updated: 2026-10-04. Read AGENTS.md, README.md, MASTER_PLAN.md and ADR 0020.

## Verified baseline

Stage 5E merged as PR #14 at `59e9a7a360b55d251871a9f168bab62e277874e2`.
Immutable `pickup/stage-5e-complete` and retained `feat/stage-5e-trust-controls`
remain. PR CI 37152054950 and postmerge CI 37152192013 passed.

## Current work — Stage 6A

Contributor: `feat/stage-6a-human-controls`, created from the exact merge above.
Implementation is ready for PR/CI; do not mark complete until merge and checkpoint.

- Explicit human-color resignation, confirmation, stale-version rejection and clock settlement.
- Durable threefold/fifty-move claims, including announced intended moves without a phantom ply.
- Desktop drag, phone tap, both-color promotion, stale dialog/drag fencing and reconnect input guard.
- Migration 0007, domain/API/store tests, desktop/phone browser acceptance.
- Reproduced and fixed repeated native task cancellation leaking a checked-out database
  connection in runner WebSocket cleanup. Regression uses an actual database session.
- ADR 0020 and STAGE_6_HUMAN_PLAY.md describe API behavior and boundaries.

## Verification and remaining gates

Local `make test`: 205 Python passed, 2 PostgreSQL-environment skips; Ruff format/lint,
3 TypeScript SDK tests and web typecheck passed. `make build` passed. Full pytest
with all warnings treated as errors also passed (205/2). Independent backend review
found no correctness issues; migration 0007 upgrade/downgrade is covered.
CI evidence will be filled in after publication. Local browser smoke
cannot launch because Chromium is absent; CI must run the full browser suite before
merge. Independently review terminal action races and preserve the tested tree.

## Next target

After Stage 6A merge, create immutable `pickup/stage-6a-complete` at the verified
merge, retain this contributor branch and update this handoff with CI evidence.
Then Stage 6B: explicit pause-safe AI/human takeover, persisted seat changes,
immutable events and stale proposal fencing. Stage 6C adds human consultation.
Multiuser ownership/invitations remain at the final deployment stage.

## Boundaries

Loopback operator only. Draw claims are supported; negotiated draw offers and agent
acceptance are deferred. Legacy bodyless resign infers a human seat; new UI always
sends explicit color/version. Clocks continue in dialogs. Runner grants remain bound
to one match/seat/generation and distributed delivery routing remains deferred.
