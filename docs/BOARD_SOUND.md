# Wooden board audio and audition studio

Open `/sound-lab` on the running Lounge to compare twelve numbered, original
synthesized piece-on-board sounds. Sound 1 (Wood) remains the game default. The
other eleven are new candidates, not claimed copies of a reference app or an
unidentified earlier sound. Auditioning does not select a replacement game sound.

Click **Replay Sound N** to listen. Nothing autoplays. Each audition stops the
previous sample. Shared volume starts at 40%; mute and volume persist locally.
The board also has **Test sound**, mute, volume, and a link to the studio.
Keyboard activation works. At volume zero or while muted, replay buttons disable.
If the test reports it sent audio but the device stays silent, check the browser
tab/site sound permission, device output selection, and system volume.

The earlier web app had no audio implementation or sound setting. Browser audio
now initializes only after a trusted pointer/keyboard gesture or explicit test
click. Suspended contexts resume on later interaction; pre-gesture moves are
dropped rather than queued. Unavailable audio does not block chess play.

Only newly committed adjacent live plies produce board sounds. Captures have a
slightly heavier, longer contact. Duplicate HTTP/socket responses, initial loads,
socket reconnect baselines, history gaps, resets and local replay stay silent.
The default remains Sound 1 irrespective of the last auditioned candidate.

## Signal and implementation

`boardSound.ts` generates short noise contacts and damped inharmonic resonances
into cached Web Audio buffers. No audio downloads, proprietary samples, provider
calls or paid service are used. Audition durations span 100–250 ms. Variants are
energy-matched with peak headroom, while Sound 1's initial waveform is preserved.
Descriptions express synthesis intent; subjective realism awaits user listening.

`BoardSoundControls.tsx` owns browser unlocking and persisted controls.
`SoundLab.tsx` serves the standalone `/sound-lab` route. The game default is not
stored as an audition choice. No board themes or hosted account changes are included.

## Verification

Build/typecheck: `npm run build` in `apps/web`.

For an already-running local server, run the sound suite with
`LOUNGE_E2E_BASE_URL=http://127.0.0.1:8000` and optionally
`LOUNGE_E2E_CHANNEL=chrome`, then `npx playwright test e2e/sound.spec.ts --workers=1`.
Omit those variables for the repository's usual CI server/bundled browser path.

The suite observes native AudioContext rendering with an analyser, source buffers
and gain values. It checks nonzero output, bounded peaks, twelve distinct signals,
comparable sample energy, gesture/suspension behavior, live moves/captures,
duplicate/reconnect/replay suppression, mute/zero volume, persistence, keyboard
input, unavailable audio and five viewport widths (320–1440 px).
These are automated browser signal checks, not a claim of audible output on the
owner's speakers or a subjective listening review.

Hosted-private-beta recovery remains separate: the exact `a766a78` patch must be
recovered and SHA-256 verified before that implementation resumes. No merge,
production migration, live deployment, credentials/access change or spend is made.
