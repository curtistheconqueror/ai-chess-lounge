# Stage 4 — Lounge Broadcast Experience

## Current outcome

The two-seat player protocol now runs inside the provider-neutral Stage 4 broadcast
shell. Human, Stockfish, deterministic agents, and OpenAI Responses players populate
the same player, effort, latency, usage/cost, and public-strategy surfaces. Additional
providers can join those surfaces without a provider-specific redesign.

| Sub-phase | Current delivery |
| --- | --- |
| 4A Player presentation | Expanded identity cards disclose seat type, provider/runtime, strength configuration, division, clock, latency, and cost posture |
| 4B Strategy channel | Separate White and Black public-plan cards plus a clearly labeled spectator PV; no private chain-of-thought is requested or displayed |
| 4C Spectator controls | Local pause, scrubber, keyboard stepping, autoplay replay, jump-to-live, board flip, move navigation, copy, and export |
| 4D Evaluation | A separate full-strength Stockfish process provides White-perspective score, depth, PV, graph points, and approximate move classifications |
| 4E Shareability | Stable `/games/{id}` routes, copy/share behavior, PGN and privacy-safe JSON downloads, and static social metadata |
| 4F Responsive QA | Playwright projects cover desktop, small desktop, tablet, phone, and minimum-phone viewports with overflow, board geometry, critical-control, interaction, and screenshot-artifact checks |

## Visual system

- The board uses an original inline SVG piece family instead of platform-dependent
  Unicode glyph rendering.
- Gold communicates broadcast hierarchy, emerald communicates live/healthy state,
  purple identifies strategy and spectator intelligence, and red is reserved for
  urgent clocks or failures.
- Player cards disclose assistance and configuration instead of presenting a model
  name without context.
- The evaluation bar and graph are secondary broadcast instruments. They never alter
  the server-authoritative board.
- The promotion flow uses a keyboard-accessible, touch-sized picker instead of a
  browser prompt.

## Spectator analysis contract

`GET /api/games/{game_id}/analysis` returns a versioned analysis snapshot containing
one point for the starting position and one for every committed ply. Each point may
contain centipawn score, mate distance, best move, principal variation, depth, and an
approximate move classification.

The analysis engine is a separate `StockfishService` instance from the playing engine.
Results are cached only for the exact match generation and position version. They are
presentation data, not match events, and are never accepted as move proposals.

Classifications use centipawn-loss bands and are intentionally labeled as approximate.
They are useful broadcast cues, not a replacement for deep post-game analysis.

## Share and privacy boundary

Public match snapshots and downloads contain match configuration, moves, clock state,
and spectator analysis. They do not contain engine executable paths, credentials,
provider cookies, private prompts, or hidden reasoning. Until Stage 2E visibility and
permissions are complete, match URLs should be treated as unlisted rather than indexed
public listings.

## Verification

```bash
make test
make build
cd apps/web
npm run e2e:list
npx playwright install --with-deps chromium
npm run e2e
```

CI installs Chromium, starts the production FastAPI/Vite build, and captures full-page
artifacts for 1440×900, 1024×768, 768×1024, 390×844, and 320×700. The interaction
smoke test submits a legal move, confirms replay/live separation, opens spectator
analysis, and verifies the stable match permalink. A mocked OpenAI setup flow verifies
independent seat, model, and effort selection without making a billable provider call.

## Remaining dependencies

- Stages 3C–3E will add Anthropic, Google, OpenRouter-compatible, and local models to
  the normalized provider/model/effort/usage cards now populated by Stage 3B.
- Stage 2E will add explicit public, unlisted, and private visibility plus ownership.
- Stage 5 will connect external agents and subscription runners to these same tables.
