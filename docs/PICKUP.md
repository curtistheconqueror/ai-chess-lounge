# Project pickup checkpoint

This is the first file a new human or agent contributor should read after `AGENTS.md`.
It records the durable handoff state; chat history is never required to resume work.

## Last completed phase

- **Phase:** Stage 5A — remote runner transport
- **Status:** merged and verified
- **Pull request:** [#9](https://github.com/curtistheconqueror/ai-chess-lounge/pull/9)
- **Merge commit:** `07b7c1239ea1b53a55581cc61513d9fcc9cc09be`
- **Contributor branch:** `feat/stage-5a-remote-runner` (retained)
- **Pickup branch:** `pickup/stage-5a-complete`
- **CI:** GitHub Actions run `37029615313` passed SQLite and PostgreSQL migration
  validation, 133 backend tests with one environment-specific skip, web
  typecheck/build, and the 45-case responsive Chromium suite.

Stage 5A delivered one-time pairing, digest-only token storage, scoped session expiry
and heartbeat, WebSocket/HTTP turn relay, operator-allowlisted HTTPS webhooks, signed
idempotent proposals, durable pairing/session tables, public presence, and UI
pairing/seat selection. The remote proposal still passes through the authoritative
clock, lease, identity, and legality fences.

## Current work

- **Phase:** Stage 5B — runner SDKs
- **Contributor branch:** `feat/stage-5b-runner-sdk`
- **State:** implementation complete and locally verified; publication/CI pending
- **Target:** give Python and TypeScript agents a supported one-handler path from a
  one-time pairing to unattended, signed, provider-neutral chess turns.

Stage 5B adds separately packageable Python and TypeScript clients with pairing,
heartbeat, authenticated HTTP long-poll, request-bound proposal builders,
cross-language canonical HMAC signing, and same-payload idempotent submission retry.
Both packages reject plaintext non-loopback servers and include a deterministic Legal
Assist sample bot. CI now verifies both SDK packages alongside the API and web app.

Provider keys, subscription credentials, runner tokens, signing keys, and raw pairing
codes never enter player configuration, match events, exports, commits, or durable
secret columns. Outbound webhook URLs require an exact operator allowlist.

Local verification passes Ruff format/lint across the API and Python SDK; 138 tests
pass with one environment-specific PostgreSQL skip; the TypeScript SDK compiles and
passes three Node contract tests; both packages build; the web production build
passes; the SQLite migration upgrades, downgrades, and re-upgrades; and all 45
Playwright cases are discovered. Local Chromium execution remains unavailable because
the Playwright browser binary is not installed in this workspace; GitHub CI is the
authoritative responsive browser gate.

## Exact next target

Publish the Stage 5B contributor branch, require green GitHub CI (including both SDK
contract suites and the existing PostgreSQL/browser gates), squash-merge, retain the
contributor branch, and create immutable `pickup/stage-5b-complete` at the merge
commit. Stage 5C MCP facade is the next product phase.

## Pickup branch policy

At every completed phase or stage:

1. Update this document before handoff.
2. Push the contributor branch and preserve it.
3. Merge only after the required checks pass.
4. Create `pickup/<stage-or-phase>-complete` at that merge commit.
5. Never move, force-push, or delete a pickup branch.
