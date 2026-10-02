# AI Chess Lounge contributor pickup

Updated: 2026-10-02. Read this file, AGENTS.md, README.md, MASTER_PLAN.md, and ADR 0018.

## Last completed phase — Stage 5D

Stage 5D — authorized subscription CLI bridge — is merged in PR #13:
https://github.com/curtistheconqueror/ai-chess-lounge/pull/13

Verified merge/base: `12255ba8209162af8f78f2124f9d7a1ae23b81d7`.
Immutable checkpoint: `pickup/stage-5d-complete` at that exact merge.
Retained contributor: `feat/stage-5d-subscription-bridge`.
Final published source: `e4a85426c6a8628c8e028502e11a667d403aa312`.
The merge tree matches the locally tested source tree exactly.

Prior baseline: Stage 5C PR #12, merge
`689b0581cc35ac56bd76cb120e46cff1aa0e1aca`; retained checkpoint
`pickup/stage-5c-complete`.

## Shipped

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

After the proxy/classifier fix: 185 local Python tests passed, 1 PostgreSQL
configuration skip; all 31 bridge tests passed. Ruff format/lint, TypeScript
web typecheck, 3 TypeScript runner tests, and production web build passed.
Optional package installation and CLI entry point passed.

Final PR CI run `37071482932`, job `111051703636`: success. It verified
184 Python tests (2 missing-Stockfish skips), PostgreSQL/SQLite migrations,
3 TypeScript tests, web build, and 14 browser tests (36 intentional
viewport-duplicate skips). Local Chromium could not be installed because its
download was truncated; browser acceptance is supplied by green GitHub CI.

Postmerge CI run `37071772590`, job `111052639598`: completed successfully,
including database migrations, Python/TypeScript tests, web build, and responsive
browser smoke tests, on merge `12255ba8209162af8f78f2124f9d7a1ae23b81d7`.

Luna extra-high independently reviewed the bridge and found the final-turn limit
edge case. It is fixed and covered by the two-move-per-side terminal-game test.
The real subscription game also completed on its final authorized turn.

## Current work and exact next target

Stage 5D is complete. No implementation work is in progress in this branch.
Start Stage 5E trust controls from the verified Stage 5D merge:

1. Read this handoff, confirm the base against main, and create a new contributor
   branch. Preserve the completed contributor and immutable pickup branches.
2. Design server-scoped match grants and append-only authorization audit events.
3. Implement limits and explicit revocation/reconnect/forfeit behavior. Existing
   session revoke remains available; the one-match grant is currently enforced
   by the local sidecar rather than a dedicated server-scoped match grant.
4. Add focused authorization/lifecycle regressions and run the relevant tests,
   build, and browser smoke suite before publication and merge.
5. Finish with a new immutable pickup branch and updated contributor handoff.

## Known boundaries

Codex is the first CLI adapter, not a ChatGPT-only architecture. Existing direct
API, OpenRouter, local, human, Stockfish, MCP and external runner paths remain.
Claude third-party subscription product permissions need approval/clarification;
Google consumer CLI subscription login is sunset. Do not implement either by
copying OAuth credentials. Consult the dated official sources in the package README.
Native effort selection is intentionally provider-default until capabilities can
be verified. POSIX only; Windows process-tree cleanup remains unsupported.
Public multiuser deployment/account auth is still deferred to the final stage.
