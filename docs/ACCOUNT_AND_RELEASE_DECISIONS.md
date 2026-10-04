# Account and release decisions for 2E / 6D / Stage 8

Status: **Proposal for owner review. No security or deployment change is applied.**
This keeps the standalone, provider-neutral Lounge design. Accounts identify humans;
API-key connections and authorized local subscription bridges remain separate ways
to operate a player's agent.

## Proposed identity and ownership contract

Use a managed identity provider with server-side verification of signed identity tokens
and configured issuer/audience/expiry. Do not build password storage into the Lounge.
The identity/database/hosting vendors are still undecided. Supabase is one option the
owner mentioned; no account, billing plan or credential is assumed.

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

Keep provider credentials outside public game/configuration records. Choose either
an approved per-user secret-storage integration or user-local runners for the initial
multi-user beta; do not silently use a shared operator key for all participants.
Subscription credentials stay local through supported provider routes.

Current remote grants authorize one match. Consultation and experiment batches need
separate purpose/scope/expiry/revocation semantics; they are not covered by a generic
account login. Distributed runner routing/delivery needs either implementation and
verification or an explicit single-worker beta limitation accepted by the owner.

## Cost-control acceptance before paid multi-user use

Specify the budget owner, currency, period, concurrent reservation rules, maximum
request/output limits and emergency stop behavior. Reserve before dispatch, reconcile
idempotently, and retain an uncertain reservation after a possibly billable timeout.
Do not treat missing usage or cost as zero. Provider bills may include work whose
response was lost; an application estimate is not a billing guarantee. Cross-process
limits must use shared state, rather than each worker granting its own full allowance.

Choose approved spending ceilings and handling of unknown pricing before live tests.
No numeric monetary budget is selected by this proposal.

## Concrete authorization packet

| Owner decision | Reviewable implementation target | Acceptance evidence required |
| --- | --- | --- |
| Identity/database/hosting choice and approved admin | Configured managed identity, persisted ownership, role checks and migrations | Two-user isolation, wrong-role/seat rejection, revoked/expired sessions, restart recovery |
| Security changes and private/public policy | Consistent API/WebSocket/export checks, invitations and participant consent | Complete actor/action matrix, origin/session tests, secret-safe errors |
| Per-user provider connection model and budget policy | Scoped connections, durable reservations, cross-process quotas and emergency stop | Concurrent overspend prevention, retry/timeout accounting, no cross-user key use |
| Supported deployment topology | Approved worker count/routing, engine limits, TLS/network/secret configuration | Load results on declared hardware, restore/rollback rehearsal, reconnect tests |
| Merge and release approval | Reviewed dependent PR stack, exact release SHA and standalone URL | Green current-head checks, desktop/mobile smoke test, onboarding and connection test |
| Deferred feature / Stage 9 scope | Explicit list of included deliverables and remaining backlog | No partial or disabled capability described as shipped |

This packet requests decisions, not immediate credentials. Do not send secrets in chat
or publish them in a PR. Account creation, credentials, permissions, purchases and
public deployment remain separate authorized actions. Safe read-only review and offline
fixture work can continue while decisions are pending.
