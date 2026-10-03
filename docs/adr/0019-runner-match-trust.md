# ADR 0019: Durable one-match runner authorization

Status: Accepted, Stage 5E.

## Decision

A pairing authorizes one exact player profile for its next dispatched match and
seat. The first current turn binds a durable grant to session, match ID, reset
generation, and color. Another match, color, or reset requires a new pairing.
The UI states this before authorization. Limits are public profile settings:
`max_turns` (default 500, maximum 2000) and `match_ttl_ms` (default four hours,
maximum one day). Grant expiry cannot exceed session expiry. Each dispatch counts,
including a fresh dispatch after a restart or operator retry. Replaying an existing
delivery and idempotently resubmitting it do not consume another turn.

Grant reservation checks current position version, internal lifecycle revision, running lifecycle, and side
before binding. Session-row write locks serialize first binding, revocation, and
final move commit on SQLite and PostgreSQL. Move commit checks grant scope and
expiry in the same database transaction as the authoritative board write. Revoking
access after proposal receipt can therefore still prevent that move committing.
A committed move remains valid if it won the transaction race before revocation.

## Transport and lifecycle

HTTP reconnects replay the pending delivery with unchanged identity and deadline.
A new WebSocket also sees the pending turn; one connection suppresses repeated
notifications for that same delivery. Authentication and grant checks apply again
before delivery and submission, including the internal lifecycle revision fence so
a pre-pause delivery cannot revive after resume. Idle polling rechecks session validity at most one
second later. An in-process revoke wakes pending turns; another process observes
revocation on its next authenticated action. Callback failure has HTTP recovery.

Disconnecting never pauses or refunds the chess clock. Reconnect is allowed within
the original deadline. Missing a request deadline pauses through the existing
adapter-failure policy; actual chess-clock expiration follows the arbiter's timeout
result, including its draw rules. An operator may adjudicate or abort explicitly.
Revocation is not an automatic loss. No replacement engine move is manufactured.
Grant time continues during pauses. A restart reconstructs a fresh request through
the durable turn lease; pending transport messages and receipts are not durable.
The grant and counts survive. Distributed delivery routing remains deferred.

## Audit and deployment boundary

Append-only runner audit rows record session claim, match authorization, dispatch,
move commit, and revocation. They contain only IDs, fixed event kinds, and timestamps.
The operator audit endpoint returns the latest 200 ordered rows. No provider
credentials, bearer tokens, signing keys, or private reasoning enter these events.

Pairing, audit, and revoke are local operator endpoints, like match controls.
This is not multiuser authentication. Continue loopback-only deployment until
account ownership/visibility authorization is implemented. A dispatch already authorized and in flight may arrive after revocation, but cannot
commit after revoke wins the session lock. Concurrent creation with the same pairing
may create two games; only the first dispatched current turn obtains authorization,
and the other pauses without a runner move. Use a separate pairing for each game.

The move wire protocol
remains 1.0; scoped authorization is a server policy, with additive public status
and profile fields. Existing sessions receive the same one-match policy on upgrade.
