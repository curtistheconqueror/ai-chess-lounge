# Stage 8D provider-attempt reservations

Status: **Design proposal, not an enforced spend guarantee or completed phase.**
No amounts, currencies, prices, identity ownership or paid calls are selected here.

## What a reservation represents

A match, batch job or accepted move is not a billable unit. Each actual outbound
provider attempt is an external side effect and needs its own durable attempt ID.
The accepted-move usage in ADR0026 excludes failed/cancelled/lost calls; it is useful
telemetry but cannot act as an invoice or budget ledger. Existing provider reliability
windows are process-local, and the shared four-game batch lease cap is concurrency
coordination, not a shared request-rate or monetary quota. `allow_provider_calls`
is consent to execute a batch, not reservation of spending capacity.

## Proposed state transitions

| State | Meaning | Permitted transition and evidence |
| --- | --- | --- |
| reserved | Atomic admission succeeded; no dispatch boundary crossed | in_flight before send; released only with durable proof it was never dispatched |
| in_flight | Provider may have received this attempt | reconciled on approved billing/usage evidence; uncertain on timeout, cancellation, process loss or persistence failure |
| uncertain | Charge is unknown; hold remains active | reconciled or released only on approved reconciliation evidence, never merely age or a stale move |
| reconciled | Amount/unit usage settled with source and version | Immutable original entry; later corrections append adjustments |
| released | Proven unsent or provider-proven non-billable | Terminal; a new deliberate network attempt needs a new attempt ID |

The database write marking in_flight precedes network dispatch. A crash in that gap
can create a conservative uncertain hold even if no bytes were sent. That is safer
than treating a possibly sent call as free. Crash recovery may release reserved rows
only after fencing their sender and proving that the dispatch marker was not crossed.
It must not automatically resend in_flight/uncertain rows. Provider idempotency may
permit special handling only when its billing semantics are independently verified.

## Transaction contract

1. Check that the caller/run is still allowed to start another attempt.
2. In one shared transaction lock the approved budget subject and rate bucket in a
   stable order. Check policy version/period, numeric bounds, stop state and available
   budget: limit minus settled spend minus active/uncertain holds and adjustments.
3. Insert one reservation with a unique attempt ID and claim its outbound rate slot.
   The same attempt ID plus same immutable parameters replays its result; different
   parameters under the same ID conflict. Admission failure changes neither counter.
4. Persist in_flight before invoking the adapter. Record the network outcome against
   this attempt, including rejected/illegal proposals, independently of move commit.
5. Reconcile idempotently, with a unique billing source plus line-item/event ID. Never silently discard
   a reservation because a callback lost its match revision or worker lease.

SQLite requires write serialization; PostgreSQL requires row locks or equivalent
conditional updates. A process mutex is insufficient. The existing dispatch-lock
pattern is useful substrate, but the ledger must cover direct matches, batch games
and consultations at a common provider-dispatch boundary. Lock ordering, period
rollover and concurrent policy updates require adversarial tests before integration.

Rate and money are separate dimensions. A used rate slot is not refunded because
a request timed out. Every actual retry consumes a new attempt slot and reservation.
Overlapping scopes (owner, connection, operator) require atomic admission across all
applicable scopes or rejection without partial reservation. Shared rate limits need
an approved unit/window/scope; defaults cannot be inferred from provider names.

## Minimum durable data

Use a unique attempt ID; budget subject and provider connection references; policy
version and period; match/run/job/position references; attempt ordinal; configured
input/output/request bounds; hold basis and quantity; dispatch status/time; nullable
usage and settled amount/unit; reconciliation source/time/evidence ID; and append-only
transition/adjustment history. Keep this ledger outside immutable experiment plan
hashes. Retain neither prompts, raw responses, raw headers nor credentials. Public
reports show coverage and unknowns rather than exposing connection/account identifiers.

Money must use approved fixed-point units after currency and precision are chosen.
The existing optional float `estimated_cost_usd` cannot become an enforced debit.
Subscription/local bridges and external runners are not trusted monetary meters;
any excluded route must say so clearly. Unknown prices/usage do not equal zero.
If request bounds cannot yield a conservative monetary hold, no monetary ceiling
guarantee exists. The owner must choose fail-closed paid dispatch or a separately
labeled non-monetary cap; this document does not choose either behavior.

## Failure, cancellation and controls

