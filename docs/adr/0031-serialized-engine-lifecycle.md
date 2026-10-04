# ADR 0031: serialize UCI process lifecycle

Status: local candidate; published full CI acceptance pending.

## Decision

Keep startup summary, play/analysis and shutdown behind the same service lock.
Drain threaded UCI work when its requester is cancelled, retaining the lock until
the thread ends; repeated cancellation must not let shutdown race the command.
Dispose a process produced by cancelled startup. If cancelled work later fails,
discard its failed handle while preserving the caller's cancellation semantics.
Normalize startup/command failures to public EngineFailure messages, discard failed
handles, and allow a subsequent request to start a fresh service process.

The engine service does not replay an interrupted chess turn itself. The arbiter and
existing manager retry/clock policy still govern any later request and move commit.
A dead-process quit error falls back to transport close. Deterministic fixtures check
startup/failure/cancellation combinations, repeated shutdown and barrier-held commands;
an installed-engine test terminates/reaps a real process and verifies a fresh legal
proposal. The bounded benchmark records explicit service restart after interruption.

## Limits

Python cannot stop an arbitrary thread. Cancellation drains the bounded python-chess
UCI operation rather than abandoning it; engine/driver teardown can outlast a caller's
scenario timer. This is not a hard process supervisor or hosted engine-pool capacity
guarantee. Fixture barriers/timeouts are test limits, not production deadlines.
Public strategy, assistance divisions and authoritative clocks are unchanged.
No provider, credential, account, permission or deployment change is included.
