# AI Chess Lounge — Master Product and Execution Plan

**Status:** Stage 2A–2D, Stage 3A–3F, the Stage 4 broadcast slice, and Stage 5A–5B implemented

**Working repository:** `curtistheconqueror/ai-chess-lounge`

**Product type:** Standalone web application with an open integration protocol

**Primary objective:** Let AI agents, chess engines, and humans enter a shared
live chess environment and play without browser-control friction or per-move
manual intervention.

---

## 1. Product vision

AI Chess Lounge is a live arena where viewers can watch different intelligence
systems reveal their character over a chessboard. A user can seat two models,
change their effort levels, place Stockfish across from a frontier model, take a
seat personally, or run a controlled tournament.

The experience must feel like a premium broadcast, while the underlying system
must behave like a reproducible evaluation harness.

### Product pillars

| Pillar | Outcome |
| --- | --- |
| Seamless play | Once a competitor joins a match, turns advance automatically. |
| Provider neutrality | OpenAI, Anthropic, Google, OpenRouter, local models, MCP agents, subscription runners, Stockfish, and humans share one player contract. |
| Visual clarity | The board, clocks, player identity, strategy, PGN, FEN, evaluation, and match state are immediately understandable. |
| Honest comparisons | Assistance level, model version, effort, prompt, tools, latency, token usage, and cost are recorded. |
| Human participation | A person can play, take over a seat, resume a paused game, or consult an AI teammate. |
| Reproducibility | A match can be reconstructed from its configuration and append-only event history. |

### Non-goals for the first release

- Building a general-purpose chess social network
- Replacing established chess analysis platforms
- Displaying or extracting private chain-of-thought
- Allowing arbitrary third-party code to execute inside the main API process
- Claiming that chess alone measures general intelligence
- Supporting real-money wagering

---

## 2. Experiences and operating modes

### 2.1 The Lounge

The spectator-first presentation layer:

- Large animated board with last-move, check, threat, and evaluation indicators
- Player cards showing provider, model, effort, assistance class, time, latency,
  tokens, and match score
- Strategy banner with a concise public plan, primary threat, and confidence
- Collapsible PGN and FEN panels with one-click copy
- Live move list, clocks, captured pieces, opening name, and evaluation graph
- Pause, resume, replay, step forward/back, jump-to-live, flip board, and export
- Shareable match URL and downloadable PGN/JSON record
- Responsive desktop, tablet, and phone layouts

### 2.2 The Lab

The evaluation and experimentation layer:

- Create repeatable match configurations
- Run color-swapped pairs, opening suites, round robins, and brackets
- Sweep model effort, time limits, prompt strategies, or assistance levels
- Compare win rate, draw rate, average centipawn loss, blunders, illegal attempts,
  latency, tokens, and estimated cost
- Store a cryptographic hash of the complete match configuration
- Export CSV/JSON/PGN for independent analysis

### 2.3 Open Table

Human participation:

- Human vs AI, human vs Stockfish, or human vs human
- Take over an AI seat at the next legal turn
- Return a seat to the configured agent
- Optional AI consultation mode in which the model suggests but cannot move
- Private practice or publicly spectated table

### 2.4 Tournament Hall

- Round-robin, Swiss-style (later), knockout, and gauntlet formats
- A competitor is a versioned configuration, not only a model label
- Independent ratings by division and time control
- Resume-safe scheduling and deterministic pairing records

---

## 3. Fair-play divisions

Results from different assistance levels must never share one leaderboard.

| Division | Information and tools allowed |
| --- | --- |
| Pure Reasoning | Position and move history only; no generated legal-move list and no chess engine. |
| Legal Assist | Position plus legal UCI moves; prevents notation mistakes without offering evaluation. |
| Tactical Metadata | Legal moves plus non-evaluative board facts such as check status and material count. |
| Engine Assisted | Agent may query Stockfish before choosing its move. |
| Open Agentic | Agent may use declared tools, memory, databases, or its own workflow. |
| Human–AI Team | Human and agent jointly decide through an explicit consultation interface. |

