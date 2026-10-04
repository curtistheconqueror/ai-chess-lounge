# 48-hour delivery target and scope decisions

Updated October 4, 2026, 18:30 UTC. Requested target: October 6, 2026,
17:40 UTC (12:40 PM America/Chicago). This is a target, not a guarantee or
permission to merge, deploy, purchase services, create credentials or expand access.

## Verified position

Main remains Stage 6C at 087c565. Stage 7A–7E are stacked drafts PR18–PR22.
PR19 corrected final head ade6bb2 passed CI 37221621195; PR20 f2b4bc3 passed
CI 37221279231. PR21 final head fa2e9a1 passed CI 37222067606. PR22 source
64f7c2c passed CI 37223412652 (302 Python, 3 SDK, 34 browser tests, both
migrations, lint/types/build); desktop/phone report downloads and screenshots passed.
PR22 final documentation head 5baac32a passed CI 37223844056. Stage 8A read-only
assessment and decision packet are in progress. No draft has been merged and no
production acceptance or partially implemented phase is described as complete.

## Phased target checkpoints

Ranges below are engineering/validation effort estimates, not guaranteed elapsed
completion times. Dependencies and approval waits can exceed the remaining window.
Parallel read-only review can help, but does not remove serial integration gates.

| Target checkpoint (UTC) | Deliverable | Estimated effort | Dependencies / acceptance |
| --- | --- | --- | --- |
| Oct 4, 20:00 | 7D metrics checkpoint; retry corrections verified across stacked heads | 1–3 h | Full current-head CI, desktop/phone visual inspection, precise pickup |
| Oct 5, 00:00 | 7E reports and bounded CSV/JSON/PGN bundles in draft | 3–5 h | 7D schema; reproducible hash, export privacy and consistency tests |
| Oct 5, 04:00 | 8A security assessment and prioritized findings; deployment/account design decision packet | 3–5 h | Threat model, secret/dependency audits, abuse/SSRF/injection tests; security changes require approval |
| Oct 5, 12:00 | 8B operations and 8D cost-control implementation candidates | 6–10 h combined | Observable health/metrics, backup/restore rehearsal, retention/runbooks; durable quota semantics, cross-process rate/budget enforcement, kill switch tests |
| Oct 5, 20:00 | 2E/6D account and invitation implementation candidate if decisions/authorization arrive | 6–12 h | Identity/hosting decision, role/visibility matrix, invitation expiry/revocation, two-user isolation tests; no public exposure without approval |
| Oct 6, 03:00 | 8C measured performance results and bottleneck corrections | 3–5 h | Representative spectators/WebSockets, engine/queue/DB load; declared hardware and bounded resource use |
| Oct 6, 09:00 | 8E release candidate and beta checklist | 3–5 h | Approved integration/deployment path, standalone URL, onboarding/connection test, deterministic exhibition, feedback and rollback |
| Oct 6, 17:40 | Integration/review/CI/restore/visual buffer and final acceptance decision | Reserve 8–9 h | Re-run integrated gates; confirm secrets/quotas/access isolation, backup restore and rollback; operator approves launch |

Implementation ranges total roughly 25–45 hours before the final buffer and
unbounded external waits. The optimistic path fits; the upper range does not.
A security finding or missing deployment/account authorization makes a hosted-beta
finish unlikely inside 48 hours. A tested local release candidate is more plausible.
Do not compress the final security, restore, CI or visual gates to meet the date.

## Deferred requirements that must be reconciled

- 2E accounts and 6D owner/player/spectator/moderator roles, private invitations and
  private/public visibility are release dependencies for hosted multi-user operation.
  Supabase is an option, not an assumed purchased or authorized dependency.
- 6A negotiated draw offers remain deferred; track explicitly in acceptance scope.
- Remote consultation requires purpose-scoped authorization; current grants cover
  one match, not advisers or tournament batches. Extending access needs approval.