Pause/cancel stops new reservations and fences late proposals. Release proven-unsent
holds; preserve in_flight uncertainty. Clock expiration, illegal output or no accepted
move does not prove no charge. A reconciliation outage must not make funds available.
A late provider response may settle its original attempt even if its chess proposal
is rejected. Duplicate callbacks cannot double settle. If final charge exceeds the
hold, record actual evidence and debt/overage explicitly; do not truncate to the limit.
Further admission follows approved overage policy. Operators need authorized,
audited reconciliation and kill-switch authority before hosted rollout.

Estimates must distinguish known prices, bounded request estimates, reported usage,
settled evidence and unknown coverage. UI previews cannot promise an exact final
match bill for a variable-length game. Budget state must remain visible after
restart and cannot be reset by clearing process-local caches.

## Offline acceptance matrix

Use generated stores, fake adapters and symbolic units, with no real money or calls.

| Fixture | Required invariant |
| --- | --- |
| Independent processes compete for one subject | Sum of committed holds never exceeds supplied symbolic limit; no partial multi-scope admissions |
| Duplicate reserve/reconcile and changed payload | Same ID replays once; changed immutable payload conflicts; evidence cannot double debit |
| Crash before/after dispatch marker | Proven-unsent release only; possibly-sent attempt remains uncertain across restart |
| Timeout/cancel/pause/clock expiration | Stop new admission; consumed rate slot and uncertain money remain; old move fenced |
| Transient retry / rejected or illegal output | Each actual send has its own record, even without an accepted move |
| Late or duplicate provider response | Settle original attempt once without committing stale board state |
| Unknown price/usage, reported zero, subscription runner | Unknown and true zero stay distinct; no trusted monetary claim from untrusted telemetry |
| Policy/period change during reservation | Deterministic approved policy version; old holds survive rollover; no cache reset |
| Reconciliation adjustment/overage | Evidence and history preserved; no silent cap/truncation or extra funds |
| Privacy/export | No prompts, credentials, raw payloads, connection secrets or user identifiers in public aggregates |
| Kill switch / admin correction | Approved authority checked and audited; fixtures cannot imply authority exists in current app |

## Owner decisions and sequencing

ACCOUNT_AND_RELEASE_DECISIONS.md already identifies the required ownership and
release choices. Resolve budget owner and credential ownership; applicable API,
subscription/local and runner scopes; currency/precision/period; ceilings and shared
hold rules; maximum input/output/request sizes; price source/version; unknown-metering
behavior; rate scopes/caps; billing evidence/manual resolution; and kill-switch
scope/authority. Do not select these implicitly while implementing tests.

Next safe work is a generated-store ledger prototype and state-machine/concurrent
reservation tests using injected symbolic policy. Then review schema, lock ordering,
recovery and redaction. Live integration, enforced monetary policy, accounts, admin
permissions and paid validation remain distinct owner/security approval gates.
The October6 17:40 UTC delivery target does not waive those gates. 8E and deferred
2E/6D depend on the approved hosted/account model; Stage9 scope remains unanswered.

## Implemented offline oracle checkpoint

`services/api/tests/budget_ledger_fixture.py` is test-only SQLite code, never imported
by the application. The tests verify eight attempts competing across four spawned
processes against one symbolic ten-unit budget (only three three-unit holds admitted),
uncertain holds surviving symbolic reopen/recovery, duplicate/changed-parameter behavior,
unknown versus evidenced zero, duplicate billing source/line-item rollback and multiple lines per source, actual overage
without truncation, and release of a proven-unsent fixture attempt.

The fixture covers a single subject and one static injected policy. It has no shared
rate bucket, multi-scope admission, rollover, policy-version correction, admin authority,
PostgreSQL implementation, clock/move integration or real billing. Its release/recover
methods assume proof/fencing supplied by the disposable test caller; they are not
application access-control APIs. This is partial contract validation, not production
spending enforcement or completion of the acceptance matrix. ADR0030 records the
boundary. All remaining live-policy decisions above remain open.

Review corrections reject null/blank/nonstring attempt IDs, make unchanged fixture
policy explicit, key billing evidence by source plus line item, and race identical
attempt IDs across processes. Release/recovery require fixture proof-precondition
tokens; these tokens do not implement real fencing or operator authorization.
No test claims an actual process crash or stale chess-proposal commit.
