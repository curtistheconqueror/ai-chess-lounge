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

## Acceptance evidence and final check

Published dependent draft PR32, contributor `feat/stage-7f-ai-leaderboards`:
https://github.com/curtistheconqueror/ai-chess-lounge/pull/32
Source 6ebff8d151d3418701c7a8b2d9ebb134e457543e passed CI37248389001 /
job111570790115: 374 warning-strict Python tests, 3 engine skips, both migration
chains, native snapshot transaction tests, PostgreSQL recovery, bounded performance,
3 SDK tests, production build and 36 browser passes (79 intentional viewport skips).
All 33 source files matched local git blob hashes. Desktop/phone screenshots inspected.
Generated PG recovery matched 14 tables / 15 rows; this is not production RPO/RTO.

Follow-up: reset captures current UCI runtime evidence while keeping old generations
immutable (32 targeted tests, 1 native-PG skip). Local Stockfish16 observation confirmed
separate 1600/2500 strength rows and unavailable rates for unfinished games. Phone
rows now show results/conditions without horizontal scrolling; provenance labels are
readable, with full evidence in details. Build passes and phone acceptance is extended.
Engine color swaps retain both samples without pooling different strengths. Ollama/
vLLM serving connectors do not imply an underlying model provider; that stays unknown
unless declared. Connector labels are recorded separately. The final 19 local identity
tests pass (1 native-PG skip).
These follow-ups require the final published-head CI/browser check; consult PR32's
current head/checks and final evidence. Do not merge or call hosted release complete.
Native PostgreSQL/browser execution remains CI-only in this workspace.

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
