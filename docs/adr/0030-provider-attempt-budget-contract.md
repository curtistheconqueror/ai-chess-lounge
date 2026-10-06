# ADR 0030: provider-attempt budget reservations

Status: **Proposal and offline fixture only; not live monetary enforcement.**

## Context and decision

Accepted-move usage is incomplete billing evidence. Durable game leases cap batch
concurrency but do not cap requests or spend. Model each actual outbound attempt
separately, admit it atomically in the shared database, and retain possibly billable
holds through timeout/cancellation/crash. Reconcile only with approved evidence;
unknown is not zero and a rejected chess proposal can still be billable.

Keep money and request-rate counters distinct. Choose ownership, units, period,
price source, unknown-cost behavior and authority through the existing account and
release decision process; do not infer them from provider names or subscription
availability. See BUDGET_RESERVATION_CONTRACT.md for transitions and acceptance.

## Prototype boundary

The SQLite fixture lives only under tests, uses generated databases and injected
symbolic integer units, and has no application import, route, dispatch hook, migration,
credentials or provider calls. It verifies competing-process admission, replay,
uncertain holds across restart, evidence uniqueness, true zero and recorded overage.
It is a contract oracle, not an approved schema or production quota implementation.
It does not implement shared rates, multiple scopes, corrections, period rollover,
operator authority, policy changes, PostgreSQL locking or real provider metering.

## Consequences

The contract can be reviewed and tested while account/spending/security decisions
remain outstanding. Integration must add shared transactional reservations at all
paid-call boundaries, approved policy and recovery/authorization/redaction gates.
The fixture's release/recovery methods assume a fenced disposable sender; they must
never be exposed as authorization-free application operations. No spend guarantee
or Stage 8D completion claim follows from these offline tests.
