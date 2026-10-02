# AI Chess Lounge player protocol

Protocol version `1.0` is the credential-free contract between the match runner and
every automated seat. The authoritative Pydantic models live in
`services/api/lounge_api/player_protocol.py`; these JSON Schemas are transport-neutral
references for external SDKs and future remote runners.

An adapter receives a `MoveRequest`, returns one `MoveProposal`, and never mutates
match state. The Lounge verifies the echoed request, match, and position identifiers,
checks UCI legality, and commits through the durable turn lease. `plan`, `threat`, and
`confidence` are intentionally generated public summaries—not private reasoning.

Credentials, raw provider responses, prompts, cookies, and subscription sessions are
outside this protocol. Direct API adapters use credential references; subscription
bridges keep provider authorization on the user's machine and receive a scoped Lounge
runner token through the implemented Stage 5A pairing flow. Every value in
`PlayerConfiguration.settings` is public and is rejected unless its adapter registers
it in the core public-settings allowlist.

Remote runners receive the same `MoveRequest` inside `RunnerTurnDelivery` and return
the same `MoveProposal` inside a signed, idempotent `RunnerProposalSubmission`. See
`runner-turn.schema.json`, `runner-proposal-submission.schema.json`, and
[`docs/STAGE_5_EXTERNAL_AGENTS.md`](../../docs/STAGE_5_EXTERNAL_AGENTS.md).

## Adapter checklist

1. Declare a stable `adapter_id`, models, capabilities, and connection mode.
2. Validate configuration without accepting inline credentials.
3. Bind proposals to `request_id`, `match_id`, and `position_version`.
4. Return strict UCI and normalized nullable usage values.
5. Keep public summaries concise and free of hidden reasoning.
6. Treat a stale, expired, or revoked request as non-committable.