- Distributed runner presence/routing and durable transport delivery remain deferred;
  either implement/verify them or document a bounded single-worker beta limitation
  with explicit scope acceptance, never imply multi-worker readiness.
- Clock-supplied versus withheld conditions and model/controller-selected adaptive
  effort experiments are disabled. Fixed effort/supplied-clock support does not
  satisfy that full experimental requirement.
- Global monetary quotas and cross-process request-rate limits belong to 8D;
  batch concurrency limits alone do not satisfy them. Estimates depend on usage
  availability and provider pricing; unknown costs must remain unknown.
- Independent engine move-quality/ACPL and strategic-coherence measurements must
  be audited against the original evaluation requirements; current 7D observed-score
  metrics do not establish that every aspirational metric has shipped.
- Provider-specific subscription availability, credential handling and paid live
  validation depend on supported routes and explicit authorization; deterministic
  adapter tests do not prove every provider/account works in production.

## Stage 9: unresolved scope, not silently omitted

MASTER_PLAN defines Stage 9 as **Expansion after proof**, prioritized only after
real use. Its eight candidates are:

1. Chess960 and additional variants.
2. Commentary agents and audience-selectable broadcast styles.
3. Opening/theme challenge packs.
4. Public profiles and season rankings.
5. Embeddable live boards.
6. Mobile install/PWA and notifications.
7. Agent marketplace/registry with signed capability manifests.
8. Team battles with voting/debating agents and public summaries.

No subset is selected or estimated as an approved commitment. “All stages” must
resolve whether it means the defined Stage 0–8 release plus a Stage 9 prioritization
checkpoint after actual use, or implementation of specific/all eight expansion areas.
The latter cannot credibly be promised in this 48-hour window alongside production
hardening; it requires a separate scope, acceptance criteria and estimate. Continue
established work while the owner decides; do not invent a minimal Stage 9 completion.

## Critical path, decisions and confidence

The critical path is corrected stacked CI → 7D/7E exports → account/security/cost
boundaries → operations/load validation → authorized integration and deployment →
end-to-end beta acceptance. Draft review and safe local implementation can continue
while approvals wait. Keep PR18–PR21 and subsequent contributor branches intact.

Needed external decisions: merge approvals; identity/hosting choice; authorization
for account/security changes; deployment URL/environment; provider spending ceiling
and live test credentials if desired; deferred-feature beta acceptance; Stage 9 scope.
Nothing in the deadline request supplies those approvals. Parent owns monitoring;
do not create duplicate monitors. Report blockers promptly at each checkpoint.

Confidence: moderate for 7D/7E and a substantial locally tested hardening candidate;
low-to-moderate for a hosted multi-user Stage 8 beta within 48 hours, conditional on
prompt decisions and no major findings; no credible commitment for all Stage 9
candidates in that window. Revise ranges after the 8A review and first load results.

## Checkpoint update — October 4, 18:15 UTC

7D final docs head fa2e9a1 passed CI 37222067606. 7E draft PR22 source head
64f7c2c passed CI 37223412652: 302 Python, 3 SDK, 34 browser tests plus all
migration/lint/type/build gates; desktop/phone screenshots inspected. Its final
pickup update is documentation-only and still receives a distinct current-head check.
The first two implementation checkpoints are ahead of their target windows.
Stage 8A read-only review has begun. Security/account/merge/deployment approvals and
Stage 9 scope remain unresolved; this progress does not remove those critical-path
dependencies or upgrade the hosted-beta confidence to a guarantee.

## Checkpoint update — October 4, 18:30 UTC

7E final documentation CI is green. Scoped dependency audits found no known
advisories; selected current-source/history key patterns found no candidates.
These results do not establish hosted security. The account/release decision packet
and trust-boundary assessment are ready for review; 8A remains in progress pending
reviewed remediation and authorization. Next safe work is 8B offline restore and
operations preparation. The schedule and confidence ranges above remain conditional.

## Checkpoint update — October 4, 18:40 UTC

