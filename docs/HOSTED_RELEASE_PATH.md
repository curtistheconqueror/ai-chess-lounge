# Free BYO Lounge: local milestone and hosted release path

Updated October 4, 2026. This is a planning/verified-source checkpoint, not public
release, account setup or permission to merge/deploy/change security or spend.

## Confirmed product decisions

Human and bot access is free for now. No Lounge subscription, payment gateway or
paywall is required. Players bring and fund their own agents/API accounts/supported
subscriptions; no shared owner-funded model key is the default. The owner funds
Lounge infrastructure. Supabase is the selected backend direction; the account,
project, plan, region, administrator and this session's access are not verified.
Subscription entitlement does not imply API entitlement. Routes remain provider-neutral.

## What already works versus what is still a draft

| Milestone | Evidence / actual boundary |
| --- | --- |
| First playable local Lounge | Main remains Stage 6C at 087c565. Human, deterministic reference, Stockfish, direct provider adapters, clocks, strategy panels, PGN/FEN, replay/pause and human takeover/consultation implemented |
| AI versus AI | Two automated seats run without browser control; direct cross-provider/local-model connections exist but require the operator's configured supported accounts. Stockfish needs an installed engine. No claim that every current frontier model/account works |
| Bring your own external agent | Paired one-match/seat signed SDK/MCP/HTTP/WS runner path keeps provider authorization local; one supported local Codex subscription bridge.73 warning-strict existing runner/SDK/MCP/bridge tests passed in this checkpoint; fake acceptance is not live provider entitlement proof |
| Model Lab | PR18–22 dependent drafts cover plans/effort sweeps, durable batches, formats, honest metrics and exports; final heads verified but unmerged |
| Hardening/readiness | PR23–30 drafts contain assessment, generated restore, local readiness/telemetry, bounded ASGI/loopback/queue/native database and real local engine evidence, budget contract/test oracle and beta packet; production phases remain open |
| Current integrated candidate | PR29 source and final docs plus PR30 source/final pickup independently passed full CI:357 Python/3 absent-engine skips,3 SDK,34 browser/76 intentional viewport skips, both migrations/native fixtures/restore/lint/types/build. Desktop/phone PR29 evidence inspected. This is not an approved merged release |
| Hosted two-person Lounge | Not yet deployed.2E/6D authenticated owners/roles/invites, object/seat visibility/isolation, approved resource controls and actual infrastructure acceptance remain |

The first-playable milestone is already reached locally. Wrapping up all hosted
release work is a different milestone; no fictional percentage or all-stages claim.

## Supabase and the application runtime

Supabase provides PostgreSQL and Auth capabilities. Its Realtime service can stream
changes/broadcasts, but the Lounge currently owns its versioned socket/delivery and
arbiter protocol in FastAPI; Realtime is not a drop-in replacement. The repository
Dockerfile runs Python/Uvicorn, bundles the React build and installs Stockfish. Its
compose file is a loopback local PostgreSQL deployment, not a Supabase deployment.

Therefore the existing architecture needs a persistent application/container runtime
for FastAPI/WebSockets, match/queue scheduling and a native Stockfish subprocess.
Supabase Edge Functions use Deno and bounded worker duration/CPU; they are not the
unchanged runtime for this Python/UCI service. This is an inference from the repo
and official runtime documentation, not a claim Supabase lacks WebSocket features.
The bundled frontend can be served by the application runtime; choosing a separate
static frontend host/domain is optional topology work, not a mandated extra vendor.

Official references reviewed October 4,2026:
- https://supabase.com/docs/guides/getting-started/architecture
- https://supabase.com/docs/guides/functions/limits

## Access findings and when setup is needed

This session exposes no Supabase tool/connector and no tool-search capability. No
Supabase dashboard session, account/project, credentials or permissions were probed.
Claude's access does not establish access here. Repository native PostgreSQL tests
prove generated PostgreSQL fixtures, not connection to an actual Supabase project.

Owner setup is genuinely needed before real Supabase Auth/token/database integration
acceptance: identify or create the intended project through separately authorized
setup, choose region/plan/administrator and approved login/visibility policies, then
provide approved connection/configuration through a secure route. Do not send secrets
in chat or public PRs. Project/credential creation, billing/terms and permissions remain
separate gates. Local play and safe generated acceptance do not require that setup.

## Concrete remaining sequence and conditional estimates

Engineering/validation estimates below exclude owner decisions, external setup waits
and newly discovered findings. They are ranges, not a promise or permission.

| Next work | Estimated effort | Required dependency / exit evidence |
| --- | --- | --- |
| Review/integrate the retained draft train |2–4h| Merge approval, deliberate dependent-base retargeting, current integrated CI and durable pickup branches |
|2E/6D Supabase identity/ownership/invitations|6–12h| Approved project/auth/admin/access choices; HTTP/WS/export/runner two-user isolation, revocation and restart tests |
| Production remediation/operations and all-route resource controls|4–8h| Reviewed security changes, numeric abuse/request/compute limits and runtime topology; shared limits, operator/backup/alert/retention acceptance |
| Representative hosted performance and recovery|3–5h| Declared runtime/Supabase hardware/plan/TLS/proxy; sustained spectator/engine/queue/database load, restore/rollback and reconnect |
| Hosted onboarding, connection/exhibition and release checks|3–5h| Approved deployment/URL, scoped supported routes, desktop/phone acceptance, incident/feedback owner |
| Final integrated review/CI/restore/visual buffer|8–9h reserved| Failed gates delay launch; no auth/restore/billing uncertainty test shortcuts |

Roughly 18–34h engineering plus8–9h buffer for the hosted BYO path, subject to route
and deferred-scope acceptance. If hosted Lounge-dispatched player API connections
are included, add approximately 3–6h for shared monetary reservations/rates and
paid-boundary integration/validation, after player ownership/pricing/unknown-cost and
credential policy approval. External agents do not need that provider monetary ledger;
they still need resource/access controls. Do not silently choose initial route scope.

Target remains October 6,2026 at 17:40 UTC (12:40PM America/Chicago). Retain the
October 6 09:00–17:40UTC review buffer. The optimistic path can fit if decisions/setup
arrive promptly; the upper ranges and waits can exceed it. Local tested-candidate
confidence is higher than hosted release confidence. Supabase direction/free/BYO
clarifications remove ambiguity, not account/security/deploy acceptance.

Negotiated draws, purpose-scoped adviser/batch grants, distributed routing/delivery,
withheld-clock/adaptive effort, ACPL/strategic-coherence scope and provider route
validation remain explicit in DELIVERY_48H_PLAN.md. Stage 9 has eight unselected
post-use candidates; it is not estimated or silently excluded by the ranges above.

## Authorized safe work and real decisions

Reuse existing BYO adapters/clients; verify local contracts, improve truthful route
onboarding/docs, preserve branches/evidence and review generated acceptance. No new
adapter or billing prototype is needed just because funding was clarified. Hosted
access-control changes, Supabase account/project/credentials, runtime selection/setup,
quotas/policy, merges/deployment and Stage 9 scope still need their applicable decisions.
See ACCOUNT_AND_RELEASE_DECISIONS.md and BETA_READINESS.md for the reviewable packet.
