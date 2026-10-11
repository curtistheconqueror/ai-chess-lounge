# ADR 0042: self-hosted supervision and engine resource limits

Status: accepted.

## Context

The private board runs on the host's own PC behind Tailscale Serve. It was started by
hand in a console window: closing the window, ending the process to free memory, or
a reboot left Serve answering 502 until someone restarted it. The Serve listener for
the board was itself a foreground command and was lost with its terminal. The web app
already reconnected to a returning server, but nothing brought the server back.

## Decision

1. A small standard-library supervisor (`scripts/windows/lounge_supervisor.py`)
   runs under `pythonw.exe` from a per-user scheduled task (sign-in plus a five-minute
   watchdog trigger). It starts the server suspended with `CREATE_NO_WINDOW`, places it
   in a Windows job object and resumes it, so the server and every Stockfish process
   share one memory cap, run at below-normal priority, never show a window, and die
   with the supervisor (kill on job close). Each start gets a fresh job (a job that is
   still terminating refuses new processes). It restarts a server that was healthy
   after one second, backs off exponentially only on repeated failures, and kills and
   restarts it after three missed `/api/health` polls. A named mutex allows one supervisor per configuration. `status`, `restart`
   and `stop` work through files in the instance folder, so no port or credential is
   added. No administrator rights or stored password are needed.
2. The Serve listener is made persistent with `tailscale serve --bg` (host approval).
3. `StockfishService` sets `Threads` and `Hash` explicitly at start
   (`STOCKFISH_THREADS`=1, `STOCKFISH_HASH_MB`=16 by default, bounded) and quits an
   engine process after `STOCKFISH_IDLE_SECONDS` (300) without use. The next request
   starts it again under the same lock; the cached engine name is kept, so summaries
   do not spawn a process.
4. The service worker shows the offline page for navigation responses 502-504 as well
   as network failures, and the offline page polls `/api/health` and reloads itself.

## Consequences

- A host's board survives closed windows, crashes, hangs and sign-in after a reboot,
  bounded by the PC being on, awake, signed in and on Tailscale.
- A runaway server is stopped at the job's memory cap instead of starving the PC.
- The first engine move after five idle minutes pays the engine start (well under the
  default one-second reply pacing).
- This is not a hosted deployment. The hosted release uses its platform's process
  supervision, health checks and limits; the engine settings apply there unchanged.
- The supervisor is Windows-only by design; Linux hosts use systemd or Docker.
