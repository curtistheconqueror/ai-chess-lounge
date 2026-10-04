# Account and release decisions for 2E / 6D / Stage 8

Status: **Proposal for owner review. No security or deployment change is applied.**
This keeps the standalone, provider-neutral Lounge design. Accounts identify humans;
API-key connections and authorized local subscription bridges remain separate ways
to operate a player's agent.

## Confirmed funding model; implementation choices remain open

The Lounge owner funds application hosting, database/storage and Lounge compute.
Players supply and fund their own agents, provider API accounts or supported
subscriptions. No owner-funded shared model key is the default product design.
Access is free for humans and bots for now: no Lounge subscription/paywall.
Supabase is the selected hosted backend direction. Its account/project, region, plan,
amount and access remain unverified; direction is not purchase/deployment authorization.

| Route | Inference responsibility | Lounge responsibility |
| --- | --- | --- |
| External SDK/MCP runner or local subscription bridge | Player operates and pays for their provider/agent; credentials remain local | Validate scoped proposals; bound requests, spectators, queue/database and any Lounge engine compute |
| Lounge dispatch using a player's API connection | Player funds that connection; approved per-user ownership and paid-call limits required | Reserve/reconcile actual paid attempts, enforce shared request limits and stop authority |
| Human/reference/Stockfish seat | No external model inference is implied | Bound hosting, database, spectator and local engine resources |

A subscription does not imply provider API access. Use only its supported
agent/CLI route; the existing bridge proves one route, not every subscription.
External runner telemetry is not a trusted billing meter. Its unknown provider cost
must not be recorded as zero or charged to an assumed owner model budget.

## Proposed identity and ownership contract

Use a managed identity provider with server-side verification of signed identity tokens
and configured issuer/audience/expiry. Do not build password storage into the Lounge.
Supabase is the selected backend direction for database/auth planning; no account,
project, billing plan, credential or working integration is assumed. The Python/API,
WebSocket, worker and Stockfish runtime host remains to be selected.

Store application ownership and permissions in the Lounge database. Every match,
agent connection, experiment, run and private export has an owner/access scope. A
provider connection belongs to its user; owning a match never grants permission to
spend an opponent's key. Public manifests contain only approved public configuration,
not private connection references or secrets.

An initial administrator must be explicitly assigned to an approved identity.
The first person to visit must not automatically become administrator. Hosted mode
must fail closed when its required identity/secret configuration is incomplete.
The existing local operator mode remains distinct until an authorized rollout.

## Proposed minimum role matrix

| Actor | Read | Play / manage | Provider authority |
| --- | --- | --- | --- |
| Anonymous | Explicitly public spectator data only | None | None |
| Invited spectator | Authorized match view/replay | None | None |
| Seated player | Authorized match/configuration and own connections | Own seat; agreed game actions; attach own agent under scoped grant | Own approved connection and budget only |
| Match owner | Match view and explicitly permitted exports | Invitations, lifecycle controls and consented visibility changes; no impersonation of another seat | Cannot use another player's connection merely by owning the match |
| Moderator | Only explicitly assigned moderation scope | Audited moderation actions with stated reasons | No credential access or implicit spending authority |
| Operator | Deployment administration under separate access | Audited operational controls and emergency stop | Approved operational budget/configuration only |

Role checks apply to HTTP reads/writes, downloads, WebSockets and runner control paths.
A URL or UUID is an identifier, not sufficient permission. Private-to-public publication
requires a defined participant-consent policy. Invite secrets are one-time, short-lived,
hashed in storage and absent from logs; transport and expiry values need review.

## Provider and runner decisions

Keep provider credentials outside public game/configuration records. User-local
runners already provide a BYO route without server-held provider keys.
If Lounge-dispatched player API connections are included in the hosted beta, approve
per-user secret storage/ownership separately; do not use a shared operator key for
all participants. Hosted route scope remains a decision.
Subscription credentials stay local through supported provider routes.

Current remote grants authorize one match. Consultation and experiment batches need
separate purpose/scope/expiry/revocation semantics; they are not covered by a generic
account login. Distributed runner routing/delivery needs either implementation and
verification or an explicit single-worker beta limitation accepted by the owner.

## Cost-control acceptance before paid multi-user use

For Lounge-dispatched paid calls, the player is the inference funding party. Approve
the mapping from authenticated player to connection/budget; specify currency, period,
concurrent reservation rules, maximum
request/output limits and emergency stop behavior. Reserve before dispatch, reconcile
idempotently, and retain an uncertain reservation after a possibly billable timeout.
Do not treat missing usage or cost as zero. Provider bills may include work whose
response was lost; an application estimate is not a billing guarantee. Cross-process
limits must use shared state, rather than each worker granting its own full allowance.

Choose approved spending ceilings and handling of unknown pricing before live tests.
No numeric monetary budget is selected by this proposal. External-agent onboarding
does not depend on selecting an owner inference budget or implementing a provider
billing meter in the Lounge. It still needs approved abuse/request/compute quotas,
hosted identity/isolation and scoped access; existing turn limits are not full quotas.
Infrastructure account/project/plan/spending limits and provider paid-call limits are separate.

## Concrete authorization packet

| Owner decision | Reviewable implementation target | Acceptance evidence required |
| --- | --- | --- |
| Supabase project/auth configuration, runtime host and approved admin | Configured managed identity, persisted ownership, role checks and migrations | Two-user isolation, wrong-role/seat rejection, revoked/expired sessions, restart recovery |
| Security changes and private/public policy | Consistent API/WebSocket/export checks, invitations and participant consent | Complete actor/action matrix, origin/session tests, secret-safe errors |
| Hosted route scope; player connection ownership/paid-call policy when dispatched by Lounge; external-agent abuse/compute quotas | Scoped connections, durable reservations, cross-process quotas and emergency stop | Concurrent overspend prevention, retry/timeout accounting, no cross-user key use |
| Supported deployment topology | Approved worker count/routing, engine limits, TLS/network/secret configuration | Load results on declared hardware, restore/rollback rehearsal, reconnect tests |
| Merge and release approval | Reviewed dependent PR stack, exact release SHA and standalone URL | Green current-head checks, desktop/mobile smoke test, onboarding and connection test |
| Deferred feature / Stage 9 scope | Explicit list of included deliverables and remaining backlog | No partial or disabled capability described as shipped |

This packet requests decisions, not immediate credentials. Do not send secrets in chat
or publish them in a PR. Account creation, credentials, permissions, purchases and
public deployment remain separate authorized actions. Safe read-only review and offline
fixture work can continue while decisions are pending.

## Safe continuation versus actual gates

Resolved: owner-versus-player funding responsibilities and absence of a default
owner model subsidy. Already implemented: local BYO pairing, Python/TypeScript SDKs,
stdio MCP and one-match local subscription bridge. Reuse and verify these paths;
do not add duplicate adapters, expand grants or treat local tests as hosted access.
Safe work includes source/fixture acceptance and route-specific onboarding/docs.
Unresolved: Supabase account/project/plan/amount/access and application runtime host;
deployment approval; identity/admin,
visibility/invites/access changes; numeric infrastructure/abuse quotas; hosted route
scope and per-user secret/paid-limit policy if Lounge dispatches; merge/release;
distributed/purpose-scope/deferred requirements and Stage9 selection.

See HOSTED_RELEASE_PATH.md for verified local versus hosted status, setup timing,
Supabase/runtime boundaries and conditional estimates. Free access does not mean
unauthenticated access or unlimited resource use; no payment subsystem is needed now.
