# Project pickup checkpoint

This is the first file a new human or agent contributor should read after `AGENTS.md`.
It records the durable handoff state; chat history is never required to resume work.

## Last completed phase

- **Phase:** Stage 3F — provider recovery
- **Status:** merged and verified
- **Pull request:** [#8](https://github.com/curtistheconqueror/ai-chess-lounge/pull/8)
- **Merge commit:** `67a69052976fcd9e08721ed37cdb28ca4e46cf01`
- **Contributor branch:** `feat/stage-3f-provider-recovery` (retained)
- **Pickup branch:** `pickup/stage-3f-complete`
- **CI:** GitHub Actions run `37023862602` passed migration validation, PostgreSQL,
  122 backend tests with one environment-specific skip, web typecheck/build, and the
  40-case responsive Chromium suite.

Stage 3F delivered bounded transient provider retries inside the authoritative clock,
process-local request budgets, outage circuits, sanitized recovery events, public
reliability status, and an explicit operator retry control.

## Current work

- **Phase:** Stage 5A — remote runner transport
- **Contributor branch:** `feat/stage-5a-remote-runner`
- **State:** implementation complete and locally verified; publication/CI pending
- **Target:** let independently operated agents pair once and play through scoped,
  signed, provider-neutral turns without browser control or provider credentials in
  the Lounge.

Stage 5A adds one-time pairing, digest-only token storage, session expiry and
heartbeat, WebSocket/HTTP turn relay, operator-allowlisted HTTPS webhooks, signed
idempotent proposals, a `remote_runner` adapter, durable pairing/session tables,
public presence, and a polished pairing/seat-selection panel. The remote proposal
still passes through the existing authoritative clock, lease, identity, and legality
fences.

Provider keys, subscription credentials, runner tokens, signing keys, and raw pairing
codes never enter player configuration, match events, exports, commits, or durable
secret columns. Outbound webhook URLs require an exact operator allowlist.

Local verification passes Ruff format/lint, 133 backend tests with one additional
environment-specific PostgreSQL skip, SQLite migration upgrade/current/downgrade,
web typecheck and production build, and discovery of all 45 Playwright cases. Local
Chromium execution remains unavailable because the Playwright browser binary is not
installed in this workspace; GitHub CI is the authoritative responsive browser gate.

## Exact next target

Publish the Stage 5A contributor branch, require green GitHub CI (including the new
remote-pairing browser smoke and PostgreSQL migration), squash-merge, retain the
contributor branch, and create immutable `pickup/stage-5a-complete` at the merge
commit. Stage 5B Python and TypeScript runner SDKs are the next product phase.

## Pickup branch policy

At every completed phase or stage:

1. Update this document before handoff.
2. Push the contributor branch and preserve it.
3. Merge only after the required checks pass.
4. Create `pickup/<stage-or-phase>-complete` at that merge commit.
5. Never move, force-push, or delete a pickup branch.
