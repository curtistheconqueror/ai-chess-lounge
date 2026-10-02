# Project pickup checkpoint

Read this file after `AGENTS.md`. It records the durable handoff; the originating
chat and local worktree are not required.

## Last completed phase

- **Phase:** Stage 5B — Python and TypeScript remote-runner SDKs, with WebSocket shutdown correction
- **Status:** merged and verified
- **SDK PR:** [#10](https://github.com/curtistheconqueror/ai-chess-lounge/pull/10)
- **SDK merge:** `27e6821ed469041f17b4bd74022fcb4a26d39913`
- **Correction PR:** [#11](https://github.com/curtistheconqueror/ai-chess-lounge/pull/11)
- **Latest verified merge:** `df25071881490881cecfea967e2cab689713e741`
- **Retained contributors:** `feat/stage-5b-runner-sdk`, `fix/stage-5b-websocket-cleanup`
- **Original immutable pickup:** `pickup/stage-5b-complete` at the SDK merge above
- **Recommended immutable pickup:** `pickup/stage-5b-cleanup-complete` at the correction merge above

Stage 5B adds separately packageable Python and TypeScript clients for pairing,
heartbeat, authenticated HTTP long-polling, bound proposal builders, cross-language
canonical HMAC signing, and same-payload idempotent submission retries. Both reject
plaintext non-loopback servers and include a deterministic Legal Assist sample bot.
Agents replace one move handler to supply their own model or inference connection.

The post-merge run for PR #10 caught intermittent WebSocket cancellation cleanup.
PR #11 cancels and awaits both child tasks even when the connection is cancelled,
shields cleanup from repeated ASGI cancellation, and always clears connected presence.
The cancellation regression fails on the previous implementation and passes with the
fix; the exact heartbeat/disconnect case passed 20 independent local runs.

## Verification evidence

- SDK PR CI: run `37035465208`, passed.
- Correction PR CI: run `37036887876`, passed.
- Correction post-merge CI: run `37037347924`, passed.
- Final CI: 139 Python tests passed; two engine tests skipped because the hosted
  runner has no Stockfish binary. PostgreSQL integration and both database migration
  gates passed.
- TypeScript SDK: build and all three contract tests passed.
- Web: production build and 13 Chromium tests passed. The 45-case project matrix
  intentionally skips 32 repeated interaction cases outside the desktop project;
  these are not 45 executed tests.
- Local SDK verification also built the Python wheel, checked npm packaging, and
  passed lint/format and the SQLite migration round trip.

## Current work and exact next target

Stage 5C — MCP facade is implemented on `feat/stage-5c-mcp-facade`, based on
verified remote main `df25071881490881cecfea967e2cab689713e741`. Publication and
merge verification are in progress; do not treat this as a completed checkpoint.

It adds an optional local stdio package with join/watch/poll/submit/heartbeat tools,
opt-in human/remote game creation, snapshot/FEN/PGN resources, safe credential
handling, bounded delivery caching, and deterministic two-client full-game tests.
Read `packages/mcp-server/README.md` and ADR 0017 for setup and boundaries.

Next: require green CI, merge, retain the contributor branch, and create immutable
`pickup/stage-5c-complete` at the verified merge. Record exact evidence here.

Stage 5D follows with the authorized subscription sidecar and official provider
CLI/SDK bridges. Stage 5E adds revocation, audit events, runner limits, and reconnect
rules. Multi-user public hosting remains deferred until ownership/visibility controls.

## Known boundaries

- SDK packages are in the repository, not published to PyPI/npm registries.
- The SDK sample chooses the first legal move; it is not an LLM strength benchmark.
- Subscription authorization and MCP host approval policies are not implemented by
  the SDK itself.
- App deployment remains loopback-only until Stage 2E access controls are implemented.
- Pending runner delivery/presence is process-local until Stage 5E.
- The original Stage 5B pickup remains unchanged; use the cleanup pickup for new work.
- Local commits were published through GitHub UI and have different IDs from the
  remote commits. Use the remote merge SHA above as the contributor base.

## Pickup policy

Retain every contributor branch. At each completed phase, create an immutable
`pickup/<phase>-complete` branch at its verified merge and update this document in
the active contributor branch. Never repoint or delete an existing pickup branch.
