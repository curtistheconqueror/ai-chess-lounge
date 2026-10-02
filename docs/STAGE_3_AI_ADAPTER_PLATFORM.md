# Stage 3 — AI Adapter Platform

## Stage 3A outcome

The Lounge now has a credential-free, provider-neutral two-seat automation core.
Human, deterministic scripted, and Stockfish players are represented by the same
persisted `PlayerConfiguration`; either color can be automated, and two automated
seats advance without browser control or per-move approval.

| Capability | Current delivery |
| --- | --- |
| Versioned protocol | `MoveRequest` and `MoveProposal` v1.0 bind every proposal to request, match, and position identifiers |
| Adapter SDK | Registry plus model listing, capabilities, validation, move selection, usage normalization, and health contract |
| Reference adapters | Deterministic scripted adapter and Stockfish adapter use the same match-facing interface |
| Unattended runner | The current automated seat acquires a durable fenced lease, computes outside a database transaction, and commits only a current legal proposal |
| Clock/lease safety | Calls are bounded by the active server clock; long calls renew leases and stale or canceled work cannot commit |
| Public metadata | Safe plan, threat, confidence, latency, normalized usage, provider, model, effort, and division data persist with accepted moves |
| Match setup | The Lounge can select Human, Stockfish, or Deterministic Agent independently for White and Black |
| Compatibility | Legacy `opponent`, engine summary, human-vs-Stockfish requests, snapshots, and PGN behavior remain readable |

## Stage 3B outcome

The first hosted-provider path uses the OpenAI Responses API behind the same adapter
contract. Either seat may select an enabled OpenAI model and Lounge effort; the match
runner applies its existing deadline, lease, position-version, and legality fences.

| Capability | Stage 3B delivery |
| --- | --- |
| Provider transport | Direct server-side `POST /v1/responses`; provider code remains isolated in `openai_adapter.py` |
| Structured proposal | Strict JSON Schema for UCI move, concise public plan, concise threat, and optional confidence, followed by local Pydantic validation |
| API storage setting | Every move sends `store: false`; the Lounge does not persist raw prompts, responses, or private reasoning or return them to the browser |
| Effort mapping | Lounge `fast`, `balanced`, `deep`, and `maximum` map to OpenAI `low`, `medium`, `high`, and `max` |
| Usage | Input, output, and reasoning tokens normalize into the common move metadata; cost stays unset until the versioned pricing registry is added |
| Model policy | Current server allowlist has documented defaults and can be replaced with `OPENAI_CHESS_MODELS` without a frontend build |
| Setup UI | White and Black independently select any configured OpenAI model and advertised effort from `/api/player-adapters`; the catalog labels access as unverified until a call is made |
| Error boundary | Provider response bodies and credentials are excluded from client-visible errors and persisted match records; a provider failure pauses after one call instead of entering a paid retry loop |

## Stage 3C outcome

Anthropic joins the same provider-neutral boundary through the Messages API. A Claude
seat can face a human, Stockfish, another Claude model, or an OpenAI model without
changing match orchestration or browser-control behavior.

| Capability | Stage 3C delivery |
| --- | --- |
| Provider transport | Direct server-side `POST /v1/messages`; provider code remains isolated in `anthropic_adapter.py` |
| Structured proposal | Anthropic JSON Schema output uses a provider-compatible form of the shared UCI move, public plan, public threat, and confidence contract; local Pydantic validation enforces the complete length and numeric bounds |
| Thinking control | Current effort-capable models use adaptive thinking; the adapter omits legacy manual thinking budgets and maps Lounge `fast`, `balanced`, `deep`, and `maximum` to `low`, `medium`, `high`, and `max` |
| Usage | Input and output tokens normalize into common move metadata; reasoning tokens stay unset because the Messages response does not expose a separate reasoning-token total |
| Model policy | Current effort-capable defaults can be replaced with `ANTHROPIC_CHESS_MODELS` without a frontend build |
| Setup UI | White and Black independently select catalog-enabled Claude or OpenAI models and effort, including cross-provider matches |
| Error boundary | Refusals, incomplete output, malformed structured data, HTTP errors, and transport failures are sanitized before reaching match events or clients |

## Stage 3D outcome

Google Gemini joins the same match-facing contract through the Interactions API.
Gemini can occupy either color and face a human, Stockfish, OpenAI, Anthropic, or
another enabled Gemini model without a provider-specific game mode.

| Capability | Stage 3D delivery |
| --- | --- |
| Provider transport | Direct server-side `POST /v1beta/interactions` with `store: false`; provider code remains isolated in `gemini_adapter.py` |
| Structured proposal | Gemini-compatible JSON Schema produces one UCI move, public plan, public threat, and confidence; complete regex, length, and range constraints are enforced locally |
| Thinking control | Gemini 3.8 Flash maps Lounge fast/balanced/deep to low/medium/high; models that expose minimal also map fast/balanced/deep/maximum to minimal/low/medium/high |
| Thinking privacy | Requests set `thinking_summaries: none`; the Lounge stores normalized reasoning-token totals when supplied, never private reasoning text |
| Usage | Total input, output, and thought tokens normalize into common move metadata; cost remains unset until the pricing registry exists |
| Model policy | `GEMINI_CHESS_MODELS` can change the catalog without rebuilding the frontend; override models without a verified effort map remain disabled |
| Setup UI | Both seats discover Gemini models and model-specific effort options from `/api/player-adapters`; unsupported levels are absent, not simulated |
| Error boundary | Failed, cancelled, incomplete, malformed, HTTP, and transport responses are sanitized; a paid failure pauses after one call |

## Stage 3E outcome

