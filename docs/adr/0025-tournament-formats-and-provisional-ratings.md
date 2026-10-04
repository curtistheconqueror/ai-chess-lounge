# ADR 0025: Tournament formats and provisional ratings

- Status: Proposed (Stage 7C dependent draft)
- Date: 2026-10-04
- Depends on: ADRs 0023–0024 / draft PRs 18–19

## Decision

New tournaments use experiment manifest schema 2.0. Legacy schema 1.0 remains a
separate model and serialization path: its saved request/configuration hashes do not
change. Both use the existing experiment API, immutable JSON persistence and bounded
run/job queue. No database migration or new provider authority is needed.

Each exact entrant/effort variant is a competitor. Round robin includes every distinct
variant pair, including two efforts of one entrant. Gauntlet compares a selected
variant against every other competitor. Knockout uses input-order adjacent seeding,
a power-of-two field (2–32 variants), and a fixed series of the configured openings,
repetitions and color swaps. Every format is capped at 512 expanded game slots.
The immutable hash includes format, seeding, bracket, tie rule and rating specification.

Knockout slots reference the winner of an earlier series. Queue claims resolve those
references from durable results while holding the run lock. A downstream match can
only be created after both competitors are known. Its fixed UUID still identifies
the original bracket slot. The worker resolves actual player profiles before creation.

A series winner requires all its scheduled games to have completed chess results and
an unequal aggregate score. A tied series, failure, cancellation or ply-limited game
cannot advance a competitor. Dependent slots become `blocked`; no additional tiebreak
calls or spending are invented. A terminal unresolved bracket has no champion. Users
can prepare a new comparison with a different fixed series before authorizing it.

## Standings and ratings

The read model recomputes standings from the manifest and queue results. Only natural
completed chess results contribute played/wins/draws/losses/points. Failed, cancelled
and limited games are explicit no-results for known competitors, never chess losses.
Blocked slots with unknown competitors cannot attribute results to anyone.

`local-elo-v1` is a deliberately provisional tournament-local measure: start at 1500,
K=24, logistic expected score with a 400-point scale, and process games in immutable
schedule order rather than completion order. Pools separate assistance division,
initial/increment clock and player protocol version. Competitor profile hashes remain
visible. Cross-pool exhibitions contribute ordinary scoreboard results but never Elo.
Rows without rated games retain only their initial seed; this is not a calibrated
human/FIDE/Stockfish rating, confidence interval, or cross-tournament leaderboard.
Tied points share a rank within a pool; no undisclosed tie-break ranks are applied.

No mutable rating table is necessary. Restart and concurrent completion cannot produce
a duplicate rating update. Metrics/uncertainty and exports remain 7D/7E work.

## Verification and limits

Pin a known v1 hash; test v2 API persistence, formats and bounds, variant pairing,
knockout dependency readiness, tied/failed/limited blocking, color-swapped scoring,
separate pools, deterministic rating order, and a complete live deterministic bracket
through the existing arbiter. Desktop/phone smoke checks cover preview and results.

All matches retain Stage 7B authorization, original deadline, exact claim fencing,
conservative crash recovery and concurrency limits. This phase grants no subscription
batch access, credentials, public hosting or account permissions. PRs remain drafts.
