# Stage 8 hardening assessment and release gates

Status: **8A read-only assessment in progress; not a production approval.**
Baseline: Stage 7E source 64f7c2c, final handoff 5baac32a (2026-10-04).
Main remains 087c565; PR18–PR22 are unmerged drafts. No deployment, credential,
permission, paid-service or security-setting change is authorized by this document.

## Scope and trust model

The implemented deployment is a local, single-operator application. Hosted accounts,
per-user visibility and roles are the deferred 2E/6D work. The local development
configuration is not a public-beta configuration.

Protect these assets: provider credentials and spending authority; runner grants;
private match/configuration data; move/event integrity and clocks; persisted games;
and CPU, engine, database and export capacity. Treat browser clients, external runners,
model responses and public labels as untrusted. The API/arbiter authorizes and validates
state transitions. Provider/subscription credentials remain outside public game data.

| Boundary | Existing evidence | Required hosted-release acceptance |
| --- | --- | --- |
| Browser → API / WebSocket | Versioned moves, legal arbiter, idempotency and local deployment | Authenticated identity, object/seat ownership, visibility and origin/session checks on every relevant path |
| Runner → API | Signed proposals, one-match grants, expiry/revocation and fencing tests | Grants bound to authenticated owner; invitation/seat consent; reconnect and revocation across deployment topology |
| Model/provider → arbiter | Structured parsing, legal move checks, bounded retry policy, sanitized failures | Adversarial output/body-size tests, per-owner resource/cost isolation, controlled destinations |
| API → provider / webhook / local engine | Operator configuration, scoped runner transport, engine limits | Egress/redirect/DNS policy review, deployment network isolation, resource/kill-switch tests |
| Store → reports / browser | Public projections, private-text exclusion, stable export checks | Private/public ACL on read/export/stream; tenant isolation and retention policy |
| Operator → deployment / backups | Loopback development setup and versioned migrations | Managed secrets, protected admin actions, backup restore, rollback and incident drills |

These are acceptance areas and known roadmap boundaries, not published exploit
instructions. Handle detailed security findings privately under SECURITY.md.

## Initial verification — October 4, 2026

| Check | Observed result | Coverage limit |
| --- | --- | --- |
| Current tracked-source selected key patterns | No candidate files; only the example environment file is tracked | Pattern matching is not a proof that every kind of secret is absent |
| Reachable local Git history, blobs ≤2 MiB | 632 blobs / 7,640,628 bytes checked; no selected key-pattern candidates | Local reachable refs and selected key/private-key patterns only; no credential files opened |
| Web npm lockfile audit | Zero known advisories reported | Registry data at audit time; not source-code or runtime assurance |
| TypeScript SDK npm lockfile audit | Zero known advisories reported | Same limitation |
| Python locked dependencies, pip-audit 2.10.1 | 54 records; zero known advisories; no skipped records | Pinned files only, with dependency resolution disabled |
| Existing integrated CI on 7E source | 302 Python tests, 3 SDK, 34 browser; both DB migrations, lint/types/build pass | No hosted identity, production load, paid-provider or deployment acceptance is implied |

Audits did not upgrade packages, change production settings, read credential files,
invoke providers, or print candidate secret values. Re-run dependency/secret checks
on the actual release commit; dates and coverage matter.

Existing security-related regressions cover inline-credential rejection, sanitized
provider failures, one-time runner pairing, signed and position-bound proposals,
expiration/revocation races, local MCP target restrictions, bridge environment
isolation, and report privacy/integrity. These do not replace the hosted-user abuse
matrix below.

Batch dispatch already has a shared database coordination lock and a global cap of
four leased jobs. That is separate from provider request-rate policy and monetary
budgets; it does not establish shared spending enforcement.

## Required abuse and isolation matrix

Before a hosted beta, test anonymous, owner, invited player, spectator and moderator
actors against list/read/move/control/analysis/export/stream/runner operations. Include
cross-user and expired/revoked grants, wrong-seat moves, duplicate submissions,
concurrent revocation, unauthorized provider spending, visibility changes, oversized
requests/exports, malformed provider output, outbound-target policy and resource
exhaustion. Verify safe errors and no raw credentials/private model text in logs.

Run controlled fixture-based tests first. Live provider tests require an approved
account and spending ceiling; public network tests require an approved environment.
No production attack or infrastructure scan is part of this initial assessment.

## Decisions needed before security or account changes

See ACCOUNT_AND_RELEASE_DECISIONS.md for a concrete proposed identity/role model,
acceptance criteria and approval boundaries. Identity/database/hosting providers,
initial administrator, visibility defaults, invitation policy and paid-call limits
must be decided explicitly. Supabase is a user-mentioned option, not an assumed
account or purchase. Do not enable public binding until those controls are tested.

8A remains open until findings are reviewed, authorized remediation is verified,
and release risks have an explicit disposition. A clean dependency scan alone does
not close this phase.

## Independent safe continuation

While approval decisions are pending, prepare 8B operator runbooks and offline
backup/restore rehearsal using generated fixtures; design observability with no raw
prompts/credentials; build bounded local 8C load harnesses; and specify 8D budget
reservation/reconciliation semantics. Do not apply retention deletion, change live
credentials, enable new access, run paid workloads or deploy without the relevant gate.

8B–8E still require their full roadmap deliverables. Account work does not disappear
because it was deferred. Stage 9 still needs an owner-selected scope after real use;
see DELIVERY_48H_PLAN.md for the dated target and confidence limits.

## Reference guidance reviewed

OWASP REST Security: HTTPS, endpoint authorization and configured token/claim validation:
https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html

OWASP SSRF Prevention: validate outbound destinations and consider redirect/DNS and
network-layer boundaries, rather than relying on string matching alone:
https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html
