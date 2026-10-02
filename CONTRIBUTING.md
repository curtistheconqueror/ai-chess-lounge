# Contributing

AI Chess Lounge welcomes human and AI-assisted contributions.

## Workflow

1. Choose an existing issue or open a narrowly scoped proposal.
2. Create a branch from the current default branch.
3. Make the smallest coherent change that satisfies the issue.
4. Add tests and documentation where behavior or contracts change.
5. Run local verification.
6. Update `docs/PICKUP.md` with the current phase, verification, risks, and exact next
   target.
7. Open a pull request with purpose, implementation, verification, risks, and any
   deferred work.
8. Keep the contributor branch after merge and create
   `pickup/<stage-or-phase>-complete` at the verified merge commit. Pickup branches
   are immutable and must never be force-pushed.

## Branch naming

- `feat/<short-name>`
- `fix/<short-name>`
- `docs/<short-name>`
- `test/<short-name>`
- `chore/<short-name>`
- `pickup/<stage-or-phase>-complete` (immutable completed checkpoint)

## Commit guidance

- Use clear imperative subjects.
- Keep mechanical formatting separate from behavioral changes when practical.
- Do not commit secrets, local databases, build output, or model transcripts that
  may contain private data.

## Pull-request gate

Before merging code, the project should require:

- Formatting and lint checks
- Static typing
- Unit and contract tests
- Application build
- Database migration validation when applicable
- A deterministic short end-to-end game once that harness exists

## Architecture decisions

Create an ADR in `docs/adr/` for changes involving service boundaries, persistence,
protocol compatibility, authentication, credential handling, match integrity, or
deployment topology.
