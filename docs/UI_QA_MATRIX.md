# Lounge UI quality and regression matrix

The Lounge should feel like a premium chess broadcast, not a developer console. This
matrix is a release gate for every change that can affect snapshots, clocks, moves,
the board, WebSockets, or responsive layout. Stage 4F now runs the five required
viewports as Playwright projects and uploads full-page screenshot artifacts from CI.

## Required viewports

| Surface | Viewport | Required result |
| --- | ---: | --- |
| Desktop | 1440 × 900 | Board remains dominant; control deck is fully usable without horizontal scroll |
| Small desktop | 1024 × 768 | Two-column layout remains unclipped and readable |
| Tablet portrait | 768 × 1024 | Single-column layout; board fills width before the control deck |
| Phone | 390 × 844 | Clocks, board, playback, and primary controls remain thumb reachable |
| Minimum phone | 320 × 700 | No horizontal overflow, clipped labels, or overlapping player cards |

## Board and interaction states

| State | Assertions |
| --- | --- |
| Initial position | 64 labeled grid cells; board is square; pieces and coordinates are crisp |
| Piece selected | Selected square and legal targets are visible without relying on color alone |
| Accepted move | Origin/destination remain highlighted; SAN, FEN, PGN, clocks, and telemetry advance together |
| Illegal attempt | Board does not mutate; selection clears predictably; useful error is announced |
| Check | King/check indicator is unambiguous and position remains server-authoritative |
| Promotion | Queen, rook, bishop, and knight paths work on desktop and touch layouts |
| Special moves | Castling and en passant render and replay correctly |
| Flipped board | Files, ranks, click targets, move highlights, and player rails reverse consistently |
| Replay | Previous/next/live never changes the authoritative live position or clock result |
| Timeout/result | Both clocks freeze; result and losing color agree with the event stream |

## Reliability flows

| Flow | Assertions |
| --- | --- |
| Rapid double action | One move effect and one `move.accepted` event |
| Lost-response retry | Same idempotency key succeeds without applying the move again |
| Stale response | Lower generation/revision snapshot cannot roll the UI backward |
| WebSocket interruption | Offline state appears, reconnect uses backoff, fresh snapshot restores live state |
| Cross-process commit | Socket connected to another API process still observes the durable revision |
| Reload | Active match restores from local storage and authoritative server state |
| Copy | PGN and FEN copy exactly; clipboard failure produces a visible error |
| Reset/resign | Controls disable while pending and terminal state cannot accept another move |

## Automation gate

The browser suite captures the initial broadcast shell at every required viewport and
fails on horizontal overflow, a non-square board, missing grid cells, or missing
critical controls. Desktop interaction smoke tests submit a human move, check legal-
target rendering, exercise local replay versus live state, open analysis, verify the
permalink, and create a credential-free automated-versus-automated match from the two
seat selectors. Mocked provider setup tests also verify that OpenAI-versus-OpenAI,
Anthropic-versus-OpenAI, and Gemini-versus-Anthropic seats use catalog-enabled models,
preserve independent model-specific effort choices, hide unselectable models, and
submit only allowlisted public settings. Check, timeout, promotion, and
post-game visual baselines remain required additions as deterministic fixture matches
are introduced.
