# ADR 0043: invite-only hosted Lounge on Fly.io and Supabase

Status: accepted (owner chose Fly.io + Supabase, invite-only, email link + Google +
GitHub sign-in, keep the existing test games).

## Decision

**Runtime:** one always-on Fly.io machine (shared-cpu-2x, 2 GB, `iad`) runs the
existing FastAPI app, WebSockets and Stockfish from the repository Dockerfile.
Database changes run as Fly's release command (`alembic upgrade head`). Live
games, clocks and WebSocket tickets are in memory, so the app runs as exactly one
machine; scaling out needs shared state first.

**Database and identity:** the existing Supabase project `ai-chess-lounge`
(Postgres 17, us-east-1, organization on Pro). The app connects as the database
owner; every table in `public` has row level security on with no policies, which
closes Supabase's REST API to them. Supabase Auth issues sign-ins (email link,
Google, GitHub). The server verifies access tokens itself against the project's
public JWKS (ES256): signature, `aud=authenticated`, issuer, expiry, a real email
and not anonymous. The server holds no Supabase secret key.

**Invite-only:** `lounge_members` lists who may sign in. Supabase may create an
account for anyone who requests a link, but the server admits only active members.
An address binds to the first account that signs in with it; a different account
with the same address is refused until an admin removes and re-invites it.
`LOUNGE_ADMIN_EMAILS` are always admins and cannot be demoted or removed from the
UI. Admins manage the list on `/players`.

**Ownership and scope:** matches have `owner_id`. A middleware checks every
`/api/games/{id}…` route and `/ws/games/{id}` socket before the route runs: owner or
admin, otherwise 404 (existence is not revealed). Each player has their own table
(live match and next-match settings), one live match at a time, and the server caps
live matches overall (`LOUNGE_MAX_LIVE_GAMES`). Pre-hosting games have no owner and
are visible to admins only. Hosted seats are human and Stockfish; remote runners,
Model Lab, leaderboards, API docs and provider consultations are not served.

**WebSockets:** a browser cannot send an Authorization header on a WebSocket, and a
token in a URL ends up in logs. The page trades its sign-in for a one-time ticket
(30 s, `POST /api/ws-ticket`) and the socket must also come from the public origin.

**Abuse limits** (from the security review): a person plays at least one side and
the shared Stockfish thinks at most one second per move; per player 90 changes and
6 new games a minute, 4 open sockets and 64 KB request bodies; open sockets
re-check membership and ownership every 10 seconds; sign-ins must prove the email
(confirmed, link or provider); hosted responses forbid framing and set HSTS; internal
error text is not shown; there is no access log (tickets are in socket URLs).

**Fail closed:** hosted startup needs every setting (Supabase URL and public key,
public origin, admin emails, a PostgreSQL URL) and a schema at exactly the current
revision; it never creates tables. `LOUNGE_DEPLOYMENT` and `LOUNGE_HOSTED_MODE`
must agree. The batch worker refuses hosted mode.

## Consequences

- Players need only a browser; the owner's PC is no longer involved.
- Supabase's built-in email sender is rate-limited (a few per hour); a larger
  group needs custom SMTP. Google and GitHub sign-in avoid email entirely.
- One machine is a single point of failure: Fly restarts it on crash and on host
  failure, and games resume from the database, but a deploy briefly disconnects
  open boards (they reconnect by themselves).
- Opening AI seats, spectating, two-player games or open sign-up later each need
  their own access design; nothing here grants them.
