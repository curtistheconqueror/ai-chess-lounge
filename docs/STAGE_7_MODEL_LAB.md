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
