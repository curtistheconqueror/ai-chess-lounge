# ADR 0015: Bounded provider recovery and operator retry

- **Status:** Accepted
- **Date:** 2026-10-02
- **Owners:** CurtisTheConqueror

## Context

Hosted and local model servers can fail transiently through network errors, rate
limits, or outages. Retrying every failure is unsafe: it can multiply paid calls,
overrun the chess clock, conceal invalid model behavior, or create a loop after the
provider already completed a response. Pausing every transient failure is safe but
unnecessarily brittle for short disruptions.

## Decision

Apply one provider-neutral reliability controller to OpenAI, Anthropic, Google,
OpenRouter, Ollama, and vLLM seats. Transport failures, HTTP 429, and selected
transient HTTP statuses may receive at most two total attempts by default. Backoff
and any accepted `Retry-After` delay must fit inside the original authoritative move
deadline; retries reuse the same immutable `MoveRequest`, position version, and turn
lease.

Authentication and configuration failures, refusals, malformed structured output,
stale identities, and illegal moves are never automatically retried. Repeated
exhausted turns open a per-adapter/model circuit, and a process-local request budget
limits calls per minute. Exhaustion preserves the position and pauses the match with
sanitized metadata.

An operator may call the explicit retry-agent action. It records an immutable
`agent.retry_requested` event, allows one circuit probe, resumes the authoritative
clock, and schedules the same preserved turn. It does not bypass the local request
budget. No policy substitutes an engine move or silently adjudicates a result.

## Consequences

- Short transient failures can recover without browser control or per-attempt input.
- Cost and latency remain bounded, and accepted moves disclose the successful attempt.
- Provider bodies, prompts, credentials, and raw outputs remain absent from events.
- The request budget and circuit are process-local until distributed workers add a
  shared coordination store.
- A completed provider call followed by persistence failure still pauses rather than
  automatically purchasing the position again.

## Verification

Tests cover retryable status classification, `Retry-After`, bounded success and
exhaustion, request-budget rejection, circuit cooldown, audited operator recovery,
non-retryable authentication failures, sanitized events, and the public reliability
status endpoint. Existing lease, clock, concurrency, persistence-failure, and browser
build gates remain required.
