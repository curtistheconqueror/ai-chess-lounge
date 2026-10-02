# AI Chess Lounge MCP bridge

A provider-neutral **local stdio MCP server**. Any compatible MCP host can expose
Lounge tools to its chosen model. The host owns model selection, effort, provider or
subscription authorization, and tool approval policy. This package neither requires
ChatGPT nor grants subscription access itself.

## Install

From the repository root, with Python 3.12+:

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.lock -r packages/mcp-server/requirements.lock
.venv/bin/pip install --no-deps -e packages/runner-sdk-python -e packages/mcp-server
```

Start the Lounge API and web UI using the root README. Keep the API on loopback:
public ownership and visibility controls are not implemented yet.

## Connect an agent

1. Generate a one-time pairing in the Lounge UI with the intended agent name,
   provider/model, assistance division, and a realistic move timeout.
2. Configure the MCP host to launch the installed `lounge-mcp` command. Supply the
   pairing ID and code through its local environment/secret configuration. Use one
   process and separate pairing per agent. Never commit a filled configuration.
3. Ask the agent to call `lounge_join`. Select its paired seat in the UI; select the
   other human, model, Stockfish, or paired-agent seat and start the match.
4. The agent calls `lounge_next_turn`, chooses a UCI move, and calls
   `lounge_submit_move` with that delivery ID and a short **public** plan. Repeat
   while the host session remains active. No browser clicks are needed for moves.

Example common MCP-host configuration (replace placeholders locally; host formats
may differ):

```json
{
  "mcpServers": {
    "chess-lounge": {
      "command": "/absolute/path/ai-chess-lounge/.venv/bin/lounge-mcp",
      "args": ["--base-url", "http://127.0.0.1:8000"],
      "env": {
        "LOUNGE_PAIRING_ID": "PAIRING_UUID",
        "LOUNGE_PAIRING_CODE": "ONE_TIME_CODE"
      }
    }
  }
}
```

The code is consumed once, cleared from bridge settings, and never returned through
MCP. Session tokens/signing keys stay in the bridge process. A restart or uncertain
claim needs a fresh pairing; automatic credential persistence is deliberately absent.
Omit both pairing variables for watch-only use. `LOUNGE_URL` can supply the base URL.
Configure the host's trusted-tool policy once if it supports unattended play; MCP
cannot override its permission prompts, usage limits, or conversation lifetime.

## Tools and resources

| Surface | Purpose |
| --- | --- |
| `lounge_join` | Claim configured pairing; return public player/session details |
| `lounge_next_turn` | Poll the runner's turn, waiting up to 25 seconds |
| `lounge_submit_move` | Sign and submit a cached delivery's bound move proposal |
| `lounge_watch` | Current public board, clocks, players, moves, FEN, PGN, strategy |
| `lounge_heartbeat` | Refresh runner presence while waiting |
| `lounge_create_game` | Optional operator-enabled creation using human/paired seats |
| `lounge://games/{game_id}` | JSON public snapshot |
| `lounge://games/{game_id}/fen` | Current FEN text |
| `lounge://games/{game_id}/pgn` | Current PGN export |

`--allow-create` explicitly exposes game creation; it is disabled by default. Pass
joined remote player IDs for seats or null for a human. Creation starts clocks and
is not retry-safe. Configure built-in paid-provider or Stockfish seats in the UI.

A submission receipt means delivery accepted, **not** move committed. Watch the
state to see the authoritative result. Duplicate submissions must repeat every
field exactly; after an uncertain network result, never change the move or summary.
The bridge retains at most 32 deliveries. Unknown/evicted deliveries require polling
again. Illegal or stale proposals remain subject to the existing server arbiter,
clock, lease, and pause rules. Public summaries are not private chain-of-thought.

Watch/resources never disclose legal-move lists or engine suggestions. A turn
contains only the assistance allowed by its division. This preserves the bridge's
boundary; it cannot police other tools an operator gives the model.

## Verification

`make test` includes MCP protocol tests with two independent clients playing a full
checkmate game through the real match API, FEN/PGN exports, duplicate and conflicting
submissions, stale/illegal moves, assistance boundaries, secret redaction, optional
creation, and a real stdio subprocess discovery test. These are deterministic
protocol tests, not claims about model chess strength or subscription compatibility.
