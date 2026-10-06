# ADR 0033: per-generation comparison identity snapshots

Status: proposed in Stage 7F draft; depends on existing Stage 7 draft stack.

## Decision

Store one `comparison_games` record per match ID and generation. The identity and
conditions captured at match creation/reset are immutable. The outcome is updated
in the same successful match CAS transaction as moves/actions. Later configuration
edits do not rewrite history. Reset retains older generations and creates a fresh
snapshot. Migration 0012 adds a table; it does not fabricate original metadata for
existing matches. Old games remain loadable and mutable without retroactive capture.
Downgrade removes comparison records only; existing match records remain.

Separate configured labels, optional declarations, adapter-recorded effort mappings,
and actual engine runtime observations. API response model labels are bounded
provider-reported observations, not independently verified model versions. Changing
observed model labels excludes the game from strength rates. No model catalog or
private subscription setting is inferred. Keep declared raw effort even when an
adapter can record the actual mapped request value. Normalized Lounge effort names
apply only to a known mapping; they are not equivalences across providers.

## Aggregation and privacy

Exact identities include evidence as well as values. Engine strength and bounded
per-seat execution settings remain separate under every grouping. Every grouping also separates
conditions (opening FEN, clock, assistance/protocol, engine target/time/version and
request bounds). Broader model/family/version/effort/access grouping intentionally
pools identity variants, which remain inspectable. A collapsed self-match appears
once in its combined row and is excluded from rates and head-to-head comparisons.
Filters select games involving one seat matching all requested identity values;
rows retain opponents for context. Color filtering affects rows, not matchup counts.

Completed chess results use wins + draws + losses as the rate denominator; score
is (wins + half draws)/eligible games. Resignation/timeouts count as forfeits by
default and can be excluded. Aborted, adjudicated, unfinished/reset, human takeover,
played consultation and changing observed-model games remain counted in totals
with exclusions, not losses. Human/engine reference opponents are identified by kind.
No Elo, intelligence score or causal effort claim is introduced.

The local endpoint aggregates at most 5,000 generation snapshots, ordered by match
ID/generation, and explicitly reports truncation. This is not a production ranking
service. It lists no player IDs, owner records or default display names. A separately
opted-in alias may appear; no personal information is required. This phase does not
add an owner directory, publish profiles or change hosted access policies. Free human
and bot access and player-funded BYO inference remain unchanged.

## Consequences and verification

Additional transactional writes/storage per move; bounded aggregation is suitable
for local fixtures, not an established hosted capacity claim. Server restart restores
snapshot/outcome data. Runtime metadata remains unknown where not available. This
phase needs migration, legacy compatibility, CAS/reset/history, denominator/provenance,
privacy and desktop/mobile browser evidence. Production consent/auth, quota policy,
Supabase/runtime integration and Stage 9 scope remain separate decisions.
