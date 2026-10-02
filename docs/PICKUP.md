# Project pickup checkpoint

This is the first file a new human or agent contributor should read after `AGENTS.md`.
It records the durable handoff state; chat history is never required to resume work.

## Last completed phase

- **Phase:** Stage 3C — Anthropic Messages adapter
- **Status:** merged and verified
- **Pull request:** [#5](https://github.com/curtistheconqueror/ai-chess-lounge/pull/5)
- **Merge commit:** `35bc08d5d6b0c3f4d5d895a31dba5a09a0ad3362`
- **Contributor branch:** `feat/stage-3c-anthropic-adapter` (retained)
- **Pickup branch:** `pickup/stage-3c-complete`
- **CI:** GitHub Actions run `36966904954` passed migration validation, PostgreSQL,
  API tests, web typecheck/build, and responsive Chromium smoke tests.

Stage 3C delivered direct Claude seats, adaptive-effort mapping, strict local move
validation, normalized usage, sanitized failures, and Claude-versus-OpenAI setup.

## Current work

- **Phase:** Stage 3D — Google Gemini adapter
- **Contributor branch:** `feat/stage-3d-gemini-adapter`
- **State:** implementation complete and locally verified; publication/CI pending
- **Target:** add a server-side Gemini Interactions adapter, model-specific thinking
  levels, normalized usage, catalog-driven Gemini UI selection, cross-provider
  browser coverage, and architecture documentation.

The Gemini API key remains server-side in `GEMINI_API_KEY`; no credential belongs in
player configuration, events, browser payloads, commits, or this document.

Local verification passed Ruff format/lint, 101 backend tests with one environment-
specific skip, the production web build, and discovery of all 30 Playwright cases.
Local Chromium execution is unavailable because this workspace cannot download the
Playwright browser archive; GitHub CI is the authoritative responsive browser gate.

## Exact next target

Complete the Stage 3D full test matrix, publish the contributor branch, open a pull
request, require green GitHub CI, squash-merge, retain the contributor branch, and
create immutable `pickup/stage-3d-complete` at the merge commit. Stage 3E then adds
OpenRouter/OpenAI-compatible and local Ollama/vLLM adapters.

## Pickup branch policy

At every completed phase or stage:

1. Update this document before handoff.
2. Push the contributor branch and preserve it.
3. Merge only after the required checks pass.
4. Create `pickup/<stage-or-phase>-complete` at that merge commit.
5. Never move, force-push, or delete a pickup branch.
