# Stage 7F — identity snapshots and local AI leaderboards

Additional authorized phase in Stage 7, extending 7C tournaments, 7D metrics and 7E
reports. It does not select Stage 9 public-profile/ranking scope or change hosted
release gates. Implementation is local/fixture only, with no provider calls required.

## Feature surface

- Optional public identity declarations in next-match, runner-pairing and Model Lab
  entrant forms. Configured model/display alias is distinct from declared underlying
  provider/model/family/version, routing broker and agent harness/version.
- Per-generation immutable identity/condition snapshots. Raw provider effort and
  evidence are preserved; unknown values remain unknown. Declared subscription
  settings are not verified. Adapter mappings describe actual configured request
  effort only; normalized names are not cross-provider equivalences.
- `GET /api/leaderboards`: grouping exact/model/family/version/effort_raw/access;
  exact filters model/version/effort/access/provider/broker/harness (use `unknown`
  for unavailable values), color filtering and optional forfeit exclusion.
- W/L/D, total/eligible sample sizes, explicit rate denominators, draw/score rates,
  color counts, head-to-head counts and inspectable conditions/identity variants.
  Human and Stockfish opponents are reference kinds. No invented catalog/Elo.
- Opt-in listing aliases only. Default display names, player IDs and owner identities
  are absent from aggregates. No owner directory or public publishing is added.

See ADR 0033 for exclusions, pooling, provider-observation provenance and bounds.
A direct adapter response model label may be recorded as provider-reported evidence;
missing/external response identity stays unknown. Such labels do not prove an exact
underlying version. Configurations containing comparison fields intentionally change
new experiment hashes; metadata-absent configurations keep legacy serialization.

## Migration and compatibility

Revision `0012_comparison_games` adds immutable identity + transactional outcome
JSON keyed by match/generation. Upgrade does not backfill unprovable historic identity.
Current legacy matches are counted separately and retained; reset creates a new known
snapshot while earlier recorded generations remain queryable. Downgrade drops only
the added comparison table. No credentials, policies or access grants are changed.

## Acceptance status

Local warning-strict suite passed 370 tests (5 native PostgreSQL skips), plus added
identity/boundary regressions. Ruff, production web/SDK builds and 3 SDK tests pass.
PostgreSQL migration/recovery and desktop/phone browser checks remain pending.
Do not describe this phase as complete until source and final-head CI and screenshot
review are recorded in PICKUP. Native PostgreSQL is available in CI, not this workspace.
Local Chromium is unavailable; use existing CI acceptance, not a new account/deploy.

## Limits and next decisions

Bounded local descriptive report (5,000 snapshots), not calibrated ratings or general
reasoning quality. All game conditions stay separate even under broad grouping.
Opt-in aliases reflect consent at snapshot time; this phase offers no public owner
profile and makes no hosted-consent or privacy-policy decision. No provider-paid calls.
The owner funds infrastructure and players fund agents/providers; access is free.
Hosted Supabase DB/auth still needs setup and authorization; persistent API/WebSocket,
queue and Stockfish runtime hosting still needs selection. Stage 9 remains unselected.

The added 7F scope consumes time within the Oct 6 17:40 UTC target. Hosted completion
remains conditional on approval/account/runtime/deferred-scope decisions, and the
planned integration buffer must not be replaced with unverified feature completion.