Each leaderboard is additionally segmented by time control and match protocol
version. Exhibition games may mix divisions, but the UI must disclose the mismatch.

---

## 4. System architecture

### 4.1 Recommended repository layout

```text
ai-chess-lounge/
├── apps/
│   └── web/                    # React/Vite spectator and player UI
├── services/
│   └── api/                    # FastAPI, auth, match API, WebSockets
├── workers/
│   ├── match-runner/           # Turn loop and provider dispatch
│   └── analysis-runner/        # Stockfish post-game/live analysis
├── packages/
│   ├── protocol/               # JSON Schemas/OpenAPI-generated clients
│   ├── model-adapters/         # Provider-neutral adapter interfaces
│   └── ui/                     # Shared visual components and tokens
├── runners/
│   └── subscription-bridge/    # User-controlled authorized CLI/SDK bridge
├── infra/                      # Docker, migrations, deployment manifests
├── tests/
│   ├── contract/
│   ├── integration/
│   └── fixtures/
└── docs/
```

### 4.2 Runtime topology

| Component | Responsibility |
| --- | --- |
| Web client | Render the live board, collect human moves, display events, and control replay. |
| API service | Authentication, match creation, persistence, public reads, and WebSocket fan-out. |
| Match runner | Own the turn loop, call the active player adapter, enforce timeouts, and submit proposals to the arbiter. |
| Chess arbiter | Authoritative `python-chess` board, move legality, terminal-state detection, FEN, and PGN. |
| Stockfish pool | Sandboxed UCI processes for engine seats and analysis. |
| Adapter layer | Normalize provider-specific authentication, effort controls, request formats, usage, and failures. |
| Subscription bridge | Locally authorized runner that receives turns and calls an officially supported subscription CLI/SDK where permitted. |
| PostgreSQL | Users, agents, configurations, games, moves, events, tournaments, and metrics. |
| Redis | Distributed match locks, job queues, presence, and transient pub/sub after horizontal scaling. |

### 4.3 Authoritative turn flow

1. Match runner acquires the game/version lock.
2. Arbiter confirms side to move, current status, and remaining clock.
3. Runner creates a normalized `MoveRequest`.
4. The selected player adapter receives FEN, PGN/moves, time budget, division,
   legal moves when allowed, and the public strategy-output schema.
5. Adapter returns a structured `MoveProposal`.
6. Arbiter validates the UCI move against the current version of the position.
7. A valid move and its metadata are committed in one transaction.
8. The event is broadcast to spectators and the next turn is scheduled.
9. Illegal output invokes the configured retry policy; timeout or exhaustion causes
   a forfeit, fallback, or pause according to match rules.

No model, browser, or remote runner may directly update board state.

### 4.4 Normalized player contract

Illustrative request:

```json
{
  "match_id": "uuid",
  "position_version": 18,
  "color": "black",
  "fen": "...",
  "moves_uci": ["d2d4", "d7d5"],
  "pgn": "1. d4 d5",
  "legal_moves": ["g8f6", "c7c5"],
  "remaining_ms": 281000,
  "move_deadline_ms": 15000,
  "division": "legal_assist",
  "public_summary_required": true
}
```

Illustrative response:

```json
{
  "move": "g8f6",
  "plan": "Develop while increasing pressure on the center.",
  "threat": "White may expand with c4 and gain space.",
  "confidence": 74,
  "client_request_id": "uuid"
}
```

`plan`, `threat`, and `confidence` are deliberately generated public summaries.
They are not private chain-of-thought and are not used as proof of internal
reasoning.

### 4.5 Connection modes

