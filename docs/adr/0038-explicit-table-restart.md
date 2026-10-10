# ADR 0038: Explicit table restart preserves archives and targets one game

Status: accepted for local/private practice, October 10, 2026.

## Context

A viewer can be reviewing an aborted game while a different paused game owns
the shared table. New match correctly rejects creation, but the distant abort
controls and generic conflict message do not explain which game blocks play.
Reset could also revive a finished game without taking the creation lock.

## Decision

Expose End match and End and start new beside the board. Confirmation names the
selected game and participants. It pins the game's ID and generation; a later
reset invalidates that confirmation. Restart archives that game with Abort,
then requests a normal single-game creation. These are deliberately two steps:
if another tab wins creation, or another legacy live game remains, show that
game and stop. Never sweep or silently abort other games. Failed creation leaves
the original archive intact and reports the failure.

Abort accepts an optional expected_generation field, preserving existing clients.
Repeated abort, or abort after completion, returns the authoritative terminal
snapshot without changing its result/history. It still interrupts in-flight
agents before waiting for their game lock. Reset through the HTTP API rejects
finished archives; users start a new game instead. Active reset shares the
single-game creation lock and refuses when another table is live. Manager-level
reset remains available to internal workflows. Snapshot and agent protocol
schemas are unchanged; the request field is additive.

Live-table discovery checks all candidate rows, so five recently expired rows
cannot hide an older paused blocker. Persistence and generation/revision guards
remain authoritative. Browser reconnect and refresh never revive an archive.

## Limits and verification

The creation lock applies to the existing single-process local/private runtime.
It is not a distributed single-table lease for a future hosted multi-worker
deployment. Explicit multi-game API/batch workflows retain their existing scope.

Disposable tests cover two tabs ending/restarting, concurrent creation, repeated
abort, stale generation confirmation, old reset/resume attempts, another live
blocker, clock expiry, and persisted status after a process restart. Private
user games are preserved; private UI verification reads state and cancels the
confirmation dialog without submitting an end action.
