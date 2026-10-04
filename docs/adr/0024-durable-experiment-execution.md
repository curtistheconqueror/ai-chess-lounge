# ADR 0024: Durable experiment execution

- Status: Proposed (Stage 7B dependent draft)
- Date: 2026-10-04
- Depends on: ADR 0023 / Stage 7A draft PR18

## Decision

An immutable plan produces a separately controlled run. Preparing a run creates its
entire bounded job schedule in one transaction but starts no games. UUID idempotency
rejects conflicting settings. Job IDs are UUIDv5(run ID, schedule number) and are also
match IDs, so reclaiming a crashed reservation can only recover the original match.

The database owns run state, revision, original wall deadline, concurrency, job state,
lease nonce/expiry, and results. Controls compare revisions; pause/resume never
extends the original deadline. Cancellation invalidates queued and leased jobs. A `pausing` barrier drains match
runners before the run becomes resumable.
Claims are serialized through a database singleton and the run row: at most four
leased games globally and the chosen one-to-four games per run. Completion releases
capacity. Each fresh reservation gets a new nonce; stale completion and renewal fail.

Execution uses the existing authoritative match and provider runner. Opening FEN is
saved at creation. A match insert and its events validate the live job lease inside
the same database transaction. Move commits lock/check the run and job before writing,
so cancellation, lease replacement, or deadline changes cannot permit a late result. The ordinary turn
lease still prevents competing model calls for one position. Turn boundaries enforce
the ply cap; limited games are aborted and recorded `limited`, never invented draws.
Reset, takeover, manual adjudication, and direct retry cannot mutate experiment identity.

A half-second coordinator dispatches queued jobs and reconciles controls. Worker
heartbeats renew ten-second reservations. Recovery loads the same match and original
clocks. Only an explicitly batch-paused match resumes under a fresh reservation.
A recovered running match has an uncertain dispatch outcome and is failed rather
than replayed; a persisted provider failure is never automatically resumed. Graceful process
shutdown drains in-progress queue database operations before closing the store,
then cancels match runners without erasing queue state. Provider failures settle a job as
failed; the configured failure threshold stops remaining work. Wall time includes
pauses and downtime. A failure in orchestration retries durable bookkeeping, not a
newly invented match ID.

Starting a provider-backed run requires a separate explicit provider-use confirmation.
Preparing a run does not authorize spending. Existing server-only credentials and
adapter capability validation remain in force. No remote/subscription batch grants
are introduced. This implementation/testing uses deterministic agents only.

## Limits

This is a single-host executor with database-coordinated reservations. The existing
provider retry/rate controller remains process-local; global request-rate and monetary
quotas are Stage 8 work. Four-game global concurrency limits simultaneous batch games,
not independent Lounge exhibitions. In-flight provider requests can incur their normal
charge before cancellation; late responses are fenced from committing moves.
Provider refusal/invalid output is a failed job, not an automatic billable restart.
No public deployment, account permission changes, or paid-service provisioning occurs.

## Verification

Test duplicate creation, two-worker claims, stale leases, shared capacity across runs,
pause/resume without deadline extension, cancellation against a delayed adapter on
another worker, process restart with stable IDs, wall deadline, exact ply cap,
provider authorization, migration rollback, and Black-to-move opening script offsets.
Desktop and phone smoke tests prepare, confirm, watch completion, and cancel a batch.
