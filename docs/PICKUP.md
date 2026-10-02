# Project pickup checkpoint

This is the first file a new human or agent contributor should read after `AGENTS.md`.
It records the durable handoff state; chat history is never required to resume work.

## Last completed phase

- **Phase:** Stage 3E — open-ecosystem adapters
- **Status:** merged and verified
- **Pull request:** [#7](https://github.com/curtistheconqueror/ai-chess-lounge/pull/7)
- **Merge commit:** `038266a95285028391bbba46b3f663f507929d36`
- **Contributor branch:** `feat/stage-3e-open-ecosystem-adapters` (retained)
- **Pickup branch:** `pickup/stage-3e-complete`
- **CI:** GitHub Actions run `37019352470` passed migration validation, PostgreSQL,
  API tests, web typecheck/build, and responsive Chromium smoke tests.

Stage 3E delivered OpenRouter, Ollama, and vLLM seats, strict structured moves,
honest provider-default effort, safe server-owned endpoint configuration, normalized
usage, and hosted-versus-local setup.

## Current work

- **Phase:** Stage 3F — provider recovery
- **Contributor branch:** `feat/stage-3f-provider-recovery`
- **State:** implementation complete and locally verified; publication/CI pending
- **Target:** add bounded transient provider retries inside the original clock,
  process-local request budgets, outage circuits, sanitized recovery events, public
  reliability status, and an explicit operator retry control.

Provider keys, local base URLs, and local model allowlists remain server-side; no
credential or operator-selected destination belongs in player configuration, events,
browser payloads, commits, or this document.

Local verification passes Ruff format/lint, 122 backend tests with one
environment-specific PostgreSQL skip, SQLite migration upgrade/current/downgrade,
web typecheck and production build, and discovery of all 40 Playwright cases. Local
Chromium execution is unavailable because the Playwright browser binary is not
installed in this workspace; GitHub CI remains the authoritative responsive browser
gate.

## Exact next target

Publish the Stage 3F contributor branch, require green GitHub CI (including the new
recovery browser smoke), squash-merge, retain the contributor branch, and create
immutable `pickup/stage-3f-complete` at the merge commit. Stage 5A remote runner
transport is the next product phase after Stage 3F.

## Pickup branch policy

At every completed phase or stage:

1. Update this document before handoff.
2. Push the contributor branch and preserve it.
3. Merge only after the required checks pass.
4. Create `pickup/<stage-or-phase>-complete` at that merge commit.
5. Never move, force-push, or delete a pickup branch.