| Mode | Use | Authorization model |
| --- | --- | --- |
| Direct API | Hosted providers such as OpenAI, Anthropic, Google, and OpenRouter | User-provided key or server-owned key with quotas |
| Local provider | Ollama, vLLM, or another OpenAI-compatible endpoint | User-controlled URL/token; private-network restrictions apply |
| Remote agent protocol | Third-party agent runner receives turn events and submits signed proposals | Short-lived scoped player token |
| MCP compatibility | MCP clients can create/join/watch games and submit moves | Host controls tool approval policy |
| Subscription bridge | Official provider CLI/SDK authenticated by the user runs as a local sidecar | One explicit match/session authorization; no credential export |

MCP support is valuable, but the remote agent protocol is the unattended match
transport. MCP hosts may intentionally require human approval for tool use, so the
core product cannot assume that MCP alone eliminates per-turn prompts.

---

## 5. Stockfish integration

Stockfish is a first-class `PlayerAdapter` and a separate analysis service.

### Seat controls

- `UCI_LimitStrength` and `UCI_Elo` when supported
- Skill level
- Move time, depth, or node limit
- Threads and hash size
- Opening book policy
- Deterministic/reproducible configuration where practical

An advertised value such as “2500 Elo” is an engine configuration target, not a
guaranteed universal rating. Hardware, engine version, opening policy, and time
control must accompany the label.

### Analysis controls

- Live evaluation can be delayed or hidden from players
- Spectator evaluation is produced by a separate engine instance
- Post-game analysis records score, best move, principal variation, centipawn
  loss, mistakes, blunders, and tactical turning points
- Engine analysis is never injected into a Pure Reasoning or Legal Assist player
  prompt

### Resource isolation

- Run engine processes in constrained worker containers
- Cap CPU, memory, threads, hash, and analysis duration
- Maintain a process pool instead of spawning per board update
- Kill and replace unhealthy UCI processes
- Record Stockfish binary/version hash with every rated match

---

## 6. Model adapter and effort system

Every provider adapter implements the same interface:

- `list_models()`
- `capabilities(model)`
- `validate_configuration()`
- `choose_move(request)`
- `normalize_usage()`
- `healthcheck()`

### Capability registry

Each model records:

- Supported effort/thinking controls and accepted values
- Structured-output or tool-call support
- Context and output limits
- Streaming support
- Authentication modes
- Temperature/seed support
- Current provider model identifier and optional pinned version
- Pricing metadata source and effective date

The UI presents a normalized effort control—Fast, Balanced, Deep, Maximum—but
also stores and shows the exact provider parameter. Unsupported levels are disabled,
not emulated invisibly.

### Initial adapter order

1. Deterministic scripted adapter used for tests
2. Stockfish adapter
3. OpenAI Responses adapter
4. Anthropic Messages adapter
5. Google Gemini adapter
6. OpenRouter/OpenAI-compatible adapter
7. Local Ollama/vLLM adapter
8. MCP compatibility adapter
9. Subscription bridge adapters, provider by provider, only through supported
   authentication routes

### Output recovery policy

1. Prefer structured output or function calling.
2. Parse strict UCI move from the declared response field.
3. Reject stale position versions.
4. On illegal/unparseable output, return a compact validation error and retry once
   or twice within the original clock budget.
5. Never silently replace the model's move with an engine move in a rated game.
6. Record every attempt for reliability metrics, with private/sensitive text
   redacted according to retention policy.

---

## 7. Core data model

| Entity | Essential data |
| --- | --- |
| User | Identity, roles, preferences, and quotas |
| Agent Profile | Display name, provider type, avatar, owner, and connection mode |
| Agent Configuration | Model identifier, effort, prompt version, division, tools, and generation settings |
| Match | Seats, time control, status, visibility, configuration hash, and result |
| Move | Ply, UCI, SAN, pre/post FEN, clocks, attempts, latency, and usage |
| Strategy Summary | Public plan, threat, confidence, and schema version |
| Event | Immutable ordered match event with sequence and timestamp |
| Analysis | Engine version/settings, score, PV, classifications, and ACPL |
| Tournament | Format, entrants, pairings, standings, and rating pool |
| Credential Reference | Encrypted secret reference; never returned to the client after storage |
| Runner Session | Scoped token, agent identity, heartbeat, match permissions, and expiry |

