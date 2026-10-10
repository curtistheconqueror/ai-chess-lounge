# Project Chimera v2: an engine pipeline that climbs the Stockfish ladder

Status: **PARKED** (2026-10-10). Blueprint only, nothing built yet.
Owner: Curtis. Home: this repository (`ai-chess-lounge`), branch `docs/chimera-blueprint`.
When it's built, the engine lives under `chimera/` in this repo, not in a separate repo.

**Owner decisions (2026-10-10):**

1. **Brain data: both tracks.** Chimera-Pure (self-play only) and Chimera-Distilled
   (Stockfish-labeled positions) are built as two separately identified entrants. See
   section 2a.
2. **Location:** this repo, as above.
3. **API budget:** up to **$200/week** as a hard ceiling. Expected spend is well below
   that (section 4).

---

## 0. The honest goal statement

"Beat Stockfish on any setting" is really five targets of very different difficulty. The
pipeline is built to climb them in order. Each rung counts as cleared only when a
statistically significant result says so.

| Rung | Opponent | Difficulty | Realistic? |
|---|---|---|---|
| R0 | Stockfish Skill 0 / `UCI_Elo` 1320 | Easy | Yes, phase 1 |
| R1 | `UCI_Elo` ~2000 | Moderate | Yes, phase 1-2 |
| R2 | `UCI_Elo` 2600 | Hard | Yes, phase 2 |
| R3 | `UCI_Elo` 3190 (the max limited setting) | Very hard: needs a real NNUE engine | Plausible, phase 3 |
| R4 | Full-strength Stockfish **with odds** (node, time or hardware handicap) | Measurable and shrinkable gap | Ongoing, phase 4 |
| R5 | Full-strength Stockfish at **equal** conditions | Moonshot | Very unlikely at this budget |

R5 context: Stockfish is the product of hundreds of contributors and a distributed test
farm (Fishtest) that has run billions of games over years. At equal conditions, top
engine games are mostly draws. Even the strongest rivals (Leela on big GPUs) rarely
outscore it. R5 belongs in the plan as a direction, not a promise. R0-R3 are
achievable, R4 is a scoreboard that can keep improving, and all of them make great
Lounge content.

---

## 1. What changes from the original blueprint, and why

| Original idea | Problem | v2 replacement |
|---|---|---|
| Python plugins choose moves (`select_move`, `evaluate_position`) | Python is roughly 100-1000x slower than C++/Rust search. Without deep search, no eval heuristic survives Stockfish tactics. Positional insight is worthless if you hang a piece at depth 6. | The LLM writes and evolves a **compiled engine** (Rust). Strategy ideas become eval features and search heuristics *inside* that engine. |
| Fitness = centipawn loss measured by Stockfish | You can't surpass a teacher by minimizing distance to the teacher. This caps you below Stockfish by construction. | Fitness = **game results** under SPRT (the same statistical gate Stockfish uses). Proxies are kept as diagnostics only. |
| "Evaluation volatility", "mobility starvation" as fitness | Goodhart traps: the evolution will learn to game the proxy (e.g. close positions and shuffle) instead of winning. | Diagnostics dashboards only. Never used for accept/reject. |
| `importlib` hot-loading LLM code into the harness process | No isolation: a crash, infinite loop or malicious/accidental file or network access hits the host. THECUBE also runs live trading services. | Build in a sandbox (WSL2/Docker, no network, CPU/RAM caps, separate user). Run engines as separate **UCI processes**. |
| Silent fallback when the plugin returns an illegal move (and `square_mirror` used on a move list) | Masks bugs and inflates results. The Lounge's own rules forbid silent move substitution. | An illegal move = an immediate loss plus a bug report. Perft and unit gates catch these before any games are played. |
| Vector DB "elitism repository" | Opaque, and retrieval quality is hard to verify. | **Git is the archive.** Every accepted patch is a commit with its hypothesis and SPRT result. Rejected ideas go to a "graveyard" log so they aren't retried. |
| "AlphaZero parity on local hardware" | Unsupported claim. | Dropped. The defensible claim is "LLM-driven engine R&D with a rigorous test gate." |

**The thesis that survives:** the LLM is a meta-architect, not a player. That part of
the original was right. The upgrade is to make it a **tireless engine developer whose
every idea is judged by statistics**, which is how engine strength is actually built.

---

## 2. Architecture

