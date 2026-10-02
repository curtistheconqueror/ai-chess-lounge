# AI Chess Lounge contributor pickup

Updated: 2026-10-02. Read this file, AGENTS.md, README.md, MASTER_PLAN.md, and ADR 0018.

## Last completed phase

Stage 5C — local MCP facade — is merged in PR #12:
https://github.com/curtistheconqueror/ai-chess-lounge/pull/12

Verified merge/base: `689b0581cc35ac56bd76cb120e46cff1aa0e1aca`.
Immutable checkpoint: `pickup/stage-5c-complete` at that merge.
Retained 5C contributor: `feat/stage-5c-mcp-facade` (postmerge handoff at
`c1e8d32f668ddfaa8a00497387f40bd6597c55bc`).

5C PR CI run 37051541641 and postmerge run 37051818985 passed.
Postmerge CI: 148 Python passed, 2 missing-Stockfish skips; 3 TypeScript tests;
web build; 13 browser tests passed, 32 intentional viewport-duplicate skips.
Local 5C Python: 149 passed, 1 PostgreSQL-environment skip.

## Current work — Stage 5D remains IN PROGRESS

Contributor: `feat/stage-5d-subscription-bridge`, based on the verified 5C merge.
Do not create or label a `pickup/stage-5d-complete` branch yet. The required live
subscription game has not passed. Keep this contributor branch for continuation.

Implemented:

- Optional Python local sidecar and `lounge-subscription-bridge doctor/run` CLI.
- Official Codex CLI capability check, sanitized subscription login status,
  explicit next-match grant, exact profile match, bounded turns/time.
- Strict final JSON response, short public summaries, signed runner submissions,
  exact duplicate reuse, process-group timeout/cancellation/output cleanup.
- No OAuth extraction, provider keys, CLI output, or private reasoning sent to the
  Lounge. Child environment excludes provider API keys and Lounge secrets.
- Subscription pairing/UI disclosure: OpenAI, exact model, provider-default
  effort, open_agentic only; independent runner defaults preserved.
- ADR 0018 and package setup/limitations documentation.
- Deterministic two-CLI-fixture game reaches checkmate through the real arbiter;
  subprocess overflow, timeout, cancellation, parsing, scope, and profile tests.

## Live acceptance evidence and concrete blocker

Official Codex CLI 0.160.0 was installed temporarily for capability verification.
Its official login status reported ChatGPT authentication; no credentials were
read or copied. A bounded live game using `gpt-6.1-sol` against a deterministic
opponent produced no model move before the 120-second deadline. One shorter
15-second diagnostic check classified the CLI's stderr as a **usage limit**
(429 / rate-limit category). Raw output was not logged or committed. Stop live
retries until the account/provider limit is resolved. Do not claim model access
or a completed live game from login status alone.

The fake CLI fixture full game is separate evidence; it is not a real model game.
No live acceptance gate has been waived. No automatic API billing fallback exists.

## Verification

Local final gates: 171 Python tests passed, 1 PostgreSQL-environment skip;
3 TypeScript runner tests passed; Ruff format/lint, web typecheck, and production
build passed. Optional package editable install and CLI entry point passed.
Local Playwright could not launch because its Chromium revision was absent;
the official download returned a truncated/invalid archive. Browser results
must be verified by PR CI before merge. PR details and CI results are recorded
in the subsequent contributor handoff update. Run `make test`, `make build`, and
`cd apps/web && npm run e2e` after any changes. PostgreSQL is verified in CI;
local runs may skip it when TEST_POSTGRES_URL is unset.

## Exact next target

1. Review the Stage 5D contributor PR and its CI evidence.
2. On a machine with an eligible official Codex CLI subscription and available
   quota, follow packages/subscription-bridge/README.md. Run doctor, pair a seat,
   then complete an unattended live game after one explicit authorization.
   Record provider/model, CLI version, public PGN/result, and game completion;
   never record credentials or private reasoning.
3. If live acceptance passes, merge the reviewed/green PR, verify postmerge CI,
   create immutable `pickup/stage-5d-complete` at that merge, and update this
   retained contributor handoff with exact commits and verification.
4. Then begin Stage 5E trust controls: server-scoped match grants, audit events,
   limits, revocation/reconnect/forfeit rules. Existing session revoke remains
   available, but the new one-match grant is currently local-sidecar enforcement.

## Known boundaries

Codex is the first CLI adapter, not a ChatGPT-only architecture. Existing direct
API, OpenRouter, local, human, Stockfish, MCP and external runner paths remain.
Claude third-party subscription product permissions need approval/clarification;
Google consumer CLI subscription login is sunset. Do not implement either by
copying OAuth credentials. Consult the dated official sources in the package README.
Native effort selection is intentionally provider-default until capabilities can
be verified. POSIX only; Windows process-tree cleanup remains unsupported.
Public multiuser deployment/account auth is still deferred to the final stage.