The append-only event log is the replay source of truth. Relational summary tables
are projections for efficient reads.

---

## 8. Evaluation framework

### Primary metrics

| Category | Metrics |
| --- | --- |
| Chess strength | Result, score, Elo estimate, ACPL, accuracy, mistakes, blunders, and missed wins |
| Reliability | Illegal attempt rate, parse failures, stale submissions, timeouts, and completion rate |
| Efficiency | Median/p95 move latency, input/output/reasoning tokens, and estimated cost per move/game |
| Effort response | Strength, reliability, latency, and cost delta between effort levels |
| Strategic coherence | Declared-plan persistence and plan changes after opponent disruption; clearly labeled as an external measurement |
| Operational stability | Provider errors, retries, rate limits, disconnect recovery, and resume success |

### Experimental controls

- Swap colors and aggregate paired games
- Use an opening suite to reduce opening-memory bias
- Keep clocks, legal assistance, prompt version, and tool permissions identical
- Pin model versions where providers allow it
- Record temperature, seed, max output, and exact effort parameters
- Run enough games to show confidence intervals, not only anecdotes
- Separate exhibition results from rated experiment results
- Never compare engine-assisted agents with pure agents on one rating list

### Model identity

A scoreboard entry uses the full identity:

```text
Provider / Model / Version / Effort / Division / Prompt / Tools / Time Control
```

Changing any material element creates a new rated competitor configuration.

---

## 9. Security, privacy, and trust

### Credentials

- Prefer bring-your-own-key for early private use
- Encrypt stored provider keys with envelope encryption
- Store only secret references in application tables
- Never send one user's key to another client, runner, or model
- Never place credentials in URLs, logs, prompts, traces, exports, or Git
- Let users test, rotate, and revoke connections
- A subscription bridge retains provider credentials on the user's machine

### Remote runners

- Pair with a short-lived one-time code
- Issue a runner token scoped to an agent and allowed match actions
- Sign move submissions and require idempotency keys
- Heartbeat, expiry, explicit revoke, and per-match authorization
- Reject arbitrary inbound URLs and protect against SSRF

### Match integrity

- Server-authoritative clocks and state
- Database transaction plus position-version compare-and-swap per move
- One active turn lease at a time
- Immutable event sequence and configuration hash
- Disclosure of every enabled tool and assistance class
- Audit trail for pause, takeover, retry, adjudication, and administrative action

---

## 10. Visual and interaction direction

### Visual thesis

A premium night-time chess club crossed with a live intelligence laboratory:
obsidian surfaces, deep green and indigo structure, restrained gold accents,
high-contrast ivory pieces, and luminous but disciplined data visualization.

### Desktop layout

| Region | Contents |
| --- | --- |
| Center | Dominant board, move animation, last move, checks, optional coordinates |
| Top/bottom rails | Player identity, model configuration, clock, connection, latency |
| Right panel | Tabs for Moves/PGN, Strategy, Evaluation, and Match Details |
| Under board | Playback controls, live status, copy/export/share actions |
| Optional left rail | Lounge rooms, tournament standings, or experiment queue |

### Mobile layout

- Board fills the available width below compact player clocks
- Strategy banner becomes a swipeable card
- PGN/FEN/evaluation move into a bottom sheet
- Essential play controls remain thumb reachable
- Spectator data is progressively disclosed instead of squeezed beside the board

### Accessibility

- Keyboard move entry and complete keyboard playback
- Screen-reader position/move announcements
- Non-color indicators for check, selection, and evaluation changes
- Reduced-motion mode
- High-contrast piece/board themes
- 200% text zoom without broken controls

---

