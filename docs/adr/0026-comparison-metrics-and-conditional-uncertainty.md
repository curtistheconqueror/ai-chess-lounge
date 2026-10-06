# ADR 0026: Comparison metrics and conditional uncertainty

- Status: Proposed (Stage 7D dependent draft)
- Date: 2026-10-04
- Depends on: ADRs 0023–0025 / draft PR20

## Decision

`GET /api/experiment-runs/{id}/metrics` is a read-only projection of the saved
manifest, job results, accepted-move metadata and structured match events. It does
not validate or call adapters, dispatch models, or launch engine analysis. Metrics
are outside both plan schema versions and cannot change their hashes. Responses
include a metrics schema/method version, configuration hash, run revision and timestamp.
The UI loads or refreshes metrics explicitly rather than scanning telemetry on every
run poll. Rows are streamed in bounded database batches.

Outcome tables distinguish scheduled/started/settled games, natural W/D/L, limited,
failed, cancelled and pending games. Known competitor slots are counted; unresolved
knockout slots are reported separately. A failed match affects both participants'
game totals, but structured agent failure/illegal-move events and clock timeouts
are attributed to the active seat. A Black-to-move opening and two effort variants
sharing an entrant ID must not confuse attribution. No invalid-output rate is
inferred from accepted moves.

Efficiency includes accepted-move latency mean/median/nearest-rank p95, sample counts,
and observed retry counts. Each token/cost field has an observed sum plus coverage
and missing counts. No observed value means null, not zero; an explicitly supplied
zero remains zero. These are adapter-reported accepted-move estimates, not complete
provider bills. Failed/cancelled requests may incur unobserved usage. Reasoning tokens
are not added to output tokens because providers may report overlapping quantities.
Public strategy text, private reasoning and raw provider messages are not returned.

## Conditional score uncertainty

Use natural chess scores 0, 0.5 and 1. For fixed schedules, group every color, repetition
and opponent at the exact same initial FEN into one opening block. Each block receives
equal weight; the ordinary per-game score fraction is displayed separately. Require
all scheduled games to have natural completed results, a compatible assistance/
clock/protocol pool and at least two distinct blocks. Otherwise suppress the interval
with a reason. Knockout intervals are always suppressed because opponents are adaptive.

For n independent bounded block means in [0,1], the two-sided 95% Hoeffding radius is
`sqrt(log(40)/(2*n))`; clip to [0,1]. This follows the bounded-independent-variable
inequality in [Berkeley Statistical Learning Theory, Theorem 4.3](https://people.eecs.berkeley.edu/~bartlett/courses/281b-sp08/12.pdf).
The implementation deliberately keeps wide ranges for small samples and all-win data.
Independence of opening blocks is an explicit, unverified assumption. The interval
is conditional on the configured opponent mix, not a calibrated strength or human
Elo interval; it is not adjusted for selecting the best of many comparisons.

Effort deltas are right minus left within one configured entrant. Match opponent
variant, initial FEN, repetition and color, excluding that entrant's self-comparisons.
Require matching complete conditions. Average differences within FEN blocks, then
across blocks. Differences lie in [-1,1], so the paired bound uses twice the radius
and clips to [-1,1]. Incomplete or mismatched conditions suppress inference. These
are descriptive controlled comparisons, not proof that effort caused a change.

## Limits and verification

Live telemetry is a read-time projection, not a frozen research export. Refresh after
settlement for a complete record. No ACPL is calculated: existing engine analysis is
on-demand and not a durable experiment record. Stage 7E handles report bundles.

Verify bounded intervals, no artificial precision from repeated/aliased openings,
suppression for incomplete/mixed/adaptive cohorts, paired effort direction and matching,
read-only API behavior, unknown-versus-zero coverage, Black-to-move attribution,
shared entrant IDs, and exclusion of strategy text. Use deterministic agents only.
