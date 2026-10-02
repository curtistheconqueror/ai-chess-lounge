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
**Stage 3A–3C** now provide the AI-seat protocol, unattended runner, and direct OpenAI
and Anthropic provider adapters, and the **Stage 4 broadcast vertical slice** is implemented.
Matches, moves, resets, and immutable ordered events are persisted;
the match lifecycle is explicit; database compare-and-swap rejects concurrent
writers; Fischer clocks, deadlines, pause/resume, and timeout results are owned by the
server; and idempotent move commands plus fenced turn leases coordinate retries and
workers. Either color can now be Human, Stockfish, or a deterministic reference agent;
two automated seats complete games without browser control. OpenAI Responses and
Anthropic Messages players can occupy either seat with independently selected model
and effort settings, including cross-provider matches. The
playable Lounge adds provider-neutral player cards, structured public strategy, local
replay controls, isolated spectator analysis, share routes, and responsive browser
checks. Google, open-ecosystem, and subscription adapters remain later increments.

Read [`docs/STAGE_2_DURABLE_MATCHES.md`](docs/STAGE_2_DURABLE_MATCHES.md) for the
current increment, [`docs/STAGE_1_VERTICAL_SLICE.md`](docs/STAGE_1_VERTICAL_SLICE.md)
for the playable foundation, [`docs/STAGE_3_AI_ADAPTER_PLATFORM.md`](docs/STAGE_3_AI_ADAPTER_PLATFORM.md)
for the AI-seat contract, [`docs/STAGE_4_BROADCAST_EXPERIENCE.md`](docs/STAGE_4_BROADCAST_EXPERIENCE.md)
for the broadcast shell, [`docs/UI_QA_MATRIX.md`](docs/UI_QA_MATRIX.md) for the
 board and responsive release gate, and [`docs/MASTER_PLAN.md`](docs/MASTER_PLAN.md)
for the complete roadmap. No model-provider credentials are required for Stage 2A–2D,
Stage 3A, or the current Stage 4 broadcast slice. Stages 3B and 3C require the selected
provider's platform API key only when a direct OpenAI or Anthropic seat is used.

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
[`CONTRIBUTING.md`](CONTRIBUTING.md) before opening a pull request.

## License

MIT. See [`LICENSE`](LICENSE).
