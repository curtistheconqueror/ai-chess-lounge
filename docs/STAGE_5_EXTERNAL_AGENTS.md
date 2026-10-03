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

## Stage 5B outcome: runner SDKs

Reference clients now make the safe HTTP runner path a small move-handler integration:

| Package | Runtime | Included behavior |
| --- | --- | --- |
| `ai-chess-lounge-runner` | Python 3.12+ | Async pairing, heartbeat, long-poll, bound proposal builder, HMAC signing, idempotent submission retry, sample bot |
| `@ai-chess-lounge/runner-sdk` | Node 24+ or Web Crypto runtime | Pairing, heartbeat, long-poll, bound proposal builder, cross-language canonical signing, idempotent submission retry, sample bot |

Both clients reject plaintext HTTP for non-loopback servers, keep bearer tokens out of
URLs, default the idempotency key to the immutable delivery ID, and reuse the exact
same body if an uncertain network failure requires a submission retry. They do not
retry pairing claims because a lost successful claim response cannot safely consume
the one-time code twice.

Install and run the Python Legal Assist sample:

```bash
python -m pip install -e packages/runner-sdk-python
lounge-sample-bot --base-url http://127.0.0.1:8000 --pairing-id PAIRING_ID
```

Or run the TypeScript sample:

```bash
cd packages/runner-sdk-typescript
npm ci && npm run build
npm run sample -- --base-url http://127.0.0.1:8000 --pairing-id PAIRING_ID
```

Each command prompts for the short-lived pairing code. The deterministic sample takes
the first disclosed legal move and is a transport demonstration, not a chess-strength
claim. A real runner supplies its own synchronous or asynchronous move handler and may
call any provider, local model, policy-compliant subscription SDK, or agent workflow.

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

Canonical JSON uses sorted keys, ASCII JSON string escaping, separators `,` and `:`
with no extra whitespace, and finite floating-point values expanded to plain decimal
notation without an exponent or insignificant trailing zeroes. This last rule keeps a
cost such as `0.0000123` identical across Python and JavaScript serializers. The
lowercase hexadecimal signature is:

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
- Stage 5E adds explicit revocation, durable match/turn limits, and reconnect rules.
  Distributed presence/routing and durable delivery queues remain deferred.
- The reference SDKs use authenticated HTTP long-poll. WebSocket and allowlisted
  webhook transports remain available for custom runners; distributed delivery and
  delivery persistence beyond restart remains deferred.
- Stage 5C provides a local stdio MCP facade and Stage 5D a verified Codex
  subscription bridge; host permission policies remain under operator control.

## Verification gate

Stage 5A tests cover one-time claim, digest-only storage, expiry, heartbeat, signature
validation, proposal binding, duplicate idempotency, webhook allowlisting and signed
delivery, WebSocket heartbeat, UI pairing/seat selection, and an authoritative
human-versus-remote move committed through the normal turn lease.

Stage 5B adds Python and TypeScript contract suites for protocol parsing, secret-safe
client surfaces, exact Unicode canonicalization, cross-language HMAC vectors, HTTPS
enforcement, request binding, encoded pairing IDs, and same-payload submission retry.

## Stage 5C outcome: MCP facade

The optional `packages/mcp-server` package exposes join, bounded turn polling, signed
move submission, watch, heartbeat, and opt-in human/remote game creation. Snapshot,
FEN and PGN resources use the same authoritative API. Each process owns one paired
identity; tokens and signing keys never enter MCP tool results. Pure-reasoning
players cannot obtain legal-move or engine assistance through watch/resources.

See [installation and host configuration](../packages/mcp-server/README.md). The
bridge accepts loopback API targets only and uses stdio, not a public HTTP endpoint.
No provider subscription is required by the facade; a host supplies its own authorized
model connection. Host trust settings govern whether per-tool approval is required.

Verification includes a full two-client checkmate game, real stdio discovery,
resource exports, duplicate/conflicting proposals, stale/illegal moves, and secret
redaction. The match manager still decides whether a received proposal can commit.

## Stage 5E outcome: match trust controls

Each pairing authorizes the next dispatched match and one color only. The server
persists that scope, reset generation, dispatch count, and expiry. Pair again for a
new match or reset. The UI exposes maximum turn requests and authorization minutes;
these are authorization limits, not chess-clock controls or dollar budgets.
Already-bound sessions are removed from the new-game seat selector.

The **Revoke access** button prevents further authorized delivery/submission and
fences any remote move not yet committed. Revocation does not erase earlier moves.
Operator endpoints (local deployment only):

| Method | Path | Behavior |
| --- | --- | --- |
| POST | `/api/runner-sessions/{id}/revoke` | Idempotent session and match-access revocation |
| GET | `/api/runner-sessions/{id}/audit` | Latest 200 ordered, credential-free trust events |

A dropped HTTP response or socket reconnect receives the same pending delivery and
deadline. Session/grant expiry, revocation, pause, terminal state, reset, and stale
position checks apply before replay and submission. Reconnects do not grant extra
clock time. A missed adapter deadline pauses; actual chess-clock expiration is
adjudicated by the existing arbiter. Explicit operator adjudication remains available.

Migration `0006_runner_trust` adds grant/audit tables. Apply `alembic upgrade head`
before starting an existing installation. Session revocation and committed moves
serialize transactionally. Restart preserves grants, counts, and audit events;
transport queues/receipts remain process-local, and distributed routing is deferred.
See [ADR 0019](adr/0019-runner-match-trust.md) for precise lifecycle semantics.