7D/7E source and final handoff checks are green; merge approval remains outstanding.
8A assessment is draft PR23 at 786f8b7, green CI 37224743392. 8B preparation is
draft PR24: generated-fixture SQLite restore/WAL checks and operations runbook;
303 local Python tests pass (3 environment skips). Neither 8A nor 8B is complete.
The original 8A–8E/account effort ranges total 21–37 hours before the reserved
8–9-hour integration buffer, plus external waits. Some assessment/preparation work
is already done, but remediation, native PostgreSQL recovery and first load results
may change those estimates. This is not 21–37 hours to every Stage 9 candidate.
No date or estimate removes the open owner decisions or release-quality gates.

## Continuation checkpoint — October 4, 13:55 America/Chicago (18:55 UTC)

PR24 final head fc7ea99 passed CI 37225178400. Safe 8B continuation now adds local
readiness/instrumentation and native generated-fixture PostgreSQL recovery using
the existing CI service; native restore still needs its published test outcome.
Account/security/spending/merge/deployment decisions and Stage 9 scope remain open.
The original dated checkpoints/ranges remain targets; full production acceptance
and the final integration buffer are preserved. No unrelated gate stops local work.

## Verified checkpoint — October 4, 14:10 America/Chicago (19:10 UTC)

8B local operations draft PR25 source 2e3c150 passed CI 37226798676: 311 Python,
3 SDK, 34 browser plus all migration/lint/type/build gates. Generated PostgreSQL17
fixture recovery executed and verified all public-table rows and game/event/run/report
state; 13 tables/14 rows do not establish production RPO/RTO or load capacity.
Current local readiness/capped telemetry and fixture recovery are verified; the full
8B operational deliverables remain open. Bounded 8C acceptance preparation is saved.
The final documentation follow-up receives a separate current-head CI check.
No new owner decision has arrived; continue independent fixture performance work
and budget design. The production/account/Stage 9 confidence and gates remain as above.

## Performance checkpoint — October 4, 15:05 America/Chicago (20:05 UTC)

PR25 final head 076c82a passed CI 37227215973. Stage8C generated-fixture harness
now measures five workload areas locally, including installed Stockfish; native
PostgreSQL and final browser CI remain upcoming gates. In-process latency is not
hosted capacity. Full 8C still requires outstanding recovery/representative-load
acceptance; 8B production operations and 8A approved remediation also remain open.
8D ledger design can proceed with symbolic-unit tests independently of policy;
live monetary enforcement still needs approved ownership/pricing/unknown-cost rules.
8E hosted onboarding and deferred 2E/6D remain gated. Stage 9 is still unselected.
Keep the dated checkpoints and final 8–9-hour integration buffer; no new approval
or improved all-stages guarantee is inferred from these local results.

## Continuation checkpoint — October 4, 15:35 America/Chicago (20:35 UTC)

8C PR26 reviewed 105eb2a passed CI 37231626012 (324 Python / 2 engine skips);
8D PR27 source 969eb7c passed CI 37231957628 (336 Python / 2 engine skips);
both include native fixtures, 3 SDK, 34 browser and all migration/lint/type/build gates.
PR27's final documentation head c267056 has a separate check pending. The local
engine lifecycle correction adds real interruption recovery and 353 passing tests;
publication remains a separate gate. Generated-only 8C/8D checkpoints are ahead
of discovery targets, but do not close production operations, policy or hosted scope.

Keep the Oct 5 12:00 operational/cost-control target conditional on approved policy;
Oct 5 20:00 account candidate still depends on owner choices/authorization. Oct 6
03:00 representative-performance and 09:00 release-candidate targets depend on
approved topology and integration. Preserve 09:00–17:40 for review/CI/restore/visual
acceptance. Hosted-beta confidence remains conditional/low without decisions; a
tested local candidate is more plausible. Stage 9 all-candidate delivery is unresolved
and unestimated, not silently included in these ranges or excluded from the request.
