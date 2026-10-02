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

## Current work — Stage 5D live gate passed; merge verification pending

Contributor: `feat/stage-5d-subscription-bridge`, based on the verified 5C merge.
PR #13: https://github.com/curtistheconqueror/ai-chess-lounge/pull/13
Published implementation: `d116e5399fc1d3e642c8e620348dc8814c8b23c4`.
Reviewed source checkpoint (includes final-turn fix and regression):
`6fbf562172b43ef81bb6afe9e196d7eeeaa60c43`.
The live-game gate has passed. Finish updated-head CI and merge verification,
then create `pickup/stage-5d-complete` at the verified merge. Keep this contributor
branch after merge.

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

## Live acceptance passed — previous diagnosis corrected

The user authorized a fresh retry on 2026-10-02. A 120-second retry showed
connection/reconnect failures, with no explicit HTTP 429 or quota message.
The previous classifier matched bare digits and was too broad; the earlier
claim of a usage-limit blocker is superseded.

Root cause: the child environment removed the hosted runtime's required outbound
proxy routing. Preserving existing credential-free HTTP(S) proxy URLs fixed the
connection. Credential-bearing URLs and API keys remain excluded. Diagnostic
classification now requires contextual status codes and distinguishes explicit
quota errors from rate limiting and transport failures.

A live official Codex CLI 0.160.0 / gpt-6.1-sol subscription game then completed
unattended after one grant: `1. f3 e5 2. g4 Qh4# 0-1`. The real CLI played Black
against a declared deterministic opponent. Both proposals traversed the signed
runner protocol and real arbiter. No provider credentials or raw reasoning were
read, copied, or retained. Full evidence and public PGN are in
`docs/verification/stage5d-live.md` and `stage5d-live.pgn`.

## Verification

After the proxy/classifier fix: 185 Python tests passed, 1 PostgreSQL-environment skip;
3 TypeScript runner tests passed; Ruff format/lint, web typecheck, and production
build passed. Optional package editable install and CLI entry point passed.
Local Playwright could not launch because its Chromium revision was absent;
the official download returned a truncated/invalid archive. Browser results
were verified by PR CI run `37066364849`, job `111035002777`, which passed:
170 Python tests, 2 missing-Stockfish skips; PostgreSQL and SQLite migrations;
3 TypeScript tests; production build; 14 browser tests passed and 36 intentional
viewport-duplicate skips.

Luna extra-high independently reviewed the bridge and found the final-turn limit
edge case. It is fixed, with the full fake-CLI game now constrained to exactly
two moves per side. All 31 bridge tests and Ruff passed after the proxy/classifier regressions. Updated
PR CI must remain green at its current head; consult PR #13 Checks. Run `make test`, `make build`, and
`cd apps/web && npm run e2e` after any changes. PostgreSQL is verified in CI;
local runs may skip it when TEST_POSTGRES_URL is unset.

## Exact next target

1. Verify CI on the current PR #13 head containing the proxy/classifier fixes.
2. Mark the PR ready, merge, verify postmerge CI, and create the immutable
   `pickup/stage-5d-complete` branch at that merge commit.
3. Update this retained contributor handoff with merge/CI/checkpoint evidence.
4. Begin Stage 5E trust controls: server-scoped match grants, audit events,
   limits, revocation/reconnect/forfeit rules. Existing session revoke remains
   available, but the one-match grant is currently local-sidecar enforcement.

## Known boundaries

Codex is the first CLI adapter, not a ChatGPT-only architecture. Existing direct
API, OpenRouter, local, human, Stockfish, MCP and external runner paths remain.
Claude third-party subscription product permissions need approval/clarification;
Google consumer CLI subscription login is sunset. Do not implement either by
copying OAuth credentials. Consult the dated official sources in the package README.
Native effort selection is intentionally provider-default until capabilities can
be verified. POSIX only; Windows process-tree cleanup remains unsupported.
Public multiuser deployment/account auth is still deferred to the final stage.
