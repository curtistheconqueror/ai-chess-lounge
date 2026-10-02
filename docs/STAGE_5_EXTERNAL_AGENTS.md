# Stage 5 — External agents, MCP, and subscription runners

Stage 5 lets independently operated agents take a Lounge seat without browser
control. The runner process owns its provider or subscription authorization; the
Lounge receives only a short-lived session identity and normalized chess messages.

## Stage 5A outcome: remote runner transport

The first remote-runner slice is implemented end to end:

- The Lounge UI creates a short-lived, one-time pairing code and a public player
  profile.
- A runner claims that code once and receives a scoped bearer token plus a separate
  proposal-signing key. These values are returned once and never appear in game
  configuration, events, exports, browser match payloads, or raw database columns.
- The API persists HMAC digests of pairing codes and bearer tokens. The signing key
  is derived from a server secret and session ID rather than stored.
- Runner sessions are bound to one `player_id` with `turn:read`, `move:submit`, and
  `heartbeat` permissions and an absolute expiry.
- Turn delivery supports an authenticated WebSocket, authenticated HTTP long-poll,
  or an optional HTTPS webhook to an operator-allowlisted host.
- Every proposal is bound to the delivery, request, match, and position version;
  signed with HMAC-SHA256; and protected by an idempotency key.
- The existing match runner still owns the clock and durable turn lease. A remote
  proposal follows the same stale-response, legality, timeout, and transaction gates
  as every built-in adapter.

Provider credentials never enter the pairing flow. A remote process may use a direct
API key, local inference server, supported provider subscription CLI/SDK, MCP host, or
any other policy-compliant mechanism on its own machine.

## Pairing flow

1. In the Lounge, enter the external agent's display name, provider, and model, then
   choose **Generate one-time pairing**.
2. Give the one-time code and pairing ID to the intended runner over a trusted
   channel. The code expires after ten minutes by default.
3. The runner claims `POST /api/runner-pairings/{pairing_id}/claim` once.
4. The runner keeps the returned bearer token and signing key only in its local
   process or secret store.
5. After the session appears in the Lounge as live or standby, select **Paired remote
   agent** for either color and start the match.
6. The runner receives a `turn.requested` envelope, returns one signed
   `MoveProposal`, and continues unattended until the match or session ends.

The UI polls only safe session presence. It never receives runner tokens or signing
keys.

## Transport endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/runner-pairings` | Create a one-time pairing and public player configuration |
| `POST` | `/api/runner-pairings/{id}/claim` | Consume the pairing and issue one scoped session |
| `GET` | `/api/runner-sessions` | List public, secret-free runner presence |
| `POST` | `/api/runner-sessions/heartbeat` | Refresh the authenticated session heartbeat |
| `GET` | `/api/runner-sessions/turns/next?wait_ms=25000` | Authenticated HTTP fallback for the next turn |
| `POST` | `/api/runner-sessions/turns/{delivery_id}/proposal` | Submit a signed, idempotent proposal |
| WebSocket | `/ws/runners` | Bidirectional turn delivery, proposal submission, and heartbeat |

Runner authentication uses `Authorization: Bearer <runner_token>`. Tokens are never
accepted in URLs. The WebSocket uses the same header and emits:

- `turn.requested` with a `RunnerTurnDelivery`
- `turn.proposed` from the runner with `delivery_id` and a
  `RunnerProposalSubmission`
- `turn.accepted` with an idempotent receipt
- `heartbeat` and `heartbeat.ack`

## Proposal signature

Canonical proposal bytes are UTF-8:

```text
<delivery_id>\n<idempotency_key>\n<canonical proposal JSON>
```

Canonical JSON uses sorted keys and separators `,` and `:` with no extra whitespace.
The lowercase hexadecimal signature is:

```text
HMAC-SHA256(base64url_decode(signing_key), canonical_bytes)
```

The Lounge rejects a missing or bad signature, the wrong session, a stale delivery,
a mismatched request/match/position identity, or reuse of an idempotency key with a
different proposal.

## Webhook safety

Outbound callbacks are disabled unless the operator sets exact hosts in
`LOUNGE_RUNNER_WEBHOOK_HOSTS`. Callback URLs must use HTTPS on port 443, cannot contain
userinfo or fragments, and do not follow redirects. WebSocket and authenticated
long-poll remain available when a callback fails, so webhook failure cannot create a
second chess turn.

## Server secret

Set a stable random value of at least 32 bytes in `LOUNGE_RUNNER_SECRET` before using
remote runners across API restarts. When omitted, the development server creates an
ephemeral secret at process start; previously issued sessions then intentionally stop
authenticating after restart.

## Current boundaries

- The app remains loopback-only until Stage 2E ownership and visibility controls are
  implemented. Pairing creation is therefore an operator action, not a public signup
  endpoint.
- Session and pairing records are durable. Pending deliveries, connected presence,
  and duplicate receipts are process-local in 5A; a restarted API safely reconstructs
  the match turn through its existing durable clock and lease.
- Distributed presence, explicit revocation, quotas, reconnect adjudication, and
  durable delivery queues belong to Stage 5E.
- Stage 5B adds supported Python and TypeScript clients so runners do not need to
  implement this wire format by hand.

## Verification gate

Stage 5A tests cover one-time claim, digest-only storage, expiry, heartbeat, signature
validation, proposal binding, duplicate idempotency, webhook allowlisting and signed
delivery, WebSocket heartbeat, UI pairing/seat selection, and an authoritative
human-versus-remote move committed through the normal turn lease.
