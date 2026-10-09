# Stockfish strength

The board's strength controls configure the **next match**. Choose Stockfish for
one or both seats, choose a target Elo or Full strength, then click New match.
The chosen value survives browser reloads. The separate Current match line shows
the match's saved settings, so changing the control cannot silently relabel or
alter an ongoing game. For an existing game, pause it and use the explicit Apply
White/Apply Black seat workflow, confirm the change, then resume.

The exact number input accepts every supported integer. The optional slider can
use 1-Elo or 25-Elo steps. Coarse steps start at the engine's minimum; the final
step may be shorter so the maximum remains reachable. Exact entry is independent
of the chosen slider increments. Elo is Stockfish's target under its native
strength limiter, not a guaranteed rating. Search time and hardware still matter.

## Runtime capabilities and execution

`GET /api/engine/strength` reads the installed engine's UCI options and reports its
version, availability, Elo minimum/maximum and full-strength availability. It
does not publish the local executable path. An unavailable engine reports null
limits, not an invented supported range. Configure `STOCKFISH_PATH` or use the
existing runtime discovery described in the repository README.

Rated mode sets UCI_LimitStrength=true and the exact UCI_Elo, including at the
maximum. Full strength is separate: it sets UCI_LimitStrength=false and resets
Skill Level to the advertised maximum. The rated range is not a menu of fixed
presets. Unsupported ratings are rejected rather than silently clamped. Existing
unavailable-engine recovery behavior remains; no move is substituted.

Full strength is an optional boolean in Stockfish player settings and the legacy
create-game request (`stockfish_full_strength`). The existing numeric target field
is retained for storage compatibility but is inactive when full strength is true.
The mode is preserved in engine summaries and comparison conditions; UI labels
distinguish it from rated play. No schema migration is needed.

## Verified local engine (October 9, 2026)

Official source: [Stockfish19 release](https://github.com/official-stockfish/Stockfish/releases/tag/sf_19).
Package: `stockfish-windows-x86-64-universal.zip`.
Release archive SHA-256:
`3c8bf1f9ea66a09350a40df4f632288285ac206d99f33ab5842c408fc30b48a7`.

The downloaded archive was hash-verified before execution. Its actual handshake:

```text
id name Stockfish 19
option name Skill Level type spin default 20 min 0 max 20
option name UCI_LimitStrength type check default false
option name UCI_Elo type spin default 1320 min 1320 max 3190
```

The binary is local, ignored runtime material under `.runtime/stockfish-19`;
it is not vendored in Git. License/source files from the official archive remain
with it. The local preview launcher sets its path only for the server process.
The app launched native Stockfish processes from that path and returned c7c5
after e2e4 in a disposable target3100 match (108ms engine latency).

## Verification

`test_stockfish_strength.py` records UCI configuration at both boundaries,3100
and full strength; checks backend errors, mode types, stored/reloaded settings,
reset persistence, active-seat rejection and explicit paused-seat changes.
`test_engine.py` exercises a real installed engine, including its own advertised
boundaries; set STOCKFISH_PATH when necessary. Tests skip native-engine acceptance
when no binary is available, rather than claiming a mock proves native behavior.

`stockfish-strength.spec.ts` covers exact input, coarse-slider endpoints, browser
persistence, new-game payloads and unchanged current matches across five widths.
It uses runtime capability data locally; when CI has no engine, a clearly named
UI capability fixture is used, separately from backend/UCI verification.
