# Hosting the Lounge on Fly.io with Supabase

The invite-only hosted Lounge (ADR0043). Players open a web address, sign in with an
invited email (link, Google or GitHub) and play Stockfish on their own table.

Cost: one Fly machine (shared-cpu-2x, 2 GB) is about $13–15/month; Supabase is the
existing Pro organization.

## One-time setup (owner)

These steps need your accounts; an agent cannot create accounts, enter payment
details or handle passwords.

1. **Fly.io account:** sign up at fly.io and add a card. Install the CLI and sign in:

   ```powershell
   pwsh -Command "iwr https://fly.io/install.ps1 -useb | iex"
   fly auth login
   ```

2. **Create the app** (from the repository root). The name must be unique on Fly;
   if `ai-chess-lounge` is taken, pick another and update `app` and
   `LOUNGE_PUBLIC_ORIGIN` in `fly.toml` to match:

   ```powershell
   fly apps create ai-chess-lounge
   ```

3. **Database secret:** in Supabase → Project Settings → Database, copy the direct
   connection string and set it as a Fly secret (paste your database password into
   the command yourself; never commit it). Fly machines reach Supabase's IPv6 direct
   address; if that fails, use the "Session pooler" string instead.

   ```powershell
   fly secrets set DATABASE_URL="postgresql://postgres:YOUR-PASSWORD@db.krkjhkhkgackragoclul.supabase.co:5432/postgres?ssl=require"
   ```

4. **Supabase sign-in settings** (Authentication in the Supabase dashboard):
   - URL Configuration → Site URL: `https://ai-chess-lounge.fly.dev`; Redirect URLs:
     add `https://ai-chess-lounge.fly.dev/**`.
   - Sign In / Providers → Email: enabled, with **Confirm email ON** (it is today).
     The server also refuses accounts whose address was never proven.
   - Google: create an OAuth client in Google Cloud Console (Web application),
     authorized redirect URI `https://krkjhkhkgackragoclul.supabase.co/auth/v1/callback`,
     then paste its client ID and secret into the Google provider.
   - GitHub: create an OAuth App (GitHub → Settings → Developer settings), callback
     URL `https://krkjhkhkgackragoclul.supabase.co/auth/v1/callback`, then paste its
     client ID and secret into the GitHub provider.

5. **Deploy** (one machine; live games are in memory):

   ```powershell
   fly deploy --ha=false
   ```

   On a PC whose antivirus inspects HTTPS (Norton on the owner's PC), Fly's default
   Depot builder fails with "certificate signed by unknown authority"; add
   `--remote-only --depot=false` to use Fly's own builder instead.

   The release step migrates the database first. Then open
   `https://ai-chess-lounge.fly.dev`, sign in with the admin address, and invite
   players from **Account → Players**.

## Day to day

- Invite or remove players: **Account → Players** (admins only).
- Deploy a new version: `fly deploy --ha=false`. Open boards reconnect by themselves.
- Logs: `fly logs`. Status: `fly status`. Restart: `fly machine restart`.
- Backups: Supabase Pro takes daily backups (7 days).

## Recovering the admin account

If the owner's sign-in account is deleted and recreated, the admin address stays
bound to the old account. Deploy once with `fly secrets set LOUNGE_ADMIN_REBIND=1`,
sign in, then `fly secrets unset LOUNGE_ADMIN_REBIND`.

## Limits

- One machine: a crash or deploy briefly disconnects boards; games resume.
- Supabase's built-in email sends only a few sign-in links per hour. For more
  players, add custom SMTP in Supabase or rely on Google and GitHub sign-in.
- Hosted seats are human and Stockfish only, a person plays at least one side, and
  Stockfish thinks at most one second per move (the engine is shared).
- Per player: 90 changes and 6 new games per minute, 4 open boards, 64 KB requests.
- Removed players lose live updates within 10 seconds.
