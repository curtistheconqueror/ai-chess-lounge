# ADR 0022: Explicit human consultation

Status: accepted for Stage 6C.

## Decision

Consultation is a separate operation from an automated seat turn. A revision-bound
request is allowed only for the human side to move in a running match. It appends a
consultation.requested event and a persisted projection before dispatching one
background job. The board, position version, seat configuration and turn-start clock
remain unchanged. A second pending request cannot pass the revision/pending guards.
Migration 0009 adds nullable JSON consultation history to matches.

The job uses the existing adapter registry, legal-move validation, fenced lease and
bounded provider retry/rate/circuit policy. It never applies a move. It polls the
current revision while thinking; a move, pause, takeover, reset, terminal action or
cancellation invalidates the result. Publication uses database CAS under the game
lock. Advice failures never pause a playable human turn. The request deadline is
capped at 30 seconds and at the remaining chess time; the clock continues throughout.

The UI shows public plan/threat, configuration, latency and reported usage/cost. A
separate confirmation submits a normal human move carrying consultation ID and
revision; the server checks both under the move lock. Manual board moves remain
available and may ignore the suggestion. Consultation request/result/cancellation
and explicit use are recorded; PGN discloses Human-AI Team exhibition assistance.
Reset starts a fresh history projection while preserving immutable past events.

## Recovery and limits

Graceful shutdown cancels and records this worker's owned pending consultations.
An abrupt crash does not redispatch possibly billable work automatically. A pending
record can be explicitly cancelled; after its original deadline it is shown stale
and a fresh request is allowed. The browser refreshes at that deadline. Startup must
not mark another worker's live request orphaned. Provider budgets remain process-local
as in Stage 3F; multiuser quotas are later account/deployment work.

Stockfish advice must disclose engine assistance. Direct hosted/local adapters and
the deterministic practice adviser are supported. Remote runner/MCP/subscription
match-seat grants are deliberately not reused as consultation grants; remote advisers
need a future purpose-scoped authorization contract. This preserves existing runner
trust boundaries. No model/provider protocol fields or credentials are exposed.
