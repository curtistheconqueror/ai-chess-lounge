# Phone support and acceptance

October 10, 2026: phone support is implemented for local/private practice.
This is browser-emulation acceptance, not physical iPhone/Android certification.
Public hosted startup remains blocked; private access follows PRIVATE_TAILSCALE.md.

Curtis clarified that the physical device is an iPad. Use the private origin's
root URL (`/`) for a fresh connection or home-screen launch. Root entry checks
the server's current running/paused table and ignores old saved-game storage.
If nothing is live it shows Ready to start with an explicit Play a new match
button. Opening `/games/<id>` intentionally preserves review of that game;
finished games offer both Play a new match and Open current table. A concurrent
new-match conflict opens the current table without aborting or resetting it.
Neither entry nor reconnect automatically starts agents or resumes a paused game.
API reads and service-worker navigations bypass the browser's HTTP cache.

Run `npm run e2e:tablet` for touch-enabled iPad portrait (820x1180) and landscape
(1180x820) profiles in Chromium/WebKit. Entry tests also run in the phone matrix
and existing responsive CI. Physical iPad acceptance remains a manual gate.

The follow-up iPhone report was traced to a paused practice game, then a successful
Abort retaining its saved final position. Board-adjacent Resume play / Play a new
match controls now explain how to continue; an aborted game itself cannot move.
Reload the page to load the update. Eighteen new Chromium/WebKit checks passed
across all three widths, plus a real private HTTPS mobile-WebKit fixture flow.
The user's game was preserved; physical iPhone confirmation is still required.

## What changed

The board uses pointer capture and position-fenced pointer gestures instead of
HTML drag-and-drop. Tap a piece and its legal destination, drag a piece, or open
**Move by square** for larger From/To/Play controls. Cancellation, changed
positions and lost capture clear the gesture. Promotion still uses the existing
explicit piece chooser and server legality checks.

Phone controls have a 44 CSS-pixel minimum target and 16px form text. An eight-file
board cannot have 44px squares inside a 320px screen: compact board cells remain
smaller, with the 44px square-entry alternative immediately below. Safe-area
padding supports notches/home indicators; playback controls wrap without overflow.
The approved pieces, green/ivory squares and original 200ms wooden tap are retained.

Audio unlock runs inside trusted pointer/touch/keyboard gestures. Backgrounding
invalidates the socket and disables moves; foregrounding obtains a fresh server
snapshot before input resumes. The server still owns clocks and moves.

The manifest, 192/512px maskable icons, Apple icon/tags and secure-context service
worker support home-screen use. The worker stores only a generic offline page,
never match snapshots, API responses, credentials or pending moves. Losing the
host means no play; the installed icon does not supply an always-on server.

## Automated evidence

Run `npm run build`, `npm run e2e`, and `npm run e2e:mobile` from `apps/web`.
Install Playwright Chromium and WebKit first. Existing CI runs the responsive
suite only. The separate mobile CI workflow patch is preserved locally because
the Git credential lacks workflow-write permission; run the mobile command
explicitly until that workflow change is separately authorized and published.
For a separate existing local fixture server, set `LOUNGE_E2E_BASE_URL`; never
point this suite at an operator's saved games because fixture cleanup aborts games.

| Gate | Local Windows result |
| --- | --- |
| TypeScript and Vite production build | Passed |
| Existing five-viewport regression suite | 125 passed, 95 existing viewport-scope skips |
| Mobile Chromium at 320/390/430 CSS px | 18 passed |
| Mobile WebKit at 320/390/430 CSS px | 15 passed, 3 native-audio skips |
| Pointer/tap/legal moves, cancellation, stale position | Passed at all six combinations |
| Foreground socket replacement and fresh board | Passed at all six combinations |
| Manifest/icons, offline-only cache, real fixture-host shutdown | Passed at all six combinations |

Windows Playwright WebKit exposes no AudioContext, including on a minimal test
page. Only that platform's native-audio test is skipped; Linux WebKit acceptance
must execute it and remains outstanding. Chromium checks an actual running AudioContext and one 200ms buffer
per move. Pointer dragging is automated through the mouse pointer API; taps use
the touchscreen API. Real finger dragging and audible device output remain manual.
Visibility transitions are simulated through document visibility events; real OS
suspension and recovery remain manual.

Lighthouse 13.5.0, production build, local loopback with mobile throttling:
performance **73**, accessibility **100**, best practices **100**, SEO **63**.
First contentful paint 4.1s; largest contentful paint 4.7s. This is a single lab
sample, not a phone/network benchmark. Remaining findings include render-blocking
fonts, unused JS/CSS and cache lifetimes. The private site's robots policy blocks
indexing intentionally. An unweighted label-content warning remains for board-edge
coordinate text despite square-and-piece accessible labels; 100 is not a claim
that all accessibility or manual audits passed. Modern Lighthouse has no PWA
category; manifest/SW tests do not prove installation or Safari compatibility.

Local handoff artifacts (outside Git) include `mobile-stage2.xml`,
`mobile-stage2-compatibility.xml`, `lighthouse-mobile-final.report.html` and JSON,
plus Chromium/WebKit screenshots at each width in `handoff/mobile-stage2/`.
Existing CI uploads responsive browser results; mobile evidence is currently local.
No live paid provider calls were used.

## Physical-device gate after sharing approval

1. On iPhone Safari and Android Chrome, connect Tailscale and open the approved
   private HTTPS origin. Verify two users see the same Human/Human game and reject
   an unapproved user. Both trusted operators can control either seat.
2. Tap and finger-drag in both orientations; test promotion, cancellation, square
   entry, legal targets and no clipped controls at the smallest supported width.
3. Enable sound with a gesture, then play a move. Check the selected quiet tap,
   mute, volume and no delayed burst after reconnect. Check iOS device audio policy.
4. Add to Home Screen/install, close and reopen. Check icon, standalone viewport,
   portrait/landscape safe areas, and readable controls without form zoom.
5. Background/restore, lock/unlock, and change Wi-Fi/mobile data. Input must wait
   for a current board; no stale move may be submitted.
6. Pause the match, stop the test host, reload and check the offline message.
   Restore the host and reconnect; no offline moves should have been queued.

Record device/OS/browser versions and outcomes before calling phone acceptance
complete. No physical-device or live two-user sharing result is claimed here.
