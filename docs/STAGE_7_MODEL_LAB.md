# Stage 7 — Model Lab

## 7A — Experiment builder (implementation ready for draft review)

Open **Model Lab** in the Lounge header. Configure 2–8 entrants from available direct
or local adapters, supported effort sweeps, Stockfish target Elo, a UCI opening suite,
Fischer clocks, repetitions, color swaps, and stop limits. Preview displays the
expanded schedule and configuration hash. Save persists an immutable draft without
starting games or spending provider credits. Saved experiments reopen after reload.

The API exposes:

- POST /api/experiments/preview: validate and expand ExperimentConfiguration.
- POST /api/experiments: save {id: UUID, configuration: ExperimentConfiguration}.
- GET /api/experiments?offset=0: pages of at most 50 summaries.
- GET /api/experiments/{id}: original complete manifest.

Configuration has entrants [{key, player, efforts}], openings [{name, moves}],
repetitions, color_swap, initial_time_ms, increment_ms, and stops {max_plies,
max_failures, max_wall_time_ms}. Empty effort lists use the player's effort. Opening
moves are UCI from the standard starting position. Up to 16 openings, 20 repetitions,
and 512 expanded games are accepted. Each pair uses all cross-entrant effort variants.

Changing a configuration creates a new draft. Retrying an identical save UUID is
idempotent; conflicting reuse returns 409. Unsupported settings, efforts, terminal or
illegal openings, and oversized schedules return 422. Missing documents return 404.

## Boundaries and next phases

Plans do not start games. Remote/subscription runners retain their one-match grants;
batch grants are not implemented. No credentials, deployment, or public permissions
are changed. Model aliases are not immutable provider versions. Existing adapter
validation and server configuration remain authoritative.

7B adds durable execution with concurrency/provider budgets, resume, stop rules and
cancellation. 7C adds tournament formats and standings. 7D adds measurements and honest
uncertainty. 7E adds comparison reports and bundles. Account permissions (6D/2E) remain
reserved for the final hosted multiplayer rollout. All publication PRs remain drafts;
merge and deployment require separate approval under the current authorization.

See ADR 0023 for hashing, schedule ordering, assistance disclosure and recovery.

## 7B — Durable scheduler (dependent draft implementation)

A saved plan now has **Prepare batch**, followed by a separate **Start batch** review.
Choose 1–4 concurrent games. Direct API entrants require an explicit provider-usage
checkbox. Local deterministic batches need no API credentials. The server revalidates
adapter configuration before start and rejects a changed plan fingerprint.

The run panel shows each job, result and a link once its match exists. Previous runs
can be reopened. Pause/resume retains the original wall deadline; cancellation stops
queued work and invalidates in-flight move commits. Games stopped at the configured
ply limit are `limited`, never counted as draws. The initial opening FEN and normal
match events remain durable. Provider failures count toward the batch stop threshold. An uncertain in-flight
request after a crash is recorded as failed rather than automatically repeated.
Only an explicitly batch-paused game is eligible for automatic resume.

Endpoints: POST /api/experiments/{id}/runs ({id: UUID, concurrency}); GET that same
path for recent runs; GET /api/experiment-runs/{id}; POST /api/experiment-runs/{id}/control
({target: running|paused|cancelled, expected_revision, allow_provider_calls}).

Migration 0011 adds runs, jobs, and the shared dispatch lock. The queue limits batch
concurrency to four games globally. Existing provider retry/rate policy still applies,
but cross-process monetary and request-rate quotas remain Stage 8 work. No live paid
provider batches are run as part of the deterministic acceptance gate. See ADR 0024.

## 7C — Tournament formats and standings (dependent draft)

Choose **Round robin**, **Gauntlet**, or **Knockout** for a schema 2.0 tournament.
The original comparison format remains schema 1.0 and keeps its original hashes.
Each selected effort variant is a competitor. A gauntlet requires an anchor variant;
a knockout requires 2, 4, 8, 16 or 32 competitors, seeded in entrant/effort order.
All configured openings, repetitions and color swaps form a series. At most 512
slots may be planned, including later knockout rounds.

Run preparation and authorization work exactly as before. Later knockout games wait
for known winners. Tied or incomplete series do not advance anyone: dependent slots
are blocked, and the report explicitly has no champion. There are no automatic
extra paid tiebreak games and no score awarded for provider failure or a ply cap.

Run snapshots include a tournament report: series, resolved opponents, champion (if
any), scoreboard and provisional ratings. Completed wins/draws/losses alone earn
points; no-results are shown separately. Ratings start at 1500 with K=24 and are
recomputed in schedule order within each assistance/clock/protocol pool. These are
local experimental ratings, not calibrated human Elo or an established strength claim.
See ADR 0025. Stage 7D adds metrics/uncertainty; 7E adds comparison exports.

## 7D — Comparison metrics (dependent draft)

A run can load or refresh comparison metrics from local records. The API is
GET /api/experiment-runs/{id}/metrics. Metrics preserve both original plan hashes
and include a method version, source revision and generation timestamp.

The report separates completed chess score from failed/limited/cancelled games,
agent failure events, illegal moves, timeouts, accepted-move latency and supplied
usage/cost coverage. Unknown usage stays unknown; partial cost sums are not bills.
Effort deltas match opponent, opening, repetition and color conditions and are
labelled right minus left.

Conditional 95% ranges use equally weighted initial-FEN opening blocks. Repeated
colors/games at one opening do not create independent samples. Incomplete, mixed-pool,
knockout or single-opening comparisons have no interval and display a reason. The
independence assumption is explicit, and these ranges do not measure general
intelligence or calibrated human strength. See ADR 0026 for the formula and limits.

## 7E — Comparison reports and export bundles (dependent draft)

Use the metrics panel to select a rating pool/competitors and compare recorded results.
A terminal batch offers **Download report bundle**. The ZIP includes manifest.json,
report.json, competitors.csv, games.csv, moves.csv, games.pgn, README.txt and
checksums.json. The bundle covers the complete run, independently of UI filters.

GET /api/experiment-runs/{id}/bundle never invokes a provider or alters match state.
Finish or cancel a batch first; an active or changing report returns 409. Unknown
usage/cost remains blank in CSV and null in JSON. The manifest preserves its original
hash and public configuration. Private move text, raw events and runner credentials
are excluded. Review public configuration labels before sharing.

PGNs retain the initial FEN and actual recorded moves. No-result games use `*`;
unplayed/blocked jobs remain in the tabular report without invented games. Exports
over 25,000 moves or 16 MiB uncompressed fail explicitly with 413; use smaller plans.
Checksums verify file content, not signatures or repeatability of provider behavior.
See ADR0027 for consistency checks and the precise privacy/resource contract.
