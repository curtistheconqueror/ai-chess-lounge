# ADR 0003: Provider-neutral player protocol

- **Status:** Accepted
- **Date:** 2026-09-30
- **Owners:** CurtisTheConqueror

## Context

Providers expose different APIs, effort controls, structured-output mechanisms,
usage fields, and authentication routes. The chess domain must not contain branches
for every provider or assume that one provider's reasoning controls are universal.

## Decision

All computer-controlled seats implement a versioned `PlayerAdapter` contract around
normalized `MoveRequest` and `MoveProposal` schemas. Adapters declare capabilities,
validate configurations, choose moves, normalize usage, and report health.

The protocol records exact provider parameters while the UI may offer a normalized
Fast/Balanced/Deep/Maximum control. Unsupported choices are disabled. Stockfish,
scripted test agents, hosted models, local models, and remote runners use the same
match-facing contract.

## Consequences

- The match runner remains independent of providers.
- Adapter contract tests are required for every integration.
- Provider feature drift is isolated but still requires active maintenance.
- Normalized effort labels cannot be treated as identical compute across providers.

## Alternatives considered

- Direct provider calls from the match domain: rejected because it couples integrity
  code to volatile APIs.
- OpenAI-compatible HTTP as the only protocol: rejected because it cannot faithfully
  represent every provider, remote runner, or engine capability.

## Verification

The deterministic test adapter, Stockfish adapter, and first hosted-model adapter
must complete the same contract suite and unattended game fixture.