## 11. Delivery stages, sub-phases, and gates

Each stage ends with a working, testable increment. Later work must not begin by
silently bypassing an incomplete exit gate.

### Stage 0 — Foundation and project contract

**Goal:** Establish the shared blueprint and make the repository safe for multiple
human or agent contributors.

| Sub-phase | Deliverables |
| --- | --- |
| 0A Product contract | Vision, modes, divisions, non-goals, terminology, and initial UX direction |
| 0B Architecture contract | Service boundaries, player protocol, event model, security rules, and repo layout |
| 0C Contribution contract | README, AGENTS, contributing rules, issue templates, license, branch/PR conventions |
| 0D Decision log | ADR template and first decisions for stack, state authority, protocol, and credential handling |

**Exit gate:** Repository is public and cloneable; master plan is reviewed; no
credential or hosting dependency is required; contributors have unambiguous rules.

### Stage 1 — Local playable vertical slice

**Goal:** Prove the board, chess arbiter, Stockfish seat, and real-time event loop on
one machine.

| Sub-phase | Deliverables |
| --- | --- |
| 1A Workspace | Monorepo skeleton, dependency management, Docker Compose, environment examples |
| 1B Chess domain | `python-chess` game service, legal move validation, FEN/PGN, terminal states, unit tests |
| 1C Board UI | Responsive board, human move input, move list, FEN/PGN copy, flip and reset |
| 1D Stockfish | UCI process manager, configurable strength/time, human-vs-engine match |
| 1E Live transport | WebSocket events, reconnect snapshot, authoritative server state |

**Exit gate:** A user can start a local human-vs-Stockfish game, finish it legally,
reload the page, replay it, and export valid PGN. CI is green.

### Stage 2 — Durable match platform

**Goal:** Turn the prototype into a reliable match service.

**Progress:** 2A through 2D are implemented. PostgreSQL is the production store,
SQLite is the contributor/test fallback, immutable events are sequence ordered,
match writes use a durable revision compare-and-swap, and restart-safe Fischer
clocks use server time. Idempotency records and fenced expiring turn leases coordinate
retries and workers. Minimal accounts remain the final Stage 2 increment.

| Sub-phase | Deliverables |
| --- | --- |
| 2A Persistence | PostgreSQL schema, migrations, matches, moves, and append-only events |
| 2B State machine | Created, waiting, running, paused, completed, aborted, and adjudicated transitions |
| 2C Clocks | Server-authoritative controls, deadlines, increments, timeouts, and resume behavior |
| 2D Concurrency | Position versions, idempotency, locks, duplicate prevention, and crash recovery |
| 2E Accounts | Minimal authentication, private/public match visibility, and owner controls |

**Exit gate:** Matches survive restarts, concurrent submissions cannot corrupt a
position, reconnects recover correctly, and clock/result tests are deterministic.

### Stage 3 — AI adapter platform

**Goal:** Seat hosted and local models through one normalized contract.

**Progress:** Stages 3A through 3F are implemented. Either color can use the versioned
player protocol through deterministic, Stockfish, OpenAI Responses, Anthropic
Messages, Google Gemini Interactions, OpenRouter Chat Completions, Ollama, or vLLM
adapters, and two automated seats can complete
an unattended persisted match. Hosted model and effort settings are independently
selectable for both seats when the model exposes a verified mapping; provider
credentials and local endpoint configuration stay server-side. Transient provider
failures now use a bounded retry budget inside the original chess clock; local request
budgets, outage circuits, sanitized recovery metadata, and an explicit operator retry
action prevent silent loops and unsafe substitutions.

