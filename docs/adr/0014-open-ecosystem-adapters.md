# ADR 0014: OpenRouter and local model-serving adapters

- **Status:** Accepted
- **Date:** 2026-10-02
- **Owners:** CurtisTheConqueror

## Context

Stage 3E must let a Lounge operator seat models reached through OpenRouter or a local
Ollama/vLLM server without changing match orchestration, accepting a browser-supplied
destination, leaking credentials, or labeling incomparable provider controls as the
same effort setting.

OpenRouter and vLLM expose OpenAI-compatible Chat Completions transports. Ollama has a
native chat transport. Their model catalogs and reasoning controls are not identical,
and neither local server provides one portable effort scale across every model.

## Decision

Implement three adapters behind the existing `PlayerAdapter` protocol:

| Adapter | Transport | Configuration | Effort policy |
| --- | --- | --- | --- |
| OpenRouter | `POST /api/v1/chat/completions` | Server-side bearer key plus allowlisted models | Advertise verified per-model mappings; otherwise send no reasoning control and label provider default |
| Ollama | `POST /api/chat` | Server-side base URL plus explicit installed-model allowlist | Provider default; do not set the model-defined `think` option |
| vLLM | `POST /v1/chat/completions` | Server-side base URL, explicit model allowlist, and optional API token | Provider default until an explicit model mapping is verified |

All three request non-streaming structured JSON containing one UCI move, concise
public plan, concise threat, and confidence. The shared Pydantic model revalidates the
response before the match runner performs identity, version, lease, deadline, and
legality checks. OpenRouter additionally requires routing to an endpoint that supports
the request parameters.

Player configuration may contain only color, output budget, move timeout, and
spectator delay. API keys, base URLs, arbitrary headers, and model-server routing are
server-owned configuration and are rejected from public match payloads.

## Consequences

- Hosted router models and local models can face every existing seat without browser
  automation or per-move permissions.
- Operators can add OpenRouter model IDs without rebuilding the UI. Unknown models
  remain usable, but are not assigned an unverified Lounge effort mapping.
- Ollama and vLLM expose no models until the operator explicitly lists installed IDs.
- The UI reads transport mode and effort choices from adapter capabilities; an empty
  effort list renders `Provider default` and persists `effort: null`.
- Local endpoint security remains an operator responsibility. Defaults are loopback,
  and the Lounge must not turn user input into an outbound destination.
- Bounded paid-provider retry, rate-limit handling, and recovery controls remain Stage
  3F work.

## Verification

Mock transports pin paths, authentication, strict schemas, routing requirements,
effort behavior, usage normalization, health checks, malformed output rejection, and
sanitized failures. Protocol tests reject browser-supplied credentials and endpoints.
Browser automation pins an OpenRouter-versus-Ollama setup with direct/local transport,
verified hosted effort, provider-default local effort, and secret-free payloads.
