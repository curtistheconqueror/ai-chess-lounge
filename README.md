# AI Chess Lounge

AI Chess Lounge is a standalone, provider-neutral arena where frontier models,
open models, Stockfish, and humans can play chess together in real time.

The project has two complementary experiences:

- **The Lounge** — a striking live board for exhibitions, spectators, replay,
  commentary, and human participation.
- **The Lab** — reproducible matches, effort sweeps, tournaments, evaluation,
  latency/cost tracking, and model-versus-engine benchmarking.

## Project status

**Stage 2: Durable Match Platform** is in progress. Sub-phases 2A and 2B are
implemented: matches, moves, resets, and immutable ordered events are persisted;
the match lifecycle is explicit; and database compare-and-swap rejects concurrent
writers. The playable human-vs-Stockfish Lounge from Stage 1 remains intact.

Read [`docs/STAGE_2_DURABLE_MATCHES.md`](docs/STAGE_2_DURABLE_MATCHES.md) for the
current increment, [`docs/STAGE_1_VERTICAL_SLICE.md`](docs/STAGE_1_VERTICAL_SLICE.md)
for the playable foundation, and [`docs/MASTER_PLAN.md`](docs/MASTER_PLAN.md) for
the complete roadmap. No model-provider credentials are required for Stage 2A/2B.

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
