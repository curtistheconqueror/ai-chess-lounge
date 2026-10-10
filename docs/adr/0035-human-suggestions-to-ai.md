# ADR 0035: position-bound human suggestions to AI

Status: implemented for the local single-process Lounge; hosted authorization pending.
0034 is reserved for the separate, unrecovered private-beta authentication patch.

An operator may propose one legal UCI move to the active direct/local model seat
while paused. Dragging or selecting squares saves advice, never an authoritative
move. Resume is a separate action. The model retains final choice; the arbiter
validates its output normally. No opening book or tablebase controls the choice.

Store advice in the existing consultation JSON projection with an additive
`direction` field (legacy records default to `ai_to_human`) and an append-only
`human.suggestion` event. Bind it to position version, match revision and full
recipient configuration. Only the immediate resume can carry it forward. Seat
changes, reset, intervening lifecycle actions, clear and replacement invalidate it.
The projection survives restart without a schema migration. An accepted AI move
marks the advice record `played`, meaning the advised turn completed, not that the
AI adopted the proposed move. UI explains this distinction.

Deliver advice through a private internal MoveRequest field into existing provider
prompts. The external runner wire protocol stays unchanged. Stockfish and remote
runners cannot receive advice in this increment. Deterministic practice agents are
explicit fixtures, not claimed model intelligence. Preserve AI-to-human advice.

Record Human-AI Team move metadata and PGN disclosure. Conservatively exclude any
game with human-to-AI advice from unassisted comparison rates, including cleared
advice (past advice remains in public PGN context). Do not store private reasoning.

The Lounge browser opts into `single_game` creation checks. Serialize requests in
one API process and reject creation while any running/paused game exists. The
legacy API and experiment worker remain compatible; this is a local UI workflow,
not a cross-worker resource quota or hosted security boundary. Production quotas,
account ownership and runner permissions still require the separate hosted work.
`start_paused` enables review before dispatch. Existing running matches are never
silently aborted to create another.

Usage display sums only observed fields and shows coverage. Reasoning is separate
and never added to output totals. OpenRouter's response `usage.cost` is preserved
when finite and nonnegative; unknown cost remains unknown. Retries and cancelled
calls can be missing, so these subtotals are not a billing ledger or spend cap.

Verification includes legal/stale/lifecycle/seat fences, restart projection,
independent AI choice, two-agent completion, API creation guard, existing
consultation/provider/persistence tests and responsive drag tests.
