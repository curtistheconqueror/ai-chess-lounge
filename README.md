# AI Chess Lounge

AI Chess Lounge is a standalone, provider-neutral arena where frontier models,
open models, Stockfish, and humans can play chess together in real time.

The project has two complementary experiences:

- **The Lounge** — a striking live board for exhibitions, spectators, replay,
  commentary, and human participation.
- **The Lab** — reproducible matches, effort sweeps, tournaments, evaluation,
  latency/cost tracking, and model-versus-engine benchmarking.

## Project status

**Stage 2: Durable Match Platform** has sub-phases 2A through 2D implemented,
**Stage 3A–3F** provide the AI-seat protocol, unattended runner, direct OpenAI,
Anthropic, Google Gemini, and OpenRouter adapters, plus local Ollama and vLLM
connections, and the **Stage 4 broadcast vertical
slice** and **Stage 5A–5E remote-runner transport, SDKs, MCP, subscription bridge, and trust controls** are implemented.
**Stage 6A human-seat controls** add desktop dragging, both-color promotion, explicit
resignation confirmation, draw claims, and reconnect input fencing; see
[human play](docs/STAGE_6_HUMAN_PLAY.md).
Matches, moves, resets, and immutable ordered events are persisted;
the match lifecycle is explicit; database compare-and-swap rejects concurrent
writers; Fischer clocks, deadlines, pause/resume, and timeout results are owned by the
server; and idempotent move commands plus fenced turn leases coordinate retries and
workers. Either color can now be Human, Stockfish, or a deterministic reference agent;
two automated seats complete games without browser control. OpenAI Responses,
Anthropic Messages, Gemini Interactions, OpenRouter Chat Completions, Ollama, and vLLM
players can occupy either seat, including cross-provider and hosted-versus-local
matches. Effort is independently selectable only where the adapter has a verified
model-specific mapping; otherwise the UI truthfully shows provider default. The
playable Lounge adds provider-neutral player cards, structured public strategy, local
replay controls, isolated spectator analysis, share routes, and responsive browser
checks. Bounded provider retries, local request budgets, outage circuits, sanitized
failure events, and explicit operator retry are implemented. Independently operated agents can pair once, appear
as selectable seats, receive turns over WebSocket, an allowlisted HTTPS webhook, or
authenticated HTTP long-poll, and submit signed idempotent proposals without giving
provider credentials to the Lounge. Reference Python and TypeScript clients now
handle pairing, binding, signatures, long-polling, safe submission retries, and a
one-command sample bot. A local stdio MCP bridge exposes the same signed move path
as tools plus game/FEN/PGN resources; see [MCP setup](packages/mcp-server/README.md).
A [local subscription bridge](packages/subscription-bridge/README.md) adds
one-match Codex CLI seats. A live ChatGPT-authenticated CLI game reached
checkmate; see [acceptance evidence](docs/verification/stage5d-live.md).
Runner authorizations now bind to one match and seat, with durable turn/time limits,
reconnect without clock extension, audit history, and revocation fenced at move commit.
Pair again for a new match or reset.

Read [`docs/STAGE_2_DURABLE_MATCHES.md`](docs/STAGE_2_DURABLE_MATCHES.md) for the
current increment, [`docs/STAGE_1_VERTICAL_SLICE.md`](docs/STAGE_1_VERTICAL_SLICE.md)
for the playable foundation, [`docs/STAGE_3_AI_ADAPTER_PLATFORM.md`](docs/STAGE_3_AI_ADAPTER_PLATFORM.md)
for the AI-seat contract, [`docs/STAGE_4_BROADCAST_EXPERIENCE.md`](docs/STAGE_4_BROADCAST_EXPERIENCE.md)
for the broadcast shell, [`docs/STAGE_5_EXTERNAL_AGENTS.md`](docs/STAGE_5_EXTERNAL_AGENTS.md)
for remote pairing and transport, [`docs/UI_QA_MATRIX.md`](docs/UI_QA_MATRIX.md) for
the board and responsive release gate, and [`docs/MASTER_PLAN.md`](docs/MASTER_PLAN.md)
for the complete roadmap. No model-provider credentials are required for Stage 2A–2D,
Stage 3A, Stage 3F, the Stage 4 broadcast slice, or Stage 5A–5C. Stages 3B–3E require the
selected provider's platform API key only when a direct OpenAI, Anthropic, Google, or
OpenRouter seat is used. Ollama and vLLM can run without provider credentials on an
operator-configured local endpoint.

## Core match types

- Model vs model
- Model vs Stockfish
- Human vs model
- Human vs Stockfish
- Human takeover of either seat
- Human + AI consultation/team play
- Round-robin and bracket tournaments

## Proposed stack

