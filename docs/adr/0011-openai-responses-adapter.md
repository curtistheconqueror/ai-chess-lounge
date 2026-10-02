# ADR 0011: OpenAI Responses adapter and credential boundary

- **Status:** Accepted
- **Date:** 2026-10-01
- **Owners:** CurtisTheConqueror

## Context

Stage 3A established a provider-neutral player contract and fenced unattended turn
runner. The first hosted provider must prove that a live model can occupy either seat
without browser control, while keeping credentials and private model reasoning out of
match data and preserving honest model/effort disclosure.

## Decision

Implement OpenAI as a direct server-side adapter using the Responses API. The adapter
sends a strict JSON Schema response format containing only one UCI move and short,
public-facing plan, threat, and confidence fields. It sends `store: false`, does not
request private chain-of-thought, and normalizes only token counts into common move
metadata.

The Lounge effort vocabulary maps explicitly to provider values:

| Lounge | OpenAI |
| --- | --- |
| `fast` | `low` |
| `balanced` | `medium` |
| `deep` | `high` |
| `maximum` | `max` |

The API key is read only from the server environment. Browser and game-creation
payloads carry provider, model, effort, division, timeout, and spectator delay, but no
credential or credential reference. Models are selected from a server allowlist with
environment override; the UI consumes the adapter capability catalog rather than
hard-coding availability.

## Consequences

- OpenAI-versus-OpenAI, OpenAI-versus-Stockfish, and human-versus-OpenAI use the same
  match runner and server-authoritative legality checks.
- API failures expose a sanitized status or exception type, never raw provider bodies.
- Paid-provider failures pause the match after one attempted call. Bounded,
  status-aware provider retries are deferred to Stage 3F.
- Once a direct provider call starts, later lease or persistence failures do not
  dispatch another paid call for that position; the match pauses for recovery.
- Default development servers and Compose publishing bind to loopback. Public hosting
  requires the authentication and quota controls planned for Stage 2E.
- Cost remains `null` until a versioned pricing registry can identify model price at
  match time without silently applying stale prices.
- Bounded retries, provider-specific rate-limit handling, and outage adjudication
  remain Stage 3F work.
- Subscription-backed OpenAI access remains a Stage 5 local bridge concern and is not
  represented as direct API access.

## Verification

Mock-transport tests pin the structured request, privacy flag, effort mapping, usage
normalization, malformed/refused output behavior, error sanitization, and a complete
fenced manager turn. UI automation pins catalog-driven model/effort selection and the
absence of credentials from both seat payloads.
