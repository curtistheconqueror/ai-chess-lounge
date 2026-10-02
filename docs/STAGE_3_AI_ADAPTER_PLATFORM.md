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

Stage 3A requires no provider account or API key. Stage 3B reads `OPENAI_API_KEY` from
the server environment (including the ignored `.env.local` development file). Player
settings reject credential-shaped and undisclosed fields through a fail-closed
per-adapter public allowlist, and the repository stores only typed public
configuration and normalized usage. The key is used only to construct the server-side
Authorization header and is never accepted from a game-creation payload.
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
- Mock-transport contract tests for Authorization, `store: false`, strict Structured
  Outputs, every effort mapping, usage normalization, malformed output, and sanitized
  provider failures
- Provider failure integration test proving a paid adapter is called once and the
  match pauses without an unbounded retry loop
- Post-call persistence-failure test proving a completed direct-API turn is never
  automatically purchased again; the match pauses for explicit recovery
- Fenced manager integration test proving an OpenAI proposal becomes one legal move
  with normalized public metadata
- Browser payload test proving independent model/effort choices and a secret-free
  public settings object for both OpenAI seats

## Remaining Stage 3 work

| Sub-phase | Next capability |
| --- | --- |
| 3C | Anthropic Messages adapter and supported thinking/effort mapping |
| 3D | Google Gemini adapter and thinking controls |
| 3E | OpenRouter/OpenAI-compatible and local Ollama/vLLM adapters |
| 3F | Bounded provider retries, rate limits, outage policy, and operator-facing recovery controls |