```
            ┌─────────────────────────────────────────────────────┐
            │ RESEARCH DIRECTOR (Fable 5.1, occasional)           │
            │ reads results + graveyard -> new idea families,     │
            │ audits stats, root-causes deep bugs                 │
            └──────────────┬──────────────────────────────────────┘
                           │ idea backlog
            ┌──────────────▼──────────────────────────────────────┐
            │ PROPOSERS (Sonnet 5.5 / Opus 5.5, many)             │
            │ one hypothesis -> one small patch + expected effect │
            └──────────────┬──────────────────────────────────────┘
                           │ patch
  ┌────────────────────────▼───────────────────────────────────────────┐
  │ SANDBOXED GATE PIPELINE (no LLM; deterministic)                    │
  │ 1 build  2 perft suite  3 bench/node determinism  4 tactics smoke  │
  │ 5 early-reject mini match vs champion  6 SPRT vs champion          │
  └────────────────────────┬───────────────────────────────────────────┘
          pass │                                   │ fail
  ┌────────────▼────────────┐          ┌───────────▼────────────┐
  │ git commit = new        │          │ graveyard.jsonl        │
  │ champion (+ SPRT log)   │          │ (idea, diff, result)   │
  └────────────┬────────────┘          └────────────────────────┘
               │ nightly
  ┌────────────▼────────────────────────────────────────────────┐
  │ LADDER RUN vs Stockfish rungs R0-R4 -> rating vs each rung  │
  │ with confidence interval -> published to the Lounge         │
  └─────────────────────────────────────────────────────────────┘

  Side loop (Phase 3+): self-play data gen (CPU) -> NNUE training (GPU) -> net SPRT
```

### Components

- **Engine (Rust):** bitboard move generation, PVS alpha-beta, quiescence search,
  transposition table, iterative deepening, time management, UCI. HCE (hand-crafted
  eval) first, NNUE later. Written clean-room from public references (the
  chessprogramming wiki). Don't paste GPL engine code: the Lounge is MIT, and owning
  the engine outright matters.
- **Match runner:** `fastchess` (or `cutechess-cli`) with balanced opening books
  (e.g. UHO-style sets, as Fishtest uses) and both colors per opening.
- **Statistics:** SPRT with Elo bounds per stage (big bounds early, e.g. [0, 10];
  tight later, [0, 2]), plus pentanomial scoring. No "it won 7 of 10, ship it."
- **Tuning (no LLM):** Texel/SPSA tuning of numeric parameters. LLMs are bad at
  picking constants; optimizers are good at it.
- **NNUE trainer:** an existing open-source trainer (e.g. `bullet`) on the local GPU.
  It's fed by two data tracks (section 2a). Check dataset and tool licenses before use.
- **Strategist research track:** the original Chimera ideas (prophylaxis, zugzwang,
  fortress detection, closed-position planning) become **curated test suites** plus
  **candidate eval features**. Example: engines still misjudge many fortress
  positions. A fortress-detection feature that passes SPRT is a real, publishable
  win.

### 2a. Two brains, one engine

The search code is shared. Only the neural net and its training data differ.

| | Chimera-Distilled | Chimera-Pure |
|---|---|---|
| Training labels | Positions scored by Stockfish at a fixed search depth | Results and scores from Chimera's own self-play only |
| Speed to strength | Fast: borrows Stockfish's judgment | Slower: bootstraps from nothing, many generations |
| Claim it supports | "Our engine + a distilled brain" | "Intelligence built entirely by our pipeline" |
| Ceiling | Tends to inherit the teacher's blind spots | No teacher ceiling, but needs far more compute |
| Datagen cost | CPU: Stockfish labeling time | CPU: self-play time across repeated generations |

Rules:

- **Order:** Distilled first, to validate the trainer, inference code and SIMD path
  with a fast signal. Pure starts once that plumbing is proven, and runs at lower
  priority in the background.
- **Provenance:** every net file carries its track, data sources, generation and
  hash. The two are separate entrants in Lounge configuration identities and
  leaderboards. They're never pooled.
- **No mixing:** a Pure net never sees Stockfish-labeled data, not even for warm
  starts. Mixed experiments, if wanted, become a third, labeled identity.
- **Scoreboard:** both climb the same Stockfish ladder. The gap between them is
  itself a result worth publishing.

---

## 3. Phases, gates and expected strength

The Elo figures are rough expectations on an engine-list scale (CCRL-like). Stockfish's
`UCI_Elo` scale isn't identical, and real numbers come from our own ladder runs.

