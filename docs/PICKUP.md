# Project pickup checkpoint

This is the first file a new human or agent contributor should read after `AGENTS.md`.
It records the durable handoff state; chat history is never required to resume work.

## Last completed phase

- **Phase:** Stage 3D — Google Gemini Interactions adapter
- **Status:** merged and verified
- **Pull request:** [#6](https://github.com/curtistheconqueror/ai-chess-lounge/pull/6)
- **Merge commit:** `c8151d1e3cbc5e1c5a34f4608fedb3c0928beeed`
- **Contributor branch:** `feat/stage-3d-gemini-adapter` (retained)
- **Pickup branch:** `pickup/stage-3d-complete`
- **CI:** GitHub Actions run `36973770292` passed migration validation, PostgreSQL,
  API tests, web typecheck/build, and responsive Chromium smoke tests.

Stage 3D delivered direct Gemini seats, model-specific thinking-level mapping,
strict local move validation, normalized usage, sanitized failures, and
Gemini-versus-Claude setup.

## Current work

- **Phase:** Stage 3E — open-ecosystem adapters
- **Contributor branch:** `feat/stage-3e-open-ecosystem-adapters`
- **State:** implementation complete and locally verified; publication/CI pending
- **Target:** add server-side OpenRouter Chat Completions, native Ollama, and
  OpenAI-compatible vLLM adapters; honest provider-default effort for unmapped local
  models; catalog-driven hosted-versus-local UI selection; and contract/browser
  coverage.

Provider keys, local base URLs, and local model allowlists remain server-side; no
credential or operator-selected destination belongs in player configuration, events,
browser payloads, commits, or this document.

Local verification passed Ruff format/lint, 116 backend tests with one
environment-specific PostgreSQL skip, web typecheck and production build, and
discovery of all 35 Playwright cases. Local Chromium execution is unavailable because
the Playwright browser binary is not installed in this workspace; GitHub CI remains
the authoritative responsive browser gate.

## Exact next target

Complete the Stage 3E test matrix, publish the contributor branch, open a pull request,
require green GitHub CI, squash-merge, retain the contributor branch, and create
immutable `pickup/stage-3e-complete` at the merge commit. Stage 3F then adds bounded
provider retries, rate limits, outage policy, and operator-facing recovery controls.

## Pickup branch policy

At every completed phase or stage:

1. Update this document before handoff.
2. Push the contributor branch and preserve it.
3. Merge only after the required checks pass.
4. Create `pickup/<stage-or-phase>-complete` at that merge commit.
5. Never move, force-push, or delete a pickup branch.
