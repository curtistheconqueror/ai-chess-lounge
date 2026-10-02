# Stage 5D live subscription acceptance

Date: 2026-10-02 (America/Chicago).

| Check | Observed result |
| --- | --- |
| Official CLI | Codex CLI 0.160.0 |
| Authentication | CLI status reported ChatGPT login; `forced_login_method=chatgpt` was used for inference |
| Model | gpt-6.1-sol, provider-default effort |
| Seat | Black, subscription_bridge, open_agentic |
| Opponent | Local deterministic test adapter, explicitly scripted f3 then g4 |
| Transport | Local Python sidecar → signed RunnerClient proposals → real FastAPI/SQLite arbiter via ASGI HTTP transport |
| Authorization | One bounded next-match grant; no intervention between moves |
| Live moves | e7e5, d8h4 |
| Terminal result | Checkmate, 0-1; sidecar returned completed with 2 submitted moves |
| Public record | stage5d-live.pgn |

This is a short functional acceptance game, not a playing-strength benchmark.
The CLI chose its own two moves. No Stockfish substitution, fake model response,
API-key fallback, or per-turn human move selection was used. The test used the
real broker, signing, validation, orchestration, persistence, and game rules.
ASGI transport kept the Lounge test local; it did not mock the provider CLI.

## Resolved blocker and correction

The earlier timeout was labeled a usage limit by an overly broad diagnostic
classifier that matched bare digit substrings. That label did not establish a
real HTTP 429 or exhausted account quota. A fresh 120-second retry found connection
failure/reconnect diagnostics, with no explicit HTTP 429 or rate/quota message.

The child environment had removed this hosted environment's required outbound
proxy settings. Preserving its existing credential-free proxy URLs fixed the
connection, and the next live game completed. The bridge still rejects proxy
URLs with userinfo, query strings, fragments, or non-root paths, and still strips
provider API keys and Lounge credentials. No authentication or network policy was
bypassed. Diagnostics now recognize contextual HTTP status codes rather than
bare digits, and distinguish rate limiting from an explicit quota error.

Regression tests cover timestamp/request-ID false positives, actual HTTP status
categories, preserved ordinary proxy routing, and rejected credential-bearing
proxy values. Raw CLI diagnostics and provider credentials are not retained.

This proves this CLI/account/model route worked at the time of the test. It does
not certify future model access, remaining subscription allowance, other providers,
Windows support, or tool-free reasoning. The seat remains open_agentic.