| Phase | Work | Duration (agent-driven) | Expected strength | Exit gate |
|---|---|---|---|---|
| **P0 Harness** | fastchess + pinned Stockfish build + opening books + SPRT + results DB + resource caps + nightly ladder script. Baselines: random mover, LLM-direct via the Lounge adapters. | 1-3 days | n/a | Reproducible "engine X vs SF `UCI_Elo` N: score, Elo ± CI" report |
| **P1 Core engine** | perft-verified movegen, alpha-beta + qsearch, TT, ID, time management, UCI, material + tapered PST eval | ~1 week | ~1800-2200 | Clears R0 and R1 |
| **P2 Evolution loop on** | Proposer agents + gate pipeline + git archive. Standard search wins (null move, LMR, futility, killers/history, SEE, aspiration windows) plus Texel tuning. | 1-3 weeks | ~2500-2900 | Clears R2. Acceptance rate tracked. |
| **P3 NNUE brain** | self-play datagen, train small nets, SIMD inference, iterate nets via SPRT | 2-6 weeks | ~3000-3300+ | Clears R3 (`UCI_Elo` 3190). This is "any limited setting." |
| **P4 Odds ladder** | vs full SF at 10k, 100k and 1M nodes, then time odds. Strategist research track. Director-driven idea families. | open-ended | climbing | Gap to full SF shrinks, measured monthly |
| **P5 Lounge productization** | Chimera seat, ladder dashboard, Strategist commentary/coach | parallel from P2 | n/a | See section 6 |

Diminishing returns are the defining dynamic. Early patches are worth +20 to +200 Elo
and pass SPRT in a few hundred games. Late patches are worth +1 to +3 Elo and need
tens of thousands of games. **Compute, not LLM cleverness, becomes the bottleneck
from P2 onward.**

---

## 4. Compute: what Curtis's machine has to do

THECUBE has an i7-14700F (20 cores / 28 threads), 32 GB RAM and an RTX 5070 (12 GB).
That's enough for everything through P3.

| Workload | Where | Load |
|---|---|---|
| Building, perft, unit gates | Local sandbox | Seconds per patch |
| SPRT matches | Local CPU | At ~10s+0.1s games and ~16 concurrent games: very roughly 2,000-3,000 games/hour. Early SPRTs take minutes; late ones take hours. |
| Nightly Stockfish ladder | Local CPU | A few hundred games per rung, overnight |
| Self-play data gen (P3) | Local CPU (or burst) | Hundreds of millions of positions = days of CPU. This is the heaviest job. |
| NNUE training (P3) | Local RTX 5070 | Small NNUE nets train comfortably on 12 GB, in hours per net |
| LLM calls | Anthropic API or the Claude Code subscription | No local compute |

**Hard rule for THECUBE:** cap the pipeline at about 12-16 threads, at below-normal
priority. Run heavy jobs off-hours (outside the 08:00 CT trading window), never touch
:9222 or the trading ports, and have a kill switch. The trading stack outranks chess.

**Optional burst compute** (only if P3/P4 stall on throughput): rent a 32-64 vCPU box
for a weekend of datagen/SPRT. Rough estimate is tens of dollars per weekend; verify
current provider pricing before renting. Don't use GitHub Actions minutes as a
compute farm (ToS risk).

**LLM spend (rough, Anthropic list prices as of 2026-09):**

- Proposer patch on Sonnet 5.5 ($2/$10 per MTok, cache reads $0.20): ~40k cached
  input + ~8k output comes to **about $0.10-0.20 per proposal**. Opus 5.5 ($4/$20) is
  about 2x that.
- Director session on Fable 5.1 ($10/$50): ~150k input + ~30k output comes to **about
  $2-4 per session**.
- Throughput is capped by SPRT, at roughly 15-40 proposals/day. That's **about
  $3-10/day** at full tilt, plus maybe $10-30/week for the Director. Non-urgent
  proposals can use the Batch API (50% off). Driving it interactively through a
  Claude Code subscription makes the marginal cost close to zero.
- **Budget guard:** the hard ceiling is **$200/week**. The pipeline tracks spend per
  call, alerts at 50%, and stops proposing (matches keep running) at 100%. The
  expected range is about $20-100/week at full tilt.

---

## 5. Where Fable-level reasoning is (and isn't) needed

