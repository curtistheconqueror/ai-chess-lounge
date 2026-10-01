# Stage 0 Exit Review

**Reviewed:** 2026-09-30

## 0A — Product contract

- [x] Product vision and pillars defined
- [x] Lounge, Lab, Open Table, and Tournament Hall experiences defined
- [x] Match types and fair-play assistance divisions defined
- [x] First-release non-goals defined
- [x] First meaningful release criteria defined

## 0B — Architecture contract

- [x] Standalone, provider-neutral application boundary defined
- [x] Recommended repository and runtime topology defined
- [x] Server-authoritative turn flow defined
- [x] Normalized player request/response contract illustrated
- [x] API, local, remote, MCP, and subscription connection modes separated
- [x] Stockfish seat, analysis, strength, and resource-isolation plan defined
- [x] Core data model, metrics, security boundaries, and deployment path defined

## 0C — Contribution contract

- [x] README and master plan created
- [x] Agent-specific contribution guardrails created
- [x] Human contribution and pull-request rules created
- [x] MIT license selected
- [x] CODEOWNERS created
- [x] Bug and feature issue forms created
- [x] Pull-request verification and integrity checklist created
- [x] Security reporting and secret-handling policy created

## 0D — Decision log

- [x] ADR template created
- [x] Server-authoritative state decision accepted
- [x] Append-only event decision accepted
- [x] Provider-neutral player protocol decision accepted
- [x] Credential and subscription boundary decision accepted

## Remaining repository administration

- [ ] Enable branch protection/rules after the bootstrap commit is published
- [ ] Require status checks after Stage 1 introduces CI jobs
- [ ] Enable GitHub private vulnerability reporting before public beta
- [ ] Add named collaborators when the owner identifies contributors who require
  direct write access; public contributors can fork and open pull requests immediately

## Exit decision

Stage 0's product, architecture, contribution, and decision contracts are complete.
The repository is ready to begin **Stage 1A — Workspace bootstrap**. Repository
administration items are intentionally sequenced to the point where their required
checks or named collaborators exist.
