import { useEffect, useRef, useState } from "react";
import { cancelConsultation, fetchGame, playConsultation, requestConsultation } from "./api";
import type { Consultation, EffortLevel, GameSnapshot, PlayerAdapterCatalog, PlayerConfiguration } from "./types";

const providers: Record<string, string> = { scripted: "Practice adviser", stockfish: "Stockfish", openai: "OpenAI", anthropic: "Anthropic", google: "Google", openrouter: "OpenRouter", ollama: "Ollama", vllm: "vLLM" };
const effortLevels: EffortLevel[] = ["fast", "balanced", "deep", "maximum"];

export function ConsultationPanel({ game, catalog, enabled, onSnapshot }: {
  game: GameSnapshot; catalog: PlayerAdapterCatalog | null; enabled: boolean;
  onSnapshot: (snapshot: GameSnapshot) => void;
}) {
  const [selection, setSelection] = useState("scripted:deterministic-v1");
  const [effort, setEffort] = useState<EffortLevel>("balanced");
  const [elo, setElo] = useState(1600);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirm, setConfirm] = useState<{ advice: Consultation; revision: number } | null>(null);
  const choices = (catalog?.adapters ?? []).filter(a => a.adapter_id in providers).flatMap(a =>
    a.models.filter(model => {
      const cap = a.capabilities[model];
      return ["stockfish", "scripted"].includes(a.adapter_id) ? cap?.available !== false : cap?.selectable === true;
    }).map(model => ({ key: `${a.adapter_id}:${model}`, adapter: a.adapter_id, model, cap: a.capabilities[model] })));
  const choice = choices.find(c => c.key === selection) ?? choices[0];
  const efforts = choice?.adapter === "stockfish" ? [] : effortLevels.filter(e => choice?.cap.effort_levels?.includes(e));
  const actualEffort = efforts.includes(effort) ? effort : efforts[0] ?? null;
  const latest = game.consultations?.at(-1);
  const pending = latest?.status === "pending";
  const humanTurn = game.lifecycle === "running" && game[game.turn === "white" ? "white_player" : "black_player"].adapter_id === "human";
  const canAct = enabled && humanTurn && !busy;
  useEffect(() => { setConfirm(null); }, [game.id, game.revision, enabled]);

  useEffect(() => {
    if (!pending || !latest || !enabled) return;
    const delay = Math.max(100, Date.parse(latest.deadline_at) - Date.parse(game.clock.server_time) + 500);
    const timer = window.setTimeout(() => { void fetchGame(game.id).then(onSnapshot).catch(() => {}); }, delay);
    return () => window.clearTimeout(timer);
  }, [pending, latest?.id, latest?.deadline_at, game.id, game.clock.server_time, enabled, onSnapshot]);

  async function action(work: () => Promise<GameSnapshot>) {
    setBusy(true); setError(null);
    try { onSnapshot(await work()); }
    catch (e) {
      setError(e instanceof Error ? e.message : "Consultation failed.");
      try { onSnapshot(await fetchGame(game.id)); } catch { /* Preserve the original error. */ }
    } finally { setBusy(false); setConfirm(null); }
  }

  function ask() {
    if (!canAct || !choice || pending) return;
    const advisor: PlayerConfiguration = {
      protocol_version: "1.0", player_id: crypto.randomUUID(), adapter_id: choice.adapter,
      display_name: `${providers[choice.adapter]} · ${choice.model}`, provider: providers[choice.adapter], model: choice.model,
      connection_mode: choice.cap.connection_mode ?? (["stockfish", "scripted"].includes(choice.adapter) ? "local" : "direct_api"),
      division: choice.adapter === "stockfish" ? "engine_assisted" : "legal_assist", effort: actualEffort,
      settings: { move_timeout_ms: 20_000, ...(choice.adapter === "stockfish" ? { target_elo: elo, move_time_ms: 450 } : {}) },
    };
    void action(() => requestConsultation(game.id, advisor, game.revision));
  }

  return <section className="consultation-panel" aria-label="Human AI consultation">
    <p className="eyebrow">HUMAN + AI TEAM · EXHIBITION</p>
    <h3>Ask an adviser</h3>
    <p>You choose the move. Your clock keeps running while the adviser thinks.</p>
    <div className="consultation-options">
      <label>Adviser model<select aria-label="Adviser model" value={choice?.key ?? ""} onChange={e => setSelection(e.target.value)} disabled={busy || pending}>
        {choices.map(c => <option key={c.key} value={c.key}>{providers[c.adapter]} · {c.model}</option>)}
      </select></label>
      {efforts.length > 0 && <label>Adviser effort<select aria-label="Adviser effort" value={actualEffort ?? ""} onChange={e => setEffort(e.target.value as EffortLevel)} disabled={busy || pending}>
        {efforts.map(e => <option key={e} value={e}>{e}</option>)}
      </select></label>}
      {choice?.adapter === "stockfish" && <label>Adviser strength<select aria-label="Adviser strength" value={elo} onChange={e => setElo(Number(e.target.value))} disabled={busy || pending}>
        {[1320, 1600, 2000, 2500, 3190].map(value => <option key={value} value={value}>{value} target Elo</option>)}
      </select></label>}
    </div>
    <button className="consultation-ask" disabled={!canAct || !choice || pending} onClick={ask}>{pending ? "Adviser thinking…" : "Request suggestion"}</button>
    {!humanTurn && <small>Available when a human is on move in a running match.</small>}
    {pending && <button disabled={!enabled || busy} onClick={() => void action(() => cancelConsultation(game.id, latest.id, game.revision))}>Cancel consultation</button>}
    {error && <p role="alert">{error}</p>}
    {latest && <article className="suggestion-card" aria-label="Latest suggestion" aria-live="polite">
      <small>{latest.advisor.display_name} · {latest.color} · {latest.status}</small>
      {latest.san && <h4>Suggested move: {latest.san}</h4>}
      {latest.plan && <p>{latest.plan}</p>}
      {latest.threat && <p><strong>Watch for:</strong> {latest.threat}</p>}
      {latest.latency_ms !== null && <small>{(latest.latency_ms / 1000).toFixed(1)}s · {latest.advisor.effort ?? "Default effort"} · {latest.advisor.division.replaceAll("_", " ")}</small>}
      {latest.usage && <small>Tokens: {latest.usage.input_tokens ?? "—"} in / {latest.usage.output_tokens ?? "—"} out · Cost: {latest.usage.estimated_cost_usd == null ? "unreported" : `$${latest.usage.estimated_cost_usd.toFixed(4)}`}</small>}
      {latest.error && <p>{latest.error}</p>}
      {latest.status === "ready" && <><p>Play this suggestion or make your own move on the board.</p><button disabled={!canAct} onClick={() => setConfirm({ advice: latest, revision: game.revision })}>Review suggested move</button></>}
      {latest.status === "stale" && <p>This advice belongs to an earlier turn or an expired request. Request fresh advice for the current position.</p>}
    </article>}
    {!!game.consultations?.length && <details><summary>Consultation history · {game.consultations.length}</summary><ol>
      {game.consultations.map(c => <li key={c.id}>{c.color} · after ply {c.after_ply} · {c.advisor.display_name} · {c.san ?? "No published move"} · {c.status}</li>)}
    </ol></details>}
    <small>Public suggestions only. Assistance is recorded in game history and PGN. API advisers use your configured provider account. Remote runner advisers are not supported yet.</small>
    {confirm && <ConfirmSuggestion advice={confirm.advice} busy={busy} onCancel={() => setConfirm(null)} onPlay={() => {
      if (!canAct || game.revision !== confirm.revision) return;
      void action(() => playConsultation(game.id, confirm.advice, confirm.revision));
    }} />}
  </section>;
}

function ConfirmSuggestion({ advice, busy, onPlay, onCancel }: { advice: Consultation; busy: boolean; onPlay: () => void; onCancel: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => { const element = dialog.current; element?.showModal(); return () => element?.close(); }, []);
  return <dialog ref={dialog} className="promotion-dialog human-action-dialog" aria-labelledby="suggestion-title" onCancel={e => { e.preventDefault(); if (!busy) onCancel(); }}>
    <h2 id="suggestion-title">Play {advice.san}?</h2><p>This submits your human move. You can cancel and choose a different move.</p>
    <div className="secondary-actions"><button autoFocus disabled={busy} onClick={onCancel}>Cancel</button><button disabled={busy} onClick={onPlay}>Confirm suggested move</button></div>
  </dialog>;
}
