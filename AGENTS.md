# Agent Contribution Instructions

These rules apply to every coding agent and automated contributor in this repository.

## Read first

Before changing code, read:

1. `README.md`
2. `docs/MASTER_PLAN.md`
3. `CONTRIBUTING.md`
4. Relevant ADRs and service-level documentation once they exist

## Safety and collaboration

- Preserve concurrent work. Never force-push, rewrite shared history, or discard
  changes you did not create.
- Work on a dedicated branch and open a pull request unless the owner explicitly
  directs otherwise.
- Never commit API keys, OAuth tokens, provider cookies, subscription credentials,
  private prompts, or generated secret files.
- Do not log raw credentials or private model reasoning.
- The server-side chess arbiter is authoritative. Adapters may propose moves but may
  not mutate game state.
- Never silently substitute a Stockfish move for an agent move in a rated match.
- Preserve assistance-division boundaries and disclose tools used by competitors.
- Treat model names, effort parameters, prices, and authentication methods as
  provider capabilities that can change; do not hard-code unsupported assumptions.

## Change quality

- Keep each change narrowly scoped.
- Add or update tests for behavioral changes.
- Run the relevant formatter, linter, type checker, tests, and build before handoff.
- Update the protocol version when making a breaking schema change.
- Add an ADR for consequential architecture choices.
- Include verification evidence and remaining risks in the pull request.

## Initial architecture guardrails

- Python/FastAPI owns chess-domain and match orchestration code.
- `python-chess` owns legality, FEN, PGN, and terminal-state rules.
- The web application consumes versioned APIs/events and does not infer authoritative
  match state.
- Provider integrations live behind normalized adapters.
- Stockfish runs out of process through UCI with resource limits.
- Match events are append-only and sequence ordered.
- Human takeover, pause, retries, and adjudication are explicit events.
