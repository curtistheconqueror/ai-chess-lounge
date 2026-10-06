# ADR 0027: Stable terminal experiment report bundles

- Status: Proposed (Stage 7E dependent draft)
- Date: 2026-10-04

## Decision

GET `/api/experiment-runs/{id}/bundle` returns a ZIP only for completed, stopped or
cancelled runs with settled jobs. Running, ready, pausing and paused runs return
409; exporting never starts, pauses or cancels work. Missing IDs return 404 and
invalid UUIDs return 422. The response is an attachment with `Cache-Control: no-store`.

The bundle contains the original public manifest, report JSON, competitor/game/move
CSVs, PGNs, README and SHA-256 file checksums. The original v1/v2 configuration hash
is recomputed and verified, then preserved unchanged. The report has its own schema
version, run revision, match generation/revision/ply markers and metrics method version.
The export timestamp can differ between captures; identical configuration hashes do
not promise identical provider results or byte-identical ZIPs.

## Consistency and resource limits

Terminal state makes the scheduled cohort fixed. Export records match revision,
generation, position-version and event-sequence markers before collection, then
rechecks them and the full run/job snapshot after collection. A change returns 409
instead of returning a mixed report. Legitimate writes increment these markers;
out-of-band edits bypassing the application are outside this consistency contract.
Metrics must name the same run revision. This is optimistic validation, not a claim
that the separate database sessions share one transaction snapshot.

Moves are read in bounded batches and validated for ply order, legality, resulting
FEN, final position and expected ply count. Completed chess-result jobs also require
a completed match whose saved authoritative outcome agrees with the queue result. Exports cap accepted moves at 25,000 and
uncompressed contents at 16 MiB. Exceeding a cap returns 413 without silently truncating
records. The existing 512-job manifest bound also applies. Two export requests may
build at once per API process; compression runs off the event loop. No temporary files
are created, and DB sessions close before download. This per-process bound is not a
replacement for Stage 8 distributed quotas or performance acceptance.

## Privacy and result semantics

Exports explicitly select move fields rather than serializing snapshots or stored
move metadata. Private plans/threats/reasoning, raw events, consultations, runner grants,
credentials and connection secrets are not exported. The manifest remains the original
validated **public** configuration, including user-supplied public labels/settings.
Users should review those public fields before sharing. PGN player headers use variant
keys rather than arbitrary display names; quoted header values are sanitized.

PGNs start from the exact scheduled initial FEN and contain only recorded legal moves.
Only queue jobs with completed natural chess results receive `1-0`, `0-1`, or `1/2-1/2`.
Limited/failed/cancelled games use `*` plus job-state/result tags. Unplayed or blocked
slots have rows in the report but no fabricated PGN. CSV numeric blanks mean unknown,
not zero; cost coverage is included. Formula-like text after leading whitespace/control
characters is apostrophe-prefixed in CSV. JSON preserves original public values.

## Verification and limits

Regression tests cover both manifest schemas, hash recomputation and per-file checksums,
custom-FEN PGN replay, no-result handling, privacy sentinels, CSV formulas, unknown cost,
active-run/missing-ID HTTP behavior, unplayed slots, changed snapshots, corrupt stored
content and explicit size failures. Browser acceptance covers download and comparison
filter controls on desktop and phone. Existing account/visibility restrictions remain
for the later 2E/6D rollout; no public hosting or new security access is authorized here.
