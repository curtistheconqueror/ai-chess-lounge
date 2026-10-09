# Board audio and appearance comparisons

Curtis selected the supplied original single-tap prototype (Sound 13) as the
game default. Every newly committed live move, including captures, plays this
same 200 ms WAV once. Test sound also uses it. Auditioning another candidate
does not change the selection. There is no substitute if the asset fails to load.

The supplied originals are preserved byte-for-byte in apps/web/public/audio:

- chess-lounge-wood-prototype.wav: SHA-256
  45bea7b0a9c90b28ea4e07d12621cb3173e3f1cf7ecace0218cb6a69459cbc00.
- chess-lounge-wood-four-taps.wav: SHA-256
  1b17438248aa6f71bb27dcf75ad7f9e926da61603941cffd75c34aa79a912b1e.

Both are mono, 48 kHz, 16-bit PCM. The four-tap clip contains four identical
copies of the single tap, with identical gain and zero-filled gaps. It is a
2.8-second listening demo only, available at /original-wood-player.html;
the game never uses it as a move sound. No proprietary reference recordings
are included. These are the user's original procedural prototype files.

/sound-lab preserves candidates 1-12 and the six already-completed dense
variants 14-19 alongside selected Sound 13. Sound expansion has stopped.
The dense variants derive only from the original prototype; their generator
and hash/parameter manifest are in scripts/audio/generate_dense_candidates.py
and apps/web/public/audio/dense-provenance.json. Descriptions describe intent,
not a claim of subjective realism. Each audition stops the previous sample.

Volume starts at 40%; mute and volume persist locally. Audio initializes after
a trusted pointer/keyboard gesture. The original asset preloads without playing.
Moves before unlocking are dropped, not queued. Initial loads, duplicate HTTP/
socket responses, reconnect baselines, history gaps, resets and replay are quiet.
Unavailable audio does not block chess play.

Mute and zero volume cancel gain automation, set gain immediately to zero and
stop/disconnect active sources. A scheduled fade alone can leave gain pending
when the audio clock is suspended; the regression test holds the native context
suspended and verifies zero gain and no active voices. The previous CI mute
assertion remains intact.

/board-studio compares current, wood, glass-inspired and metallic looks using
the same board component, pieces, size and position. Shared controls flip all
boards, change the preview position and toggle highlights. These are visual
previews only; the live game's appearance remains unchanged pending selection.

The studio's **Current vs proposed pieces** tab (direct link:
`/board-studio?pieces=compare`) compares the existing pieces with an original
classic SVG set. It includes all 12 pieces on both square colors at 32, 40 and
64 px, four board finishes and an eye/detail-free silhouette check. The shared
renderer defaults to the existing set everywhere outside this explicit preview.
No Figma usage or copied reference assets are claimed. Ten additional board/piece
checks passed across five viewports; artwork still awaits Curtis's review.

## Verification

Run npm run build in apps/web. For an existing local server, set
LOUNGE_E2E_BASE_URL=http://127.0.0.1:8000 and optionally
LOUNGE_E2E_CHANNEL=chrome, then run:

    npx playwright test e2e/sound.spec.ts e2e/board-studio.spec.ts --workers=1

Omit those variables for the usual CI server/bundled browser path.

The focused suite passed 60 checks across five widths (320-1440 px): native
audio rendering, exact original asset hash, first-move selection, mute/zero,
suspended clocks, persisted settings, keyboard/pointer unlock, capture and
duplicate/reconnect/replay handling, loading failure and slow-decode races;
four comparable boards, coordinates, flip/position/highlight controls and no
horizontal overflow or game writes from the studio. Production build passed.
Screenshots were inspected. These checks measure browser signals, not actual
speaker output or subjective listening. Published-head CI is a separate gate.

Hosted beta remains blocked on recovering and verifying the exact a766a78
patch. No hosted readiness, merge, production migration or deployment is claimed.
