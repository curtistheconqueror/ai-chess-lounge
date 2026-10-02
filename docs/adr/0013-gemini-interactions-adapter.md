# ADR 0013: Google Gemini Interactions adapter and thinking levels

- **Status:** Accepted
- **Date:** 2026-10-02
- **Owners:** CurtisTheConqueror

## Context

Stage 3D must add Gemini without coupling the match runner to Google-specific
transport, exposing the API key, persisting provider interactions, requesting private
thinking summaries, or pretending every Gemini model supports the same thinking
levels.

## Decision

Implement Google as a direct server-side adapter using the Gemini Interactions API.
Every move request uses `store: false`, `thinking_summaries: none`, and a structured
JSON response format containing one UCI move plus short public plan, threat, and
confidence fields. The provider-compatible schema uses advertised JSON Schema
features; the Lounge then applies the complete shared Pydantic constraints before the
existing runner may commit the proposal.

Thinking support is model-specific:

| Model class | Lounge mapping |
| --- | --- |
| Gemini 3.8 Flash | fast → low, balanced → medium, deep → high |
| Gemini 3.5 Flash and Gemini 3.1 Flash-Lite | fast → minimal, balanced → low, deep → medium, maximum → high |

Unsupported Lounge effort levels are omitted from capabilities and rejected during
configuration validation. They are never silently approximated. Override models with
no explicit verified mapping remain visible but unselectable until their capabilities
are added.

The API key is read only from `GEMINI_API_KEY` in the server environment and sent in
the server-side `x-goog-api-key` header. A `GEMINI_CHESS_MODELS` allowlist override
controls which models the Lounge advertises.

## Consequences

- Gemini, Anthropic, OpenAI, Stockfish, scripted, and human seats use the same lease,
  deadline, legality, persistence, and public-metadata fences.
- Gemini may face any other configured seat without a provider-specific match type.
- Input, output, and thought-token totals normalize into the shared usage object.
- Failed, cancelled, incomplete, malformed, HTTP, and transport responses surface
  sanitized errors rather than provider bodies.
- Paid-provider failures pause after one call. Bounded retry and outage policy remain
  Stage 3F work.
- Subscription-backed Gemini access remains a Stage 5 bridge concern.

## Verification

Mock-transport tests pin the endpoint, API-key header, `store: false`, response
schema, disabled thinking summaries, every model-specific effort mapping, usage
normalization, local validation, sanitized failures, health check, and a complete
fenced manager turn. Browser automation pins catalog-driven Gemini selection,
model-specific effort visibility, Gemini-versus-Anthropic setup, and secret-free
public player settings.