| Step | Model | Why |
|---|---|---|
| Blueprint and evaluation-protocol design (this doc, P0 review) | **Fable 5.1**, one-off | Wrong stats or wrong goals poison months of results |
| Writing P0/P1 code (harness, movegen, search) | Opus 5.5 / Sonnet 5.5 | Well-documented techniques; correctness is checked by perft |
| Routine proposer patches (P2+) | Sonnet 5.5 (Opus 5.5 for trickier search work) | High volume; SPRT catches bad ideas cheaply |
| Parameter tuning | **No LLM** (Texel/SPSA) | Optimizers beat LLMs at constants |
| Running matches, parsing results | **No LLM** | Deterministic scripts |
| **Silent-Elo-leak debugging** (TT corruption, mate-score bugs, repetition/50-move handling, time losses, SMP races) | **Fable 5.1** | These are the subtle, multi-file reasoning problems where the top model pays for itself |
| **Plateau research director**: when SPRT acceptance falls below ~1 in 10 for a week, read the archive + graveyard and propose *new idea families* (eval architecture, extensions, fortress/zugzwang features) | **Fable 5.1**, weekly | Novelty and synthesis across long history |
| Statistical-integrity audits (book bias, time-control mismatch, data leakage, overfitting to one Stockfish version) | **Fable 5.1**, monthly | Self-deception is the main risk of evolution loops |
| Strategist commentary / coaching in the Lounge | Sonnet 5.5 / Haiku 4.5 | Explains the engine's plan; it doesn't decide moves |

Rule of thumb: Fable for **judgment over long history and subtle correctness**, cheaper
models for **volume**, and no model at all where an optimizer or script will do.

---

## 6. How it fits the AI Chess Lounge

The Lounge is the **arena, scoreboard and audit trail**, not the inner training loop.
The inner loop needs thousands of fast games per hour, while the Lounge deliberately
adds server-authoritative clocks, events, persistence and WebSockets.

1. **Chimera seat, day one, no server changes:** a thin Python runner built on
   `packages/runner-sdk-python` drives the Chimera UCI binary as a remote-runner seat.
   That works with today's pairing flow. Later, add Chimera as a first-class engine
   seat next to Stockfish (out-of-process UCI with resource limits, the same
   guardrail Stockfish already follows).
2. **Model Lab ladder:** Stage 7's gauntlets, tournaments and report bundles run the
   official "Chimera vs Stockfish ladder" showcase. Leaderboards show score, games
   and CI per rung, and keep Stockfish target Elo and Skill Level visibly separate
   (ADR0039).
3. **Honest divisions:** Chimera is an *engine* entrant, not an "AI model" seat. LLM
   authorship is disclosed in its configuration identity. This respects AGENTS.md's
   assistance-division and disclosure rules.
4. **LLM-direct exhibitions:** frontier models playing Stockfish rungs directly via
   the existing adapters. Great content, and a baseline that shows why the
   meta-architect approach exists.
5. **Strategist and lifelines:** the Strategist explains Chimera's plans as public
   strategy text. A capped Chimera could later power the "lifeline" idea (opt-in
   limited help while behind) under the Stage 6C consultation rules. That is
   currently deferred.
6. **Progress page:** the nightly ladder results feed a Lounge dashboard showing the
   rung reached, Elo vs each rung, and the gap to full Stockfish over time.

---

## 7. Risks and how they're contained

- **Self-deception** (lucky streaks, opening bias, testing at one time control). The
  SPRT gate, balanced books, both colors, periodic re-test of the champion at a
  longer time control, and Fable audits.
- **Runaway agent code.** The sandbox has no network and capped resources. Agents
  only produce patches; the gate pipeline (not the agent) decides what merges.
- **THECUBE contention.** Thread caps, low priority, off-hours scheduling, kill switch.
- **License contamination.** This repo is MIT, so the engine must be clean-room:
  never paste GPL engine code (Stockfish included) into `chimera/`. Running the
  Stockfish binary as an opponent or labeler is fine; copying its source is not.
  Record data provenance per net.
- **Repo weight.** Large artifacts (nets, datasets, PGN dumps) stay out of git. Use
  release assets or external storage with hashes in the repo. The Chimera CI job is
  separate, so Lounge CI stays fast.
- **Plateau before R3.** That's expected. It's the trigger for NNUE (P3) and for the
  Director. If P3 nets stall, the burst-compute datagen is the lever.

---

## 8. Immediate next actions (when unparked)

1. ~~Owner decisions~~ Done 2026-10-10: both data tracks, this repo, $200/week cap.
2. Fable 5.1 review pass on this blueprint and the P0 statistics protocol.
3. Build P0 harness in the sandbox; produce the first baseline ladder report
   (random mover and one LLM-direct seat vs R0).
4. Start P1 engine core; perft gate green before any games.

Reference read: r/LocalLLaMA "What Happens When LLMs Play Chess? And the
Implications for AGI" (Nov 2024). Only the title and snippet were retrievable: Reddit
blocked automated fetch. The well-known takeaway from that period still holds and
motivates this design. Chat LLMs playing directly are weak and error-prone against
engines; the gap is spatial and calculation-bound, not knowledge-bound.
