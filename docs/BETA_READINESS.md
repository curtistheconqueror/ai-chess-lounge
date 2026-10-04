# Stage 8E beta readiness packet

Status: **Preparation only. No hosted beta, deployment or complete Stage 8 claim.**
The Lounge is a standalone React/FastAPI application with provider-neutral player
connections. A production URL/vendor/domain has not been selected or deployed.
This packet makes the remaining release work concrete without creating accounts,
credentials, permissions, spending policy or services.

## Verified candidate versus release acceptance

| Requirement | Current evidence | Remaining acceptance |
| --- | --- | --- |
| Human/reference/engine play | Durable arbiter, clocks, takeover/consultation, SDK/MCP runner protocol; responsive smoke suite | Reviewed integration of draft stack; representative acceptance on release SHA |
| Model Lab | Draft experiment plans, shared batch leases, tournament formats, honest metrics/report bundles | Approved merge train, current integrated CI and deferred metric/scope reconciliation |
| Local health/recovery | Bounded readiness/local telemetry, generated SQLite/WAL and native PostgreSQL restore | Production tracing/metrics/alerts/retention, backup ownership/schedule, approved RPO/RTO and rollback |
| Performance | Generated ASGI/queue/database and installed-engine fixtures; loopback transport candidate | Declared production topology/hardware, representative sustained load, operator latency/resource targets, pool supervision |
| Cost control | Reviewed per-attempt contract and test-only symbolic SQLite oracle | Approved ownership/prices/unknown-cost rules; shared monetary/rate ledger, all paid boundaries, estimates and authorized kill switch |
| Accounts/invitations | 2E/6D actor/action proposal | Vendor/admin selection, identity verification, ownership/visibility/invites, HTTP/WS/export/runner isolation and two-user tests |
| Provider-neutral onboarding | Existing direct adapters, local models, remote runner SDK/MCP and one supported subscription bridge | Supported route/model/effort validation per provider, connection tests with approved billing and clear error/availability states |
| Standalone beta | Independently runnable app and local exhibition path below | Approved hosting/TLS/URL, onboarding on actual release, sample exhibition and feedback/incident ownership |

Fixture restoration is not production RPO/RTO. In-process/loopback timing is not a
hosted SLA. Accepted-move usage is not an invoice. A green dependency audit is not
hosted security acceptance. Reports must keep missing usage/cost and no-results
explicit, and never claim calibrated Elo or general intelligence from these scores.

## Local exhibition without provider credentials

Use a clean contributor checkout at the verified head in PICKUP.md. Main is still
Stage 6C while later features remain in dependent drafts. Install dependencies with
`make setup`; start a fresh generated demo database rather than another operator's
configured database:

```bash
LOUNGE_DEMO_DIR=$(mktemp -d)
export DATABASE_URL="sqlite+aiosqlite:///$LOUNGE_DEMO_DIR/lounge.db"
make dev
```

The existing dev script binds the API to loopback and prints the web URL
`http://localhost:5173`. Stop with Ctrl+C. Keep or export generated demo data before
removing its disposable directory; this guide does not delete any existing data.
No paid model is selected by this exhibition.

1. In **White seat** and **Black seat**, choose **Deterministic agent**, then **New match**.
   Observe automatic legal moves, clocks, identity/assistance labels and public strategy.
   This is a deterministic reference exhibition, not a frontier-model comparison.
2. Pause, replay/step through moves, return live, flip the board, copy FEN/PGN and
   **Export PGN**. Confirm replay state is visibly distinct from authoritative live state.
3. Create Human versus Deterministic agent and play by desktop drag or phone tap.
   Check legal-move feedback, promotion and pause/reconnect fencing with the QA matrix.
4. In Model Lab, save a bounded two-entrant reference plan. Saving starts no calls.
   Prepare/run explicitly, pause/resume/cancel, then download a terminal report bundle.
   Limited/cancelled games remain no-results; absent costs remain unknown.
5. Record the exact source, OS/browser/viewport, selected division/clock/effort and
   reproducible steps for any issue. Use generated examples, not private provider data.

Stockfish seats additionally need an installed declared engine. Missing Stockfish is
reported unavailable; the exhibition must not substitute a reference agent silently.
API/subscription seats require their own supported connection/auth route and approved
billing scope. Credential-free reference play does not validate every provider account.

