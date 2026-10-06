# ADR 0023: Immutable experiment plans

- Status: Proposed (Stage 7A draft; merge pending)
- Date: 2026-10-04

The Model Lab needs a reproducible configuration boundary before batch execution.
Building or saving a plan must not dispatch an adapter, charge a provider, change a
live match, or reuse a one-match external runner grant for a batch.

The API validates 2–8 direct/local entrants and expands supported effort variants,
legal UCI opening lines, repetitions, and optional color swaps deterministically.
Variants of the same entrant do not face one another. Schedule ordering is entrant
pair, opening, repetition, then original/swapped colors. At most 512 games are
planned. Openings start from standard chess and cannot end in a terminal/claimable
position. Their exact moves and resulting FEN are saved.

Plans are immutable JSON documents in the experiments table (migration 0010).
A client UUID is an idempotency key: the identical body returns its original saved
snapshot; a different body conflicts. Saving and previewing call only local adapter
configuration validation, never choose_move or a provider health check. Existing
credential configuration can be required by an adapter's validation; this does not
make a network request. No credentials belong in experiment configuration.

SHA-256 over canonical JSON covers the normalized configuration, expanded player
profiles, exact advertised provider effort mapping, deterministic schedule, and
exhibition label. Random player IDs are normalized to entrant keys. Metadata such
as document ID, creation timestamp and warnings does not enter the hash. Names and
entrant ordering are intentional configuration inputs. The hash establishes document
identity, not provider determinism or a guarantee that a model alias never changes.

Mixed divisions are explicitly exhibitions. Stockfish uses explicit engine settings;
its legacy UI effort labels cannot be swept as if they changed strength. Clock info
is supplied and effort fixed for this increment. Withheld-clock/adaptive-effort
experiments require a separate protocol/control implementation before being enabled.
The UI currently builds Legal Assist model entrants and Engine Assisted Stockfish
entrants; supported alternative divisions remain available through the API.

Stop limits are stored, not enforced by a nonexistent execution loop. Stage 7B must
own atomic job creation, dispatch authorization, leases, recovery, provider budgets,
stop enforcement and cancellation. Max plies counts moves played after the opening;
wall-time applies to a batch run. Remote/subscription batch participation requires
fresh purpose-specific authorization and is not implied by this schema.
