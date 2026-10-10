# ADR 0039: Explicit current-seat updates and native Stockfish skill mode

Status: accepted for private practice, October 10, 2026.

## Decision

Current-match Stockfish controls are separate from next-match draft configuration.
Each Stockfish seat shows current and proposed values. Confirmation pins the match
revision. A running game is paused using that revision, then its selected seat is
changed using the returned paused revision. Cancel performs neither operation.
Both steps retain their existing compare-and-swap and experiment-edit guards.
The match stays paused for explicit resume. If the second step loses a race, report
the error and reload; never overwrite a newer controller or automatically resume.
The existing seat history/event records the change and broadcasts it to viewers.
The shared engine is configured from the authoritative seat on every search.

Stockfish supports three distinct modes: target Elo, native Skill Level, and full
strength. An optional integer `skill_level` from 0 to 20 in Stockfish settings selects
skill mode. It is mutually exclusive with `full_strength=true`. Legacy `target_elo`
remains stored for compatibility but is inactive in skill/full modes. Skill mode
sets `UCI_LimitStrength=false` and the requested `Skill Level`; Elo/full modes reset
Skill Level to the advertised maximum, then respectively enable/disable the Elo
limiter. Capability discovery exposes actual skill bounds or null when absent.
Unsupported runtime settings fail explicitly. Unavailable-engine recovery remains.

The optional create request `stockfish_skill_level` supports legacy convenience
clients. Engine summaries include optional skill metadata. Player settings and
engine summaries already persist as JSON: no database migration is needed. Wire
fields are additive; existing clients and the agent protocol remain compatible.

Skill levels are not calibrated Elo ratings. The UI displays the skill mode and
level, and comparison conditions record skill level with no active Elo target.
Distinct levels remain distinct comparison conditions. Historical generation
snapshots remain immutable; mid-game seat changes retain their existing exclusion
from comparable rating results. Human/agent seats acquire no configurable rating.

## Verification

Tests cover cancel, confirmation, stale revisions, multiple isolated viewers,
position/history preservation, interrupted searches, reload/resume, both colors,
new games, invalid types/ranges, mode switches, persistence and native UCI options.
No claim is made that level 0 is a particular human rating or reliably beginner-like.
