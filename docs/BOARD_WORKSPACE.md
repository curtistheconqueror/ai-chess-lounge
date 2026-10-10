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

## Stage 2: motion and spectator pacing

2A uses browser-native Web Animations transforms on the existing SVG wrapper;
no third-party chess widget or animation dependency replaces the board. Dragging
follows the pointer. The server owns the accepted move and no motion callback
submits a move or produces sound. A dragged piece is not animated a second time.

2B provides instant/150/300/500 ms transitions and 0/150/300/600 ms visual buffers
for automated moves when no human move is available. A human's reply gets no
extra spectator buffer. Preferences use optional local storage. Reduced motion
snaps immediately, including when toggled during an animation. Clocks, history
and evaluation update from the current authoritative snapshot without waiting.
Board input is fenced during the bounded visual transition to avoid acting on a
piece still in transit. This never delays the server's clock or any agent turn.

There is no accumulating move queue. An update that interrupts a transition
snaps to the newest position; missed histories and replay jumps also snap.
Game ID, generation, lifecycle, connection, live/replay mode, board orientation
and resizing cancel outstanding motion. Consecutive forward replay can animate.
Castling translates both king and rook; capture/en-passant removal and promotion
come from the authoritative final position. Promotion shows the promoted piece
during translation. Original sound deduplication remains unchanged and plays
on acceptance, independently of visual pacing.

`motion.spec.ts` covers these boundaries on disposable games. The automated
metadata scenario is a mocked socket fixture, not a live provider call.

## Stage 3: regression and review

3A: 68 desktop feature/lifecycle checks passed. Full iPad Chromium/WebKit
portrait/landscape matrix: 122 passed, two existing Windows WebKit native-audio
skips. The first desktop run found narrow-screen tools-menu overflow; the fix
passed the clean aggregate rerun. Legacy feature suites explicitly set the
expanded workspace fixture without an audio-unlocking gesture. Separate tests
cover real keyboard disclosure, focus, tab navigation and the collapsed layout.
Provider catalogs are mocked for binding tests; no paid provider calls occur.
An additional20-check desktop run passed with native audio and motion enabled,
including keyboard square activation and actual socket reconnection during motion.
Final refinements passed36 iPad motion checks,10 responsive workspace checks and
four explicit no-buffer-on-human-reply checks. These runs overlap earlier cases.

3B records visual/performance inspection and private-serving byte identity in
the local dashboard handoff. Full screenshots and a bounded animation sample
are diagnostic evidence, not proof of physical iPad latency or chess.com parity.
Five private desktop/iPad browser contexts verified HTTPS/API/WSS, settled
evaluation, zero page errors/overflow and no mutation requests. The paused game
was verified unchanged. Static assets were refreshed without a backend restart;
the prior entry/assets remain recoverable. Exact current hashes are local evidence.
Physical iPad acceptance and Linux WebKit native-audio verification remain gates.