| Sub-phase | Deliverables |
| --- | --- |
| 3A Protocol | **Implemented:** versioned MoveRequest/MoveProposal schemas, adapter SDK, scripted fake agents, dual-seat unattended runner |
| 3B OpenAI | **Implemented:** Responses API adapter, strict structured move output, effort mapping, usage normalization, and two-seat UI selection |
| 3C Anthropic | **Implemented:** Messages adapter, adaptive-thinking effort mapping, strict structured move output, usage normalization, and cross-provider UI selection |
| 3D Google | **Implemented:** Gemini Interactions adapter, model-specific thinking-level mapping, usage normalization, and cross-provider UI selection |
| 3E Open ecosystem | **Implemented:** OpenRouter/OpenAI-compatible plus local Ollama/vLLM connections, structured moves, honest effort disclosure, and hosted-versus-local UI setup |
| 3F Recovery | **Implemented:** bounded transient retries, rate limits, outage circuit, sanitized failure policy, reliability status, and operator retry control |

**Exit gate:** Two configured models can complete an unattended game; every move
has latency/usage metadata; failures produce an explicit result without board
corruption.

### Stage 4 — Lounge broadcast experience

**Goal:** Make live model competition striking, legible, and shareable.

**Progress:** The human-versus-Stockfish vertical slice now implements the Stage 4
broadcast shell across 4A–4F: disclosed player cards, structured public strategy,
local replay, isolated spectator Stockfish evaluation, stable match routes and exports,
and a five-viewport Playwright gate. Stage 3 adapters will populate normalized model,
effort, usage, and cost fields; Stage 2E will add explicit visibility permissions.

| Sub-phase | Deliverables |
| --- | --- |
| 4A Player presentation | Model cards, effort/division disclosure, clocks, status, latency, and cost |
| 4B Strategy channel | Structured public plan/threat/confidence banner with clear limitations |
| 4C Spectator controls | Pause local playback, jump to live, scrub, replay, flip, copy, and export |
| 4D Evaluation | Separate spectator Stockfish analysis, evaluation graph, PV, and move classifications |
| 4E Shareability | Public match pages, social-safe metadata, PGN/JSON downloads, and finished-game permalink |
| 4F Responsive QA | Desktop, tablet, phone, accessibility, latency/loading, and failure states |

**Exit gate:** A viewer can understand who is playing, under what settings, what
happened, what each agent publicly claims to be planning, and replay/share the game.

### Stage 5 — External agents, MCP, and subscription runners

**Goal:** Allow independently operated agents to join without browser control.

**Progress:** Stages 5A and 5B are implemented. The Lounge now creates one-time pairings,
issues digest-protected sessions scoped to one player, exposes heartbeat/presence,
delivers turns by authenticated WebSocket, allowlisted HTTPS webhook, or HTTP
long-poll, and accepts signed idempotent proposals through the existing authoritative
turn lease. Dependency-light Python and TypeScript clients claim pairings, long-poll
turns, bind and sign proposals, preserve idempotency across safe submission retries,
and include one-command deterministic sample bots.

| Sub-phase | Deliverables |
| --- | --- |
| 5A Remote runner | **Implemented:** one-time pairing, scoped session token, WebSocket/allowlisted webhook/HTTP turn transport, heartbeat, signed idempotent proposals, and UI seat selection |
| 5B Runner SDK | **Implemented:** Python and TypeScript reference clients with cross-language signing vectors and a one-command sample bot |
| 5C MCP facade | Implemented: local stdio create/join/watch/submit tools, polling/heartbeat, FEN/PGN resources, and deterministic full-game verification |
| 5D Subscription bridge | In progress: local Codex CLI sidecar, one-match authorization, capability detection, and deterministic full-game tests implemented; live acceptance blocked by CLI-reported usage limit |
| 5E Trust controls | Revocation, audit events, runner limits, secret isolation, and reconnect/forfeit rules |

**Exit gate:** A remote agent and one supported subscription-authenticated agent can
complete unattended games after a single explicit session authorization. No provider
credential reaches the Lounge server from the subscription bridge.

### Stage 6 — Human participation and mixed teams

**Goal:** Let the user sit at any table without weakening match integrity.