## Release connection test contract

Before a paid/remote beta exhibition, the operator must select an approved connection
and budget scope. The test should show provider/model/effort capability, authentication
outcome, schema/legality compatibility, bounded timeout/cancellation, availability,
usage coverage and explicitly unknown cost. It must not expose credentials/prompts,
create implicit spending authority or accept unsupported effort as a silent fallback.

For subscriptions, verify the provider-supported local authorization route and keep
subscription credentials in the local bridge. Current evidence for one bridge does
not prove all providers support the same subscription flow. Remote grants are scoped
to one match; consultation/batch purposes and multi-worker routing remain deferred.
A connection test may be billable and needs approved limits; none is run by this packet.

## Hosted acceptance sequence after decisions

1. Review ACCOUNT_AND_RELEASE_DECISIONS.md and private security findings; approve
   identity/admin, roles/visibility/invites, budget ownership/policy, topology and release
   scope. Keep Stage 9 explicit. No credentials are required just to review this packet.
2. Implement/review 2E/6D, approved remediation, shared paid-call enforcement and
   production operational controls. Exercise the full actor/action matrix across HTTP,
   WebSockets, downloads and runner paths, including wrong-user/seat/revoked invites.
3. Review the dependent PR train, approve merges, retain contributor branches and
   create immutable completed pickup branches only after verified approved merges.
   Retarget dependent bases deliberately and recheck current integrated heads.
4. On approved infrastructure, verify migrations, generated plus representative backup
   recovery, limits, uncertainty/cancel/retry billing, reconnect/routing, and load on the
   selected hardware/TLS/proxy/worker count. Keep production archives/credentials private.
5. Publish the approved standalone URL/release SHA. Validate onboarding and supported
   connection routes, desktop/phone visuals, one declared sample exhibition and feedback
   reporting on that actual deployment. Keep rollback/incident ownership visible.
6. Reserve the final review window for release acceptance. A failed gate delays launch;
   do not remove auth, billing uncertainty or restore/visual tests to meet the date.

## Feedback and incident intake

A beta report should contain release SHA, generated match/run reference, browser/OS,
viewport, role/connection mode, assistance division, clock/effort, expected/actual
behavior, reproduction steps and a redacted screenshot/export if relevant. Avoid
keys, cookies, raw prompts/responses or private opponent data. Security-sensitive
reports follow SECURITY.md's private route. Assign an operator to triage impact,
record remediation/regression evidence and communicate release/rollback state.
No external feedback service, monitoring schedule or new permission is created here.

## Deadline and unresolved scope

Target: October 6, 2026, 12:40 PM America/Chicago (17:40 UTC), with the final
8–9 hours reserved for integrated review/CI/restore/visual acceptance. Engineering
ranges in DELIVERY_48H_PLAN.md remain conditional; decisions and external service
waits can exceed the remaining window. A tested local candidate is more plausible
than a hosted beta without account/security/budget/topology decisions. No guarantee.

Deferred negotiated draws, purpose-scoped advisers/batches, distributed runner
routing, withheld-clock/adaptive-effort experiments, ACPL/strategic-coherence scope,
provider live/subscription route validation, and 2E/6D are listed in the dated plan;
they must be explicitly accepted or implemented, never silently called complete.

Stage 9 is **Expansion after proof**, with eight unselected candidates: Chess960/
variants; commentary/broadcast styles; opening/theme packs; profiles/season rankings;
embeds; PWA/notifications; signed agent registry/marketplace; and team voting/debate.
“All stages” must resolve whether it includes prioritization after real use, a selected
implementation subset, or all eight with a new scope/estimate. This packet chooses
none and does not omit them from the request.

## Exact release-blocking decisions

The reviewable authorization packet already exists in ACCOUNT_AND_RELEASE_DECISIONS.md.
Outstanding dependencies are approved merge/release; identity/database/hosting/admin
and private/public/invite policy; provider credential and budget ownership, units,
ceilings/prices/unknown usage, shared rates and kill-switch authority; supported
production topology/operational targets; and deferred/Stage 9 scope. These block
live integration/public acceptance, not safe local fixture work. Do not use this
preparation packet as authorization for any of those actions.
