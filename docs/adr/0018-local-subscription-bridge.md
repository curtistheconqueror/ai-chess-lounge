# ADR 0018: Local one-match subscription CLI bridge

Status: Accepted; live CLI acceptance passed on 2026-10-02 (see verification/stage5d-live.md).

## Context

The signed runner protocol and local MCP facade already allow independent agents
to play. Subscription access is not interchangeable with an API key and must not
be implemented by copying browser or CLI OAuth tokens into the Lounge backend.
Provider CLI capabilities and product permissions differ and change over time.

## Decision

Add an optional `packages/subscription-bridge` Python sidecar. Its first adapter
invokes the installed official Codex CLI with the player's existing local login.
A required next-match grant binds once to the first delivered match and has
bounded time/turn counts. Reuse the existing runner SDK signing, identity checks,
and idempotent submission. The arbiter remains authoritative.

Pairing profiles distinguish `subscription_bridge` from `remote_runner`, with
OpenAI and an exact operator-selected model, no asserted effort override, and
open_agentic assistance. This is additive to protocol 1.0: the connection mode
already exists in its enum. Existing remote runner defaults do not change.

The child gets only board data, ephemeral working files, and a narrow environment
that retains official auth locations and credential-free outbound proxy routing,
but excludes API keys, credential-bearing proxy URLs, and Lounge secrets.
Use read-only sandbox, forced ChatGPT auth, no user config, disabled shell/web,
no private-reasoning logs, bounded output, deadline and cancellation cleanup.
Reject unknown response fields and malformed moves; never repair with Stockfish.

The bridge does not certify a CLI installation as pure reasoning. CLI defaults,
managed configuration, and future tools require stronger attestation before such
a claim. Subscription account access is not inferred from this ChatGPT session:
preflight uses the official CLI status, and inference establishes model access.

## Consequences

No provider credentials are stored by the backend. No per-move approval is needed
within an explicitly authorized match. All host/provider policies still apply.
The runtime is POSIX-only for reliable process-group cancellation. Native effort
controls, additional subscription providers, server-scoped match grants,
reconnect semantics, and richer trust auditing require subsequent work.

Claude third-party subscription permissions require clarification/approval;
Google consumer CLI subscription login is sunset. Existing API and external
runner paths remain available. See the package README for dated primary sources.
