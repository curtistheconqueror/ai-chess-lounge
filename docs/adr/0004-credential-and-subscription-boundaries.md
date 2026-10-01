# ADR 0004: Credential and subscription boundaries

- **Status:** Accepted
- **Date:** 2026-09-30
- **Owners:** CurtisTheConqueror

## Context

Direct APIs use provider keys, while subscription-backed agents may authenticate
through officially supported desktop, CLI, or SDK routes. Moving subscription tokens
to a hosted server would create unnecessary risk and may violate provider rules.
MCP hosts may also require approval for individual tool calls.

## Decision

Direct API credentials use encrypted bring-your-own-key storage or a server-owned key
with explicit quotas. Subscription credentials remain on the user's machine inside a
local subscription bridge. The bridge receives a short-lived Lounge runner token
scoped to one agent and authorized matches; it never sends provider credentials to
the Lounge.

Subscription adapters are implemented only when the provider officially supports an
automation/authentication route. MCP is supported as a compatibility facade, while an
event-driven remote runner protocol handles unattended turns.

## Consequences

- Subscription play requires a local process and clear connection health UI.
- Each provider route must be capability-detected and independently maintained.
- The hosted service carries less credential risk.
- “Any subscription” cannot be promised when a provider offers no supported route.

## Alternatives considered

- Browser control: rejected as the primary transport because it is slow, brittle,
  visually coupled, and prone to per-action approval.
- Upload provider session cookies: rejected for security and policy reasons.
- MCP-only unattended play: rejected because host approval behavior is not controlled
  by the Lounge.

## Verification

Security tests must show that revoking or expiring a runner token immediately blocks
move submission and that no provider credential appears in network payloads, logs,
events, exports, or database records outside the designated secret store.