| Sub-phase | Deliverables |
| --- | --- |
| 6A Human seats | Legal drag/click moves, promotion, draw/resign, clocks, and reconnect |
| 6B Takeover | Pause-safe AI-to-human and human-to-AI seat handoff recorded as match events |
| 6C Consultation | AI suggestion card where only the human may submit the final move |
| 6D Permissions | Owner, player, spectator, moderator roles and private invitations |

**Exit gate:** Human-vs-model, human-vs-Stockfish, takeover, and consultation games
work on desktop and mobile with full audit history.

### Stage 7 — Model Lab and tournament system

**Goal:** Produce defensible comparisons instead of isolated exhibitions.

| Sub-phase | Deliverables |
| --- | --- |
| 7A Experiment builder | Entrants, effort sweep, opening suite, clocks, game count, color swaps, stop rules |
| 7B Scheduler | Durable queue, concurrency budgets, provider rate limits, resume, and cancellation |
| 7C Tournaments | Round robin, knockout, gauntlet, standings, and division-specific ratings |
| 7D Metrics | Chess strength, reliability, efficiency, effort response, confidence intervals |
| 7E Reports | Interactive comparisons and CSV/JSON/PGN experiment bundles |

**Exit gate:** A color-swapped, multi-opening model comparison can run to completion,
resume after interruption, and produce a reproducible report with configuration hash.

### Stage 8 — Production hardening and public beta

**Goal:** Operate safely for invited users and public spectators.

| Sub-phase | Deliverables |
| --- | --- |
| 8A Security review | Threat model, secret audit, dependency scan, abuse cases, SSRF and injection tests |
| 8B Operations | Health checks, tracing, metrics, alerts, backups, retention, and incident runbook |
| 8C Performance | Load tests for spectators, WebSockets, engine pool, tournament queue, and database |
| 8D Cost controls | Quotas, budget ceilings, per-match estimates, rate limits, and kill switches |
| 8E Beta release | Hosted standalone URL, onboarding, connection test, sample exhibition, and feedback loop |

**Exit gate:** Backups and restore are tested; secrets remain isolated; budget and
abuse controls work; launch checklist passes; rollback is documented.

### Stage 9 — Expansion after proof

Candidate additions, prioritized only after real use:

- Chess960 and additional variants
- Commentary agents and audience-selectable broadcast styles
- Opening/theme challenge packs
- Public profiles and season rankings
- Embeddable live boards
- Mobile install/PWA and notifications
- Agent marketplace/registry with signed capability manifests
- Team battles with multiple agents voting or debating through public summaries

---

## 12. Test strategy

| Layer | Required tests |
| --- | --- |
| Chess domain | Castling, en passant, promotion, repetition, fifty-move rule, insufficient material, mate, stalemate |
| State machine | Every allowed/forbidden transition, pause/resume, forfeit, abort, adjudication |
| Concurrency | Duplicate proposal, stale version, two runners, reconnect, crash between proposal and commit |
| Adapter contracts | Schema, effort mapping, usage mapping, retryable/fatal errors, malformed output |
| Stockfish | UCI startup, option validation, timeout, process crash, pool recovery, version capture |
| WebSocket | Snapshot then ordered events, missed sequence recovery, reconnect, backpressure |
| UI | Move entry, promotion, replay, responsive layouts, keyboard, screen-reader announcements |
| Security | Secret redaction, authorization matrix, runner scope, token expiry, SSRF, prompt/log leakage |
| Experiment | Color swap, opening assignment, deterministic schedule, cancellation, resume, report integrity |

Release branches must pass formatting, linting, unit tests, contract tests, build,
database migration checks, and a short end-to-end game using deterministic adapters.
Board-facing changes also pass the viewport and interaction states in
[`UI_QA_MATRIX.md`](UI_QA_MATRIX.md).

---

## 13. Deployment path

The project remains host-neutral and receives its own public URL.

### Local development

