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

## Phase and stage handoff

Every completed project phase or stage must leave a durable GitHub pickup point so a
new contributor can resume without the originating chat or local worktree:

- Keep the completed contributor branch on the remote. Do not delete it after merge.
- After merge, create an immutable `pickup/<stage-or-phase>-complete` branch at the
  verified merge commit. Never force-push or repoint a pickup branch.
- Update `docs/PICKUP.md` in the active contributor branch with what shipped, the
  pull request and commit, verification evidence, known risks, current work, and the
  exact next target.
- Before starting a new phase, read `docs/PICKUP.md` and confirm the documented base
  commit still matches the repository.
- If a phase stops before completion, push its `feat/`, `fix/`, `docs/`, `test/`, or
  `chore/` contributor branch and mark the handoff as in progress; do not label it a
  completed pickup checkpoint.

## Initial architecture guardrails

- Python/FastAPI owns chess-domain and match orchestration code.
- `python-chess` owns legality, FEN, PGN, and terminal-state rules.
- The web application consumes versioned APIs/events and does not infer authoritative
  match state.
- Provider integrations live behind normalized adapters.
- Stockfish runs out of process through UCI with resource limits.
- Match events are append-only and sequence ordered.
- Human takeover, pause, retries, and adjudication are explicit events.