- **Web:** React, TypeScript, Vite, and a custom accessible chessboard
- **API:** Python, FastAPI, WebSockets, and `python-chess`
- **Engine:** Stockfish through the UCI protocol
- **Data:** PostgreSQL plus an append-only match event log; SQLite fallback for
  zero-setup native development and tests
- **Coordination:** Redis when multi-instance workers are introduced
- **Runtime:** Docker Compose locally; independently deployable web, API, and
  worker services in production

## Run the Lounge

With Docker installed, Compose starts PostgreSQL and the Lounge:

```bash
docker compose up --build
```

Open <http://localhost:8000>. PostgreSQL data survives container restarts in the
`lounge-postgres` volume. For native development, use `make setup` followed by
`make dev`; when `DATABASE_URL` is omitted, the API uses
`.runtime/lounge.db` through async SQLite.

To enable OpenAI seats, copy `.env.example` to an ignored `.env.local`, set
`OPENAI_API_KEY`, and optionally set the comma-separated `OPENAI_CHESS_MODELS`
allowlist. The key remains server-side and is never included in player configuration,
match events, exports, or browser payloads.

To enable Claude seats, set `ANTHROPIC_API_KEY` in the same ignored `.env.local` and
optionally set `ANTHROPIC_CHESS_MODELS`. The built-in allowlist contains current
effort-capable Claude models. Anthropic credentials remain behind the identical
server-only boundary.

To enable Gemini seats, set `GEMINI_API_KEY` and optionally
`GEMINI_CHESS_MODELS`. Gemini 3.8 Flash advertises Lounge fast, balanced, and deep;
models whose API supports minimal thinking also advertise maximum. Unsupported
effort choices are omitted rather than silently emulated. An override model without
an explicit verified thinking-level map remains disabled in the catalog.

To enable OpenRouter seats, set `OPENROUTER_API_KEY` and optionally
`OPENROUTER_CHESS_MODELS`. Known models expose only verified effort mappings;
additional allowlisted models remain playable with provider-default effort. The
adapter requires structured-output-capable routing and keeps the bearer key entirely
server-side.

To enable local models, set `OLLAMA_CHESS_MODELS` or `VLLM_CHESS_MODELS` to the exact
installed model identifiers. The default endpoints are `http://127.0.0.1:11434` for
Ollama and `http://127.0.0.1:8000/v1` for vLLM; override the matching `*_API_BASE`
only in server configuration. vLLM may also use an optional server-side
`VLLM_API_KEY`. Local adapters currently label effort as provider default because
those servers do not expose one portable cross-model effort contract.

To connect an independently operated agent, use the **Remote runner** panel in the
Lounge to generate a one-time pairing. The external runner claims the pairing, keeps
the returned token and signing key locally, then uses WebSocket or HTTP to receive
protocol-v1 turns and submit signed proposals. Set `LOUNGE_RUNNER_SECRET` to a stable
random value of at least 32 bytes before relying on sessions across API restarts.
Outbound webhooks are optional and restricted to exact hosts in
`LOUNGE_RUNNER_WEBHOOK_HOSTS`; arbitrary callback URLs are rejected.

The reference SDKs live in
[`packages/runner-sdk-python`](packages/runner-sdk-python/README.md) and
[`packages/runner-sdk-typescript`](packages/runner-sdk-typescript/README.md). Both
include a deterministic Legal Assist sample bot that can be launched after creating a
pairing; custom agents replace only the move-handler function.

Stage 3F retries only explicitly transient transport, HTTP 429, and selected HTTP
5xx failures. The default is two total attempts inside the original server-owned
move deadline. Authentication errors, refusals, malformed output, stale responses,
and illegal moves pause immediately. Operators can tune the bounded policy with the
`LOUNGE_PROVIDER_*` variables documented in `.env.example`; the browser receives
policy and circuit state, never provider response bodies or credentials.

The provided native and Compose development commands bind to loopback because Stage
2E authentication and quotas are not implemented yet. Do not expose a key-enabled
instance to the public internet; external access becomes supported only with the
ownership, quota, and visibility controls in that later stage.

## Design principles

1. The server is the sole authority for clocks, legality, state, and results.
2. Models never mutate the board directly; they submit a move proposal.
3. Every competitor is identified by its full configuration, not only its model
   name.
4. API, local, MCP, and authorized subscription runners use one normalized player
   protocol.
5. Private chain-of-thought is never requested or displayed. The UI shows a short,
   intentionally generated strategy summary.
6. Raw API keys, OAuth tokens, and subscription credentials never enter game logs
   or the repository.
7. A match must be replayable from its immutable event stream.

## Contributing

Read [`AGENTS.md`](AGENTS.md) before making changes and
[`CONTRIBUTING.md`](CONTRIBUTING.md) before opening a pull request. Resume interrupted
work from [`docs/PICKUP.md`](docs/PICKUP.md).

## License

MIT. See [`LICENSE`](LICENSE).
