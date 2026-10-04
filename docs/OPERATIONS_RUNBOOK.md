# Operations and recovery runbook — Stage 8B candidate

Status: **In progress. Offline SQLite fixture recovery is tested; production
operations, native PostgreSQL CI restore, tracing, alert delivery and retention are
not yet fully accepted.**
No live database, account, setting, provider or deployment is changed by this document.

## Current evidence and remaining work

`services/api/tests/test_restore_rehearsal.py` generates a terminal Model Lab game,
backs up its database, restores into a different temporary database, compares the
complete SQL dump, and verifies game FEN/version/result, run/job state and reproducible
manifest/game/move/PGN exports. A separate WAL test confirms that committed journal
content is included and an uncommitted write is excluded. All connections close.
This is a correctness rehearsal at fixture scale, not a production RPO/RTO result.
It does not establish multi-host durability, encrypted storage or PostgreSQL recovery.

Run with `.venv/bin/pytest -W error services/api/tests/test_restore_rehearsal.py`.
The helper exists only in tests. It is not a supported live backup CLI or scheduled job.

| Operational gate | Existing behavior / evidence | Remaining acceptance |
| --- | --- | --- |
| Process health | Compatible liveness plus bounded `/api/ready` database/worker checks; engine optional unless requested | Deployment probe policy and fault/recovery drill |
| Backups | Offline SQLite snapshot/restore regression | Approved PostgreSQL backup destination, access and encryption; native backup plus isolated restore and measured RPO/RTO |
| State recovery | Persistent moves/events, revision fencing and queue recovery tests | Production-topology crash/restart drill, runner reconnect and clock reconciliation |
| Observability | Opaque request IDs; capped process-local route timing/status summaries and WebSocket counts; privacy regressions | Full tracing, queue/provider/engine/DB operational metrics, approved collector and sampling |
| Alerts | No delivery configured | Approved recipient/channel; synthetic fault and recovery delivery checks; alert ownership |
| Retention | No deletion job applied | Owner-approved category durations, legal/operational holds, preview counts, recovery and deletion acceptance |
| Rollback | Versioned migrations, CI upgrade/downgrade checks | Exact release/backup mapping and rehearsal with real populated schema; no automatic downgrade of live data |

## Backup and isolated restore procedure

1. Record the exact application commit, database engine/version, migration revision,
   UTC backup time and operator. Keep credentials and connection URLs out of evidence.
   Owner must select recovery-point and recovery-time objectives; none is promised yet.
2. Use the database engine's consistent backup mechanism. Do not copy only an open
   SQLite main file while WAL content may be outstanding. PostgreSQL requires its
   own native backup/PITR approach; SQLite test results do not validate it.
3. Preserve the source and immutable backup. Record artifact checksum, size and
   completion status in restricted operator records. A checksum detects corruption;
   it does not encrypt or authenticate an untrusted backup.
4. Restore into a new isolated database at the compatible schema/application version.
   Keep provider execution, outbound webhooks, subscription bridges and worker
   scheduling disabled during validation. Do not point a live service at this copy.
5. Verify schema revision, database integrity, row/event counts, sampled legal move
   replay, exact final FEN/result, run/job states, configuration hashes and report
   regeneration. Inspect idempotency and runner-grant recovery in the approved topology.
6. Treat external calls around a crash as potentially billable. Do not automatically
   replay uncertain jobs or trust restored runner grants as newly authorized. Restored
   clocks/leases require the existing recovery policy and explicit acceptance.
7. Measure elapsed restore time and latest recovered event timestamp against approved
   RTO/RPO. Record failures and limitations. A successful fixture is not a substitute.
8. Cutover, credential/grant disposition and rollback require the release owner's
   approval. Retain original data until the approved retention decision. Never test
   destructive restore against the only copy or run a live downgrade as a rehearsal.

## Incident handling

