# Stage 1 — Local Playable Vertical Slice

> Historical stage record. Current `main` also includes the durable Stage 2A/2B
> increment described in [`STAGE_2_DURABLE_MATCHES.md`](STAGE_2_DURABLE_MATCHES.md).

## Current outcome

Stage 1 delivers a locally runnable Human-vs-Stockfish Lounge with a
server-authoritative board and a polished responsive broadcast surface.

| Sub-phase | Delivered |
| --- | --- |
| 1A Workspace | Python 3.12 project, React/Vite app, locked dependencies, Docker, Compose, Make targets, and CI |
| 1B Chess domain | `python-chess` legality, SAN, PGN, FEN, terminal states, version checks, and rule tests |
| 1C Board UI | Responsive board, click-to-move, promotion, strength selector, move panel, PGN/FEN copy, flip, replay, reset, and resign |
| 1D Stockfish | UCI auto-discovery, target-Elo configuration, move-time limit, serialized engine access, and version reporting |
| 1E Live transport | WebSocket snapshot stream, local game restoration, ordered position versions, and reconnect snapshot |

## Start with Docker

```bash
docker compose up --build
```

Open <http://localhost:8000>.

## Start for development

Requirements:

- Python 3.12
- Node.js 24
- Stockfish on `PATH`, at `/usr/games/stockfish`, or specified by `STOCKFISH_PATH`

```bash
make setup
make dev
```

Open <http://localhost:5173>. The web dev server proxies `/api` and `/ws` to
FastAPI on port 8000.

## Verify

```bash
make test
make build
```

## Stage 1 authority rules

- The client proposes a UCI move with the position version it observed.
- The server rejects stale or illegal proposals.
- Only the server mutates the authoritative `python-chess` board.
- Stockfish receives a copy of the authoritative position and returns one UCI
  proposal.
- FEN, PGN, move history, legal moves, game result, and replay frames all derive
  from that same board history.
- WebSocket reconnect begins with a complete current snapshot.

## Stage 1 limitations

- At the Stage 1 exit gate, games were held in memory. Stage 2A now persists games,
  moves, and ordered events across restarts.
- Stage 1 has one human White seat and a Stockfish Black seat. Seat selection,
  model adapters, remote runners, and tournaments arrive in later stages.
- The strategy banner is an explicit public status summary, not model
  chain-of-thought.
- The Stockfish Elo value is a UCI strength target. It is not a universal rating
  guarantee across hardware and time controls.
