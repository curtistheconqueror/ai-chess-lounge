# ADR 0016: Scoped remote-runner sessions and signed turn relay

- **Status:** Accepted
- **Date:** 2026-10-02
- **Owners:** CurtisTheConqueror

## Context

External agents and subscription-backed bridges must play without browser automation
or per-move approval. The Lounge cannot receive provider keys, subscription cookies,
or broad agent credentials. Remote work can also race a timeout, reset, pause, another
worker, or a duplicated network submission.

## Decision

Use a one-time pairing code to issue a short-lived runner session bound to one public
`PlayerConfiguration.player_id`. Persist only keyed digests of pairing codes and
bearer tokens. Derive a per-session proposal-signing key from an operator-owned server
secret and return it only at claim time.

Deliver the unchanged protocol-v1 `MoveRequest` over authenticated WebSocket, HTTPS
webhook, or HTTP long-poll. Require every returned `MoveProposal` to carry a scoped
idempotency key and an HMAC-SHA256 signature over its canonical delivery payload.
The remote adapter returns the proposal to the existing fenced match runner; it never
updates game state itself.

Outbound webhooks are permitted only for exact operator-allowlisted HTTPS hosts and
never follow redirects. Tokens are accepted only in the `Authorization` header, not
URLs. WebSocket and pull delivery use the same session scope.

## Consequences

- Any independently operated agent can join through a small transport contract while
  keeping its provider authorization local.
- A stolen match link or public player profile cannot authorize moves.
- Duplicate or late remote submissions cannot create duplicate moves because the
  runner signature/idempotency check precedes the existing position and lease fence.
- Operators need a stable `LOUNGE_RUNNER_SECRET` for sessions to survive restarts.
- Pending deliveries and live presence remain process-local until Stage 5E introduces
  distributed coordination and explicit revocation.

## Alternatives considered

- Put provider credentials in the Lounge: rejected because it violates the
  subscription and credential boundary.
- Use MCP tool calls as the unattended transport: rejected because MCP hosts may
  retain per-call approvals.
- Accept unsigned bearer-only proposals: rejected because a proposal should be
  independently bound to its session, delivery, and idempotency key.
- Accept arbitrary callback URLs: rejected because the API would become an SSRF
  primitive.

## Verification

Contract and integration tests prove one-time claim, token expiry, digest-only secret
storage, signature and identity checks, idempotent duplicate handling, callback host
validation, safe public presence, and a remote move committed through the standard
authoritative turn lease.
