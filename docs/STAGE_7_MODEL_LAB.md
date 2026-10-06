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