Stage 3E opens the same match contract to a routed hosted provider and two local
serving stacks. OpenRouter, Ollama, and vLLM seats use the existing fenced turn runner;
there is no browser-control loop or per-move approval.

| Capability | Stage 3E delivery |
| --- | --- |
| OpenRouter | Server-side Chat Completions adapter with bearer authentication, strict JSON Schema, structured-capability routing, normalized usage, and verified per-model effort mappings |
| Broad model access | `OPENROUTER_CHESS_MODELS` can enable additional router model IDs without a frontend rebuild; models without a verified mapping use an explicit provider-default effort instead of a fabricated comparison label |
| Ollama | Native `/api/chat` adapter with JSON Schema format, non-streaming moves, configured model allowlist, and prompt/evaluation token normalization |
| vLLM | OpenAI-compatible `/v1/chat/completions` adapter with strict JSON Schema, configured local models, and optional server-side API token |
| Local trust boundary | Base URLs, model allowlists, and optional vLLM token come only from the server environment; player payloads cannot supply destinations, headers, or credentials |
| Setup UI | Either seat can choose OpenRouter, Ollama, or vLLM from the common catalog; local models show `Provider default` when no portable effort mapping exists |
| Failure boundary | HTTP bodies, credentials, raw outputs, and private reasoning remain outside snapshots and event records; malformed or incomplete responses are rejected before legality checks |

The local adapters deliberately require an explicit model allowlist. This prevents a
fresh Lounge process from claiming that a model exists merely because an Ollama or
vLLM default URL is present. The default URLs are loopback-only; Compose provides the
`host.docker.internal` host-gateway alias for an operator who intentionally runs the
model server on the Docker host.

## Protocol boundary

The transport-neutral JSON Schemas are published in `packages/protocol`. The
authoritative Python models live in `services/api/lounge_api/player_protocol.py`, and
the reference SDK surface lives in `services/api/lounge_api/adapters.py`.

Adapters receive immutable chess data. They cannot update the board, clocks, events,
or database. The server validates the echoed request identity, position version, UCI
move, lease, durable revision, and deadline before committing.

Legal moves are omitted for the `pure_reasoning` division. The deterministic adapter
requires `legal_assist`; unsupported configurations fail during match creation rather
than silently changing assistance level.

## Credential boundary

Stage 3A requires no provider account or API key. Stage 3B reads `OPENAI_API_KEY`,
Stage 3C reads `ANTHROPIC_API_KEY`, Stage 3D reads `GEMINI_API_KEY`, and Stage 3E reads
`OPENROUTER_API_KEY` plus optional local endpoint configuration from the server
environment (including the ignored `.env.local` development file). Player
settings reject credential-shaped and undisclosed fields through a fail-closed
per-adapter public allowlist, and the repository stores only typed public
configuration and normalized usage. Credentials are used only to construct
provider-specific server-side headers, and neither credentials nor endpoint URLs are
accepted from a game-creation payload.
Subscription-backed agents remain on the user's machine behind the Stage 5 bridge and
will receive only a short-lived Lounge runner token.

The supplied native and Compose launch paths bind to `127.0.0.1`. Until Stage 2E adds
authenticated ownership and quotas, a key-enabled Lounge is a single-user local
development service and must not be published to the internet.

## Persistence and recovery

Migration `0004_player_seats` adds nullable White/Black configuration documents and
nullable per-move metadata. Older rows fall back to their exact legacy mapping:

- `opponent=stockfish` → White human, Black Stockfish
- `opponent=human` → White human, Black human

Startup, reset, and resume schedule whichever persisted automated seat owns the turn.
Pause, abort, resign, and adjudication cancel local in-flight automation; durable
revision and lease fencing reject late work from any other process.

## Verification

- Protocol round-trip, version rejection, secret-field rejection, and schema pinning
- Deterministic adapter repeatability and request binding
- Complete unattended Fool's Mate with both colors automated
- Public metadata/event ordering and database reload
- Human submission rejection on an automated seat
- Illegal automated proposal pauses without changing the board
- Stale or mismatched automated responses pause without changing the board
- Slow automated calls renew their fenced turn lease while thinking
- Pause cancels an in-flight automated call without accepting a late move
- Existing human/Stockfish, clocks, concurrency, analysis, API, and UI build tests
- Alembic `0003 → 0004 → 0003` migration exercise
- Mock-transport contract tests for OpenAI Authorization, provider `store: false`,
  Anthropic API key/version headers, Gemini API-key headers, strict structured
  outputs, every provider effort mapping, usage normalization, malformed output,
  refusals or failed interactions, incomplete responses, health checks, and sanitized
  provider failures
- OpenRouter contract tests for bearer authentication, strict schema routing,
  verified and provider-default effort behavior, usage, health, and sanitized errors
- Ollama and vLLM contract tests for local paths, structured output, absent invented
  effort, optional authentication boundaries, usage, malformed output, and health
- Provider failure integration test proving a paid adapter is called once and the
  match pauses without an unbounded retry loop
- Post-call persistence-failure test proving a completed direct-API turn is never
  automatically purchased again; the match pauses for explicit recovery
- Fenced manager integration test proving an OpenAI proposal becomes one legal move
  with normalized public metadata
- Browser payload tests proving independent model/effort choices and secret-free
  public settings for OpenAI-versus-OpenAI, Anthropic-versus-OpenAI, and
  Gemini-versus-Anthropic seats, plus OpenRouter-versus-Ollama with provider-default
  local effort

## Remaining Stage 3 work

| Sub-phase | Next capability |
| --- | --- |
| 3F | Bounded provider retries, rate limits, outage policy, and operator-facing recovery controls |
