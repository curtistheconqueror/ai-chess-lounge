# Running the Lounge in the background on Windows

For a host who keeps the Lounge on their own PC (see [private Tailscale](PRIVATE_TAILSCALE.md)).
A hosted release does not use this: its platform supervises the server (see
[hosted release path](HOSTED_RELEASE_PATH.md)).

## What it does

`scripts/windows/lounge_supervisor.py` keeps one server running with no console window:

| Problem it removes | How |
| --- | --- |
| A console window pops up while the server runs | Started by `pythonw.exe`; the server gets a hidden console that Stockfish inherits |
| Closing or killing the server leaves the site down (Serve shows 502) | Restarted on exit after 1 s; only a server that keeps failing (three exits in 10 minutes, or never healthy) backs off, from 2 s doubling to 60 s |
| A hung server keeps the port but answers nothing | `/api/health` is polled every 10 s; three misses in a row kill and restart it |
| Memory can grow unchecked | The server and its engines share one Windows job object capped at `memory_limit_mb` (1536 MB by default); an allocation past the cap fails and the server is restarted |
| The chess server competes with other work on the PC | The job runs at below-normal priority |
| Engines left behind when something dies | Kill-on-close job: when the supervisor exits, the server and every engine exit too |
| Two copies fight over the port | One supervisor per configuration (named mutex); a second start exits immediately |
| Nothing starts after a reboot or sign-in | A per-user scheduled task starts it at sign-in and re-checks every five minutes |

Stockfish also has explicit limits in the server: `STOCKFISH_THREADS` (default 1),
`STOCKFISH_HASH_MB` (default 16) and `STOCKFISH_IDLE_SECONDS` (default 300: an idle
engine process is shut down and starts again transparently on the next request).

The web app already reconnects by itself: an open board shows "Reconnecting…" and
picks up the authoritative position when the server returns; a move lost to the outage
shows a plain "Lost connection" notice that clears on reconnect. A page opened while
the server is down shows "Reconnecting to the Lounge" (from the service worker, also
for Serve's 502) and reloads by itself once `/api/health` answers.

## Set up

1. Create a folder for the instance, for example `%USERPROFILE%\.ai-chess-lounge\private`.
2. Put a launcher script there that sets the server's environment and runs
   `lounge_api.serve` (the same settings as in [private Tailscale](PRIVATE_TAILSCALE.md)).
   Never put provider keys in it.
3. Add `service.json` next to it (paths can be relative to this file; use `/` or `\\`
   in JSON):

   ```json
   {
     "name": "private",
     "python": "C:/path/to/ai-chess-lounge/.venv/Scripts/python.exe",
     "launcher": "start-server.py",
     "health_url": "http://127.0.0.1:8001/api/health",
     "memory_limit_mb": 1536
   }
   ```

   Other settings and their defaults are listed in `DEFAULTS` in the supervisor.
4. Make the Serve listener persistent so it also survives a reboot (this is a lasting
   Tailscale configuration change on the host; the foreground Serve command from the
   first test must be stopped first):

   ```powershell
   tailscale serve --bg --https=8444 http://127.0.0.1:8001
   tailscale serve status
   ```

5. Install the task (no administrator rights; runs only while you are signed in).
   The supervisor needs only the standard library, so any Python 3.11+ `pythonw.exe`
   works:

   ```powershell
   scripts\windows\install-lounge-service.ps1 -Name private `
     -Config "$env:USERPROFILE\.ai-chess-lounge\private\service.json" `
     -Pythonw "$env:LOCALAPPDATA\Programs\Python\Python313\pythonw.exe"
   ```

## Day to day

```powershell
$sup = "scripts\windows\lounge_supervisor.py"; $cfg = "$env:USERPROFILE\.ai-chess-lounge\private\service.json"
python $sup --config $cfg status    # state, PIDs, restarts, last exit, peak memory
python $sup --config $cfg restart   # e.g. after deploying backend changes
python $sup --config $cfg stop      # stops until the next sign-in or watchdog check (5 min)
Disable-ScheduledTask AIChessLounge-private   # keep it off; Enable-ScheduledTask to resume
scripts\windows\install-lounge-service.ps1 -Name private -Uninstall
```

Logs are in the instance folder: `logs\supervisor.log` (starts, exits, restarts) and
`logs\server.log` (server output), each rotated at 10 MB. If the configuration cannot
be read, the reason is written to `supervisor-config-error.log`.

Pause or finish a match before a planned `restart` or `stop`. Games, moves and
settings are persisted, so a crash keeps the game; clocks follow the existing
restart-recovery policy.

## Limits

This keeps one PC's server available while that PC is on, awake, signed in and on
Tailscale. It is not multi-user hosting: it does not add accounts, more tables,
off-site backups or alerting. Those are part of the hosted release.