| Symptom | Immediate read-only triage | Controlled recovery and verification |
| --- | --- | --- |
| API unavailable | Check process, version, health and database connectivity without printing URLs | Operator restores known configuration; verify readiness and deterministic match |
| Database unavailable / writes failing | Preserve error category, timestamps, release and last durable event | Stop admission through an approved control; restore connectivity before replay/retry decisions |
| Provider failures / uncertain usage | Inspect sanitized failure category, pending turn and budget reservation state | Pause affected work using existing controls; reconcile provider usage before explicit retry |
| Queue stalled | Check durable run/job/lease state and worker liveness | Follow fenced lease recovery; do not edit rows or mint replacement games manually |
| Engine exhaustion | Check engine availability, queue pressure and resource telemetry | Reduce approved workload or recover pool; never substitute an engine move for an agent |
| Suspected access/secret issue | Preserve restricted evidence; follow SECURITY.md privately | Owner-controlled containment/rotation and access review; never publish raw logs or exploit details |
| Bad release | Identify exact release, schema compatibility and last tested backup | Prefer tested application rollback when compatible; otherwise isolated restore and approved cutover |

After recovery, verify replay, clocks, duplicate-move rejection, runner reconnection,
export integrity and a deterministic exhibition. Document incident times, affected
capabilities and unresolved uncertainty. Notify only approved recipients; this runbook
does not configure or send notifications.

## Proposed telemetry and retention contract

Measure request latency/error class by route template, active WebSockets, dropped
connections, queue age/lease expiry, provider retry/outcome category, engine wait,
database failures and backup age/result. Avoid match IDs, user/model labels, prompts,
raw responses, credentials, full URLs and unbounded tags in metrics. Correlation IDs
must be opaque and must not encode user data. Decide collector access, sampling,
retention and alert thresholds with the operator before enabling an external sink.

Define retention separately for game/event records, private connection references,
runner authorizations, reports, backups and operational telemetry. Record ownership,
expiry, holds and downstream copies. Produce a dry-run inventory before any approved
deletion. No retention duration or automated deletion is selected here.

## Next implementation checkpoint

Add bounded readiness and privacy-tested instrumentation under the approved local
mode; rehearse native PostgreSQL restore in an isolated fixture environment. Then
validate alerts/retention/backups in the chosen deployment. Keep 8B open until all
roadmap deliverables are implemented and accepted. See DELIVERY_48H_PLAN.md and
ACCOUNT_AND_RELEASE_DECISIONS.md for deadlines and external gates.

## Local readiness and instrumentation candidate

`GET /api/ready` returns a fresh database/worker readiness result without changing
games or invoking providers. Its HTTP wait is bounded to 250 ms around one shared
probe; timed-out callers return unavailable without cancelling connection creation.
A successful DB result is cached for two seconds. Worker success must be within five
seconds. Add `?require_engine=true` only for engine-required service readiness; an
installed engine is not proof of a successful analysis. Existing `/api/health` remains
liveness. Database failures expose no driver error or connection URL. Shutdown drains
the shared probe before disposing the store; the driver shutdown itself can take longer.

`application.state.operations.snapshot()` provides local aggregate route-template
latency/status counts, a 100-entry timing ring and WebSocket active/opened counts.
An opaque server-generated `X-Request-ID` accompanies ordinary HTTP responses.
No request-supplied ID, path/query/body/header, match ID or provider text is retained.
This is not a public telemetry endpoint or external collector; counts reset on restart.

The native PostgreSQL fixture test is explicitly enabled in CI against its existing
PostgreSQL 17 service. It creates separate disposable UUID databases, uses native
custom-format dump/transactional restore, checks logical rows before app initialization
and validates game/event/run/export state. Only secret-free counts/size/timing evidence
may be uploaded. Local environments without this declared infrastructure skip that test.
Record its actual published CI outcome before calling PostgreSQL recovery verified.
See ADR0028; full Stage 8B and production recovery acceptance remain open.
