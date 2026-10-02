# Project pickup checkpoint

Read this file after `AGENTS.md`. The repository and this handoff are sufficient to
resume without the originating chat. The newest handoff lives on the retained
contributor branch; immutable pickup branches stay at their verified merge.

## Last completed phase

- **Phase:** Stage 5C — provider-neutral local MCP facade
- **Status:** merged; PR and post-merge CI passed
- **Pull request:** [#12](https://github.com/curtistheconqueror/ai-chess-lounge/pull/12)
- **Verified merge:** `689b0581cc35ac56bd76cb120e46cff1aa0e1aca`
- **Retained contributor:** `feat/stage-5c-mcp-facade`
- **Immutable pickup:** `pickup/stage-5c-complete` at that exact merge
- **PR CI:** run `37051541641` passed
- **Post-merge CI:** run `37051818985` passed

## What shipped

`packages/mcp-server` is an optional, installable Python stdio MCP bridge. Any
compatible host can expose join, watch, bounded turn polling, heartbeat, signed
submission, and optional human/remote game creation to its selected model. Resources
provide public game JSON, FEN and PGN. Each process owns one paired runner identity;
credentials stay local. Watch and resources exclude legal-move/engine assistance.
The existing arbiter still controls legality, clocks, leases, and committed moves.

The full-game test caught an existing concurrency issue: snapshot reads waited for
an agent's entire thinking turn. Reads now copy the last locally committed board
while a writer is busy, allowing watch-before-submit without stalling the agent.
Writers still publish only after persistence; read revisions can lag a concurrent
write. The regression fails on the old implementation and passes with the fix.

Read `packages/mcp-server/README.md`, `docs/STAGE_5_EXTERNAL_AGENTS.md`, and
`docs/adr/0017-local-mcp-facade.md` for setup, architecture and boundaries.

## Verification evidence

- Local full suite: **149 passed, one PostgreSQL environment skip**.
- Final CI: **148 Python tests passed, two missing-Stockfish skips**; PostgreSQL
  integration and SQLite/PostgreSQL migration gates passed.
- Nine MCP cases include two independent clients completing checkmate through the
  real API/persistence, read-before-submit, FEN/PGN exports, duplicate/conflicting
  proposals, stale/illegal moves, assistance boundaries, safe errors, and actual
  stdio subprocess discovery.
- Ruff format/lint, editable package installation, installed CLI entry point and
  dependency consistency passed.
- TypeScript SDK build and all **three** contract tests passed in CI.
- Web production build and **13** responsive Chromium tests passed; the matrix
  intentionally skips 32 repeated interactions outside the desktop project.
- Published branch and merged source were compared against the tested local tree;
  no source differences remained. Temporary publication files are absent from the
  final tree. No model-provider calls or subscription charges were needed.

## Exact next target

**Stage 5D — authorized subscription bridge.** Start a fresh
`feat/stage-5d-subscription-bridge` from the verified merge above (or newer verified
main after checking intervening work). No Stage 5D implementation has started.

1. Verify official CLI/SDK authentication and subscription support for the initial
   provider; detect installed capabilities and available models/effort rather than
   assuming support or inventing OAuth routes.
2. Implement a local sidecar using the runner SDK, with explicit one-match operator
   authorization, bounded execution, cancellation and sanitized failure handling.
3. Keep provider credentials exclusively with the official local provider client.
   The Lounge should receive only normalized player configuration and move proposals.
4. Add a deterministic fake-CLI contract suite, then an explicitly authorized live
   smoke game when the required provider login is available. Clearly distinguish
   API-backed, subscription-backed, and local-inference access in UI/status.
5. Require regression/CI gates, retain the contributor branch, merge, and create the
   next immutable pickup with an updated handoff.

Stage 5E follows with revocation, audit events, runner limits and reconnect rules.
Multi-user public hosting remains deferred until ownership/visibility controls.

## Known boundaries

- Packages are in this repository; no PyPI/npm release has been published.
- The bridge is local stdio with a loopback API, not a hosted public MCP endpoint.
- Host permission policy, unattended-loop lifetime, model choice and effort remain
  controlled by the MCP host. The bridge cannot bypass approval prompts or provider
  subscription restrictions. Official subscription adapters are not yet implemented.
- Restarting the bridge requires a new pairing. Delivery/proposal caches are bounded
  and process-local; distributed presence/reconnect durability remains Stage 5E.
- Strategy text is deliberately public commentary, never private chain-of-thought.
- Development deployments remain loopback-only until Stage 2E access controls.
- Browser publication produced remote commit IDs different from local commits.
  Use the verified remote merge above as the base for new work.

## Previous completed checkpoint

Stage 5B SDKs: PR #10, merge `27e6821ed469041f17b4bd74022fcb4a26d39913`,
`pickup/stage-5b-complete`. WebSocket cleanup: PR #11, merge
`df25071881490881cecfea967e2cab689713e741`, `pickup/stage-5b-cleanup-complete`.
Contributor branches `feat/stage-5b-runner-sdk` and `fix/stage-5b-websocket-cleanup`
remain available. Those immutable checkpoints have not been moved.

## Pickup policy

Retain every contributor branch. At each completed phase, create an immutable
`pickup/<phase>-complete` branch at its verified merge and update this document in
the active contributor branch. Never repoint or delete an existing pickup branch.
