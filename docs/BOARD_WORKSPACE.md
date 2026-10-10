# Board workspace checkpoints

The live board, both clocks, evaluation, move list and named End / End and start
new confirmation remain the main view. Root entry still discovers the server's
table. This is a local/private presentation refactor, not hosted authentication.

## Stage 1: information and navigation

1A inventories and relocates controls without removing their bindings:

| Feature | Entry point |
| --- | --- |
| Current game, clocks, end/restart, resume/pause | Board play controls |
| Evaluation, depth, latency, lifecycle, event sequence | Live sidebar metrics |
| Moves and replay selection, spectator analysis | Sidebar Moves / Analysis tabs |
| PGN, FEN, raw match JSON download | Sidebar PGN / FEN tabs |
| Human, engine, all provider seats including OpenRouter | Seats & game setup |
| Model capabilities/effort, strength, time controls, paused start | Seats & game setup |
| Takeover, restore seats, history, adjudication | Seats & game setup / Match control |
| Pairing, remote limits, subscriptions, runner identity/revocation | Connections & API access |
| Provider API configuration | Existing server configuration; keys never entered in this browser |
| Strategy, usage, consultation | Strategy & live telemetry |
| Selected original wood sound, volume, mute, comparison | Board preferences |
| Reset, resign, draw, copy link, export | Match actions & export |
| Model Lab, leaderboards, identity declarations, board comparisons | Lounge tools |
| Suggestions to an AI | Existing contextual board suggestion panel |

1B uses native keyboard/touch disclosures, a focusable setup shortcut next to the
board, arrow/Home/End detail-tab navigation, large touch targets and responsive
desktop/iPad layouts. No added UI dependency. Approved SVG artwork and audio
assets are unchanged. Keyboard/disclosure, overflow and screenshot checks are
recorded in `workspace.spec.ts`. Physical iPad acceptance remains separate.

## Remaining checkpoints

2A: piece translation and drag feedback. 2B: bounded visual spectator pacing,
special moves and interruption handling. 3A: full feature/lifecycle/accessibility
regression. 3B: visual/performance inspection and private-serving byte identity.
Test counts alone do not establish chess.com experience parity.
