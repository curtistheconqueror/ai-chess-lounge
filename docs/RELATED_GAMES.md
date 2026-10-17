# Game repository map

The owner maintains two separate chess applications. Choose the repository before
changing code; shared chess terminology does not mean they share an implementation.

| Application | Repository | Runtime and source | Local development |
| --- | --- | --- | --- |
| Original AI Chess Lounge | [ai-chess-lounge](https://github.com/curtistheconqueror/ai-chess-lounge) | Python/FastAPI and python-chess in `services/api`; React/TypeScript in `apps/web`; database migrations and agent-runner packages | Follow this repository's `README.md`, `AGENTS.md`, `CONTRIBUTING.md` and `docs/PICKUP.md` |
| Wizard's Chess / The Cathedral | [wizard-chess](https://github.com/curtistheconqueror/wizard-chess) — separate private repository | Node.js server; authored browser modules in `dist/`; minimalist 2D board and a procedural 3D cathedral | Follow that repository's `AGENTS.md`, `docs/PROJECT_MAP.md` and `docs/PICKUP.md`; `npm start` serves port 4173 |

**The Lounge** and **The Lab** are complementary experiences inside the original
AI Chess Lounge. They are not alternative names for Wizard's Chess. Wizard's 2D
and 3D boards are views of its own shared game controller, not the Lounge's React UI.

## Separate work and records

- Keep issues, feature branches, fixes, tests and releases with the application
  they change. Do not treat a feature in one game as implemented in the other.
- Preserve this repository's existing stage, contributor and immutable pickup branches.
- Wizard's Chess uses `main` for verified releases, `develop` for integration and
  `feat/`, `fix/`, `docs/`, `test/` and `chore/` branches for contributions.
- Its initial v1.9.3 source baseline is commit
  `af1b4e27a5d66d17edd02018aa1c458eb4c25689`; the version tag is `v1.9.3`.
- Accounts, credentials, sessions, records, rating pools, protocols and provider
  availability are not automatically shared between the two games.
- The TAP knowledge library / chess research collection remains a separate data
  project. Do not copy its private raw transcripts into either game repository.

The Wizard repository requires access because it is private. A source repository,
cross-link or version tag does not establish a hosted deployment. This routing
document changes neither application's deployment, access policy or runtime.
