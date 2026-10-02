# ADR 0012: Anthropic Messages adapter and adaptive effort

- **Status:** Accepted
- **Date:** 2026-10-02
- **Owners:** CurtisTheConqueror

## Context

Stage 3B proved the first live hosted-provider seat without browser control. Stage 3C
must add Claude without coupling the match runner to Anthropic-specific request or
response shapes, exposing credentials to the browser, or claiming unsupported
thinking controls for current models.

## Decision

Implement Anthropic as a direct server-side adapter using the Messages API. The
adapter sends an Anthropic-compatible JSON Schema for one UCI move plus short public
plan, threat, and confidence fields, then validates the returned text locally against
the complete shared contract before the existing runner considers the move. Provider-
unsupported string-length and numeric constraints stay in that local validation
rather than causing a live request rejection.

Current built-in Claude models use adaptive thinking. The request therefore omits the
legacy manual `thinking` budget and maps the Lounge effort vocabulary explicitly:

| Lounge | Anthropic |
| --- | --- |
| `fast` | `low` |
| `balanced` | `medium` |
| `deep` | `high` |
| `maximum` | `max` |

The API key is read only from `ANTHROPIC_API_KEY` in the server environment. The
browser receives capability and availability metadata, never the credential. A
server allowlist with `ANTHROPIC_CHESS_MODELS` override controls which effort-capable
models appear in the UI.

## Consequences

- Anthropic, OpenAI, Stockfish, scripted, and human seats share the same position,
  lease, deadline, legality, persistence, and public-metadata fences.
- A Claude seat and an OpenAI seat can be selected together without a provider-
  specific match type.
- Refusals, incomplete output, malformed structured data, HTTP failures, and transport
  errors expose sanitized messages instead of raw provider response bodies.
- Input and output token counts normalize into the common usage object. A separate
  reasoning-token count remains `null` because the Messages response does not expose
  one independently.
- Paid-provider failures still pause after one call. Bounded retry and outage policy
  remain Stage 3F work.
- Subscription-backed Claude access remains a Stage 5 local bridge concern and is
  not represented as direct API access.

## Verification

Mock-transport tests pin the URL, version and API-key headers, structured-output
schema, absence of a manual thinking field, every effort mapping, usage normalization,
refusal and malformed-output behavior, sanitized errors, health check, and a complete
fenced manager turn. Browser automation pins a secret-free Anthropic-versus-OpenAI
setup payload and catalog-driven model and effort selection.