- Docker Compose starts web, API, PostgreSQL, Redis, and Stockfish worker
- `.env.example` documents configuration without secrets
- Deterministic fake agents let contributors work without paid API access

### First hosted environment

- Independently deploy the web client and Python API/workers
- Managed PostgreSQL and Redis
- Container runtime that permits Stockfish processes and explicit CPU/memory limits
- TLS, custom domain, environment secret store, and preview deployments for pull
  requests where economical

### Scaling sequence

1. Single API instance plus one match/engine worker
2. Separate match and analysis pools
3. Redis-backed distributed leases and queues
4. Multiple API instances with shared WebSocket/pub-sub transport
5. Regional spectator delivery only after measured demand

Avoid premature microservices. Service boundaries exist in code first and become
separate deployments only when load, isolation, or reliability justifies it.

---

## 14. Contribution workflow for humans and agents

1. Read `README.md`, `AGENTS.md`, this plan, and the relevant ADRs.
2. Create or claim a narrowly scoped issue.
3. Work on a branch; do not rewrite shared history.
4. Keep changes minimal and include tests for behavior.
5. Update documentation when contracts, environment, schemas, or architecture change.
6. Open a pull request describing intent, implementation, verification, risks, and
   follow-ups.
7. Require CI and review before merge once code work begins.

Direct pushes to `main` should be disabled after repository bootstrap. The owner and
authorized agents can push branches; outside contributors use forks or branches and
pull requests according to GitHub permissions.

---

## 15. Initial backlog

| Priority | Item | Stage |
| --- | --- | --- |
| P0 | Bootstrap monorepo, Docker Compose, formatting, linting, and CI | 1A |
| P0 | Define domain types and versioned MoveRequest/MoveProposal JSON Schemas | 1B/3A |
| P0 | Implement game aggregate with `python-chess` and exhaustive rule tests | 1B |
| P0 | Build responsive human board and move/replay controls | 1C |
| P0 | Implement sandboxed Stockfish UCI adapter and human-vs-engine loop | 1D |
| P0 | Add WebSocket snapshot/event protocol and reconnect test | 1E |
| P1 | Add PostgreSQL event persistence and match state machine | 2A/2B |
| P1 | Add durable server-authoritative clocks and timeout recovery | 2C |
| P1 | Add scripted/fake agent contract harness | 3A |
| P1 | Add first hosted-model adapter with strict structured move output | 3B |
| P1 | Build model-vs-model match creation flow | 3F |
| P2 | Add strategy banner, PGN/FEN panels, and spectator engine evaluation | 4 |
| P2 | Add remote runner and reference SDK | 5A/5B |

---

## 16. Definition of the first meaningful release

Version `0.1.0` is complete when:

- The project runs locally from documented commands
- A human can play Stockfish at selected strength
- Two API-backed models can play an unattended legal game
- Stockfish can occupy either seat against a model
- The UI shows live board state, clocks, model identity/configuration, strategy
  summaries, PGN, FEN, and replay controls
- Games survive refresh/reconnect and export correctly
- Illegal move, timeout, provider failure, and engine crash paths are tested
- API keys are protected and never logged
- The match record includes model/provider versions, effort, division, latency,
  tokens, cost estimate, Stockfish settings/version, and configuration hash
- The application is deployed to a standalone URL

---

## 17. Reference foundations

Implementation should verify current provider documentation before pinning a model,
effort value, or authentication route. Relevant foundations include:

- OpenAI Responses API reasoning and Structured Outputs documentation
- Anthropic Messages API effort/thinking and MCP documentation
- Google Gemini thinking controls and OpenAI-compatible API documentation
- `python-chess` board, PGN, and UCI engine APIs
- Stockfish UCI configuration and distribution requirements
- Model Context Protocol tool and authorization specifications

Provider features and subscription authentication are capability-detected. The
product must never promise a subscription route that the provider does not officially
permit at the time of connection.
