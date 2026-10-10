# ADR 0041: shared next-match table settings

Status: accepted.

## Decision

Next-match settings (seats, Stockfish strength mode, time control, start paused) live
in one server-side document, `table_settings`, so desktop and iPad agree instead of
each browser keeping its own `localStorage`. The Lounge has a single shared table, so
there is exactly one row (`id = "default"`).

`GET /api/table-settings` returns `{revision, updated_at, settings}`; an unsaved table
reports defaults at revision 0. `PUT /api/table-settings` takes `{revision, settings}`
and succeeds only when `revision` equals the stored revision (compare-and-swap, like
match revisions); otherwise it returns 409 and changes nothing. Revision 0 is claimed
by inserting the single row, so the primary key makes concurrent first saves safe.

Validation is strict (unknown fields rejected). Seat names and time-control keys
mirror the web client's `SeatChoice` and `timeControls`. Elo uses the same 800-3200
bounds as `CreateGameRequest`; the live engine's narrower caps are still enforced when
a match is created. The document stores preferences only, never credentials, and
creating a match still validates every field.

Migration 0013 adds the table. Local databases gain it through `create_all`. The
trusted-device network allow-list admits `/api/table-settings` (exact path), the same
trust level as `/api/games`, so a paired iPad can read and save it.
