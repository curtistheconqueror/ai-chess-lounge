import { ExperimentRunPanel } from "./ExperimentRunPanel";
import { useEffect, useState } from "react";
import { fetchExperiment, listExperiments, previewExperiment, saveExperiment } from "./api";
import type { EffortLevel, PlayerAdapterCatalog, PlayerConfiguration } from "./types";

export interface ExperimentConfig {
  name: string; entrants: { key: string; player: PlayerConfiguration; efforts: (EffortLevel | null)[] }[];
  openings: { name: string; moves: string[] }[]; repetitions: number; color_swap: boolean;
  initial_time_ms: number; increment_ms: number;
  stops: { max_plies: number; max_failures: number; max_wall_time_ms: number };
}
export type TournamentFormat = "round_robin" | "gauntlet" | "knockout";
export interface TournamentExperimentConfig extends ExperimentConfig {
  schema_version: "2.0";
  format: TournamentFormat;
  anchor: string | null;
}
export type ExperimentConfiguration = ExperimentConfig | TournamentExperimentConfig;
export function isTournamentConfig(config: ExperimentConfiguration): config is TournamentExperimentConfig {
  return "schema_version" in config && config.schema_version === "2.0";
}
export interface ExperimentPlan {
  id?: string; configuration: ExperimentConfiguration; configuration_hash: string; game_count: number;
  exhibition: boolean; warnings: string[];
  schedule: { number: number; white: string; black: string; opening: string; repetition: number; series?: string | null; round?: number | null }[];
  tournament?: { format: TournamentFormat; series: { id: string; round: number; white: string; black: string; numbers: number[] }[]; rating_spec: string };
}
export interface ExperimentSummary { id: string; name: string; game_count: number; configuration_hash: string }
const effortLevels: EffortLevel[] = ["fast", "balanced", "deep", "maximum"];
const providerNames: Record<string, string> = { scripted: "Reference", stockfish: "Local UCI", openai: "OpenAI", anthropic: "Anthropic", google: "Google", openrouter: "OpenRouter", ollama: "Ollama", vllm: "vLLM" };
const allowed = ["scripted", "stockfish", "openai", "anthropic", "google", "openrouter", "ollama", "vllm"];

export function ModelLab({ catalog }: { catalog: PlayerAdapterCatalog | null }) {
  const choices = (catalog?.adapters ?? []).filter(a => allowed.includes(a.adapter_id)).flatMap(a => a.models.filter(model => a.adapter_id === "scripted" || (a.adapter_id === "stockfish" ? a.capabilities[model]?.available !== false : a.capabilities[model]?.selectable === true)).map(model => ({ key: `${a.adapter_id}:${model}`, adapter: a.adapter_id, model, cap: a.capabilities[model] })));
  const [entrants, setEntrants] = useState([{ key: "A", model: "scripted:deterministic-v1", efforts: [] as EffortLevel[], elo: 1600 }, { key: "B", model: "scripted:deterministic-v1", efforts: [] as EffortLevel[], elo: 1600 }]);
  const [name, setName] = useState("My first comparison");
  const [openings, setOpenings] = useState("Start |\nOpen game | e2e4 e7e5\nQueen pawn | d2d4 d7d5");
  const [repetitions, setRepetitions] = useState(1);
  const [swap, setSwap] = useState(true);
  const [seconds, setSeconds] = useState(300);
  const [increment, setIncrement] = useState(2);
  const [maxPlies, setMaxPlies] = useState(300);
  const [maxFailures, setMaxFailures] = useState(3);
  const [minutes, setMinutes] = useState(60);
  const [format, setFormat] = useState<"comparison" | TournamentFormat>("comparison");
  const [anchorKey, setAnchorKey] = useState<string | null>(null);
  const [plan, setPlan] = useState<ExperimentPlan | null>(null);
  const [saved, setSaved] = useState<ExperimentSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [saveId, setSaveId] = useState(() => crypto.randomUUID());
  const [offset, setOffset] = useState(0);
  useEffect(() => { let active = true; void listExperiments(offset).then(s => { if (active) setSaved(s); }).catch(e => { if (active) setError(String(e)); }); return () => { active = false; }; }, [offset]);
  function invalidate() { setPlan(null); setError(null); setSaveId(crypto.randomUUID()); }
  function selectedEfforts(e: typeof entrants[number]): (EffortLevel | null)[] {
    const c = choices.find(c => c.key === e.model);
    if (!c) return [];
    const levels = c.adapter === "stockfish" ? [] : effortLevels.filter(v => c.cap.effort_levels?.includes(v));
    return e.efforts.length ? e.efforts : levels.length ? [levels[0]] : [null];
  }
  const tournamentVariants = entrants.flatMap(e => selectedEfforts(e).map(effort => ({
    key: `${e.key}:${effort ?? "default"}`,
    label: `${e.key} · ${effort ?? "provider default"}`,
  })));
  const selectedAnchor = tournamentVariants.some(v => v.key === anchorKey) ? anchorKey! : tournamentVariants[0]?.key ?? "";
  function configuration(): ExperimentConfiguration {
    const base: ExperimentConfig = { name, entrants: entrants.map(e => {
      const c = choices.find(c => c.key === e.model);
      if (!c) throw new Error("Select an available model for each entrant.");
      const efforts = selectedEfforts(e);
      return { key: e.key, efforts, player: { protocol_version: "1.0", player_id: e.key, adapter_id: c.adapter, display_name: `${e.key} · ${c.model}`, provider: providerNames[c.adapter], model: c.model,
        connection_mode: c.cap.connection_mode ?? "local", division: c.adapter === "stockfish" ? "engine_assisted" : "legal_assist", effort: efforts[0], settings: { move_timeout_ms: 20_000, ...(c.adapter === "stockfish" ? { target_elo: e.elo, move_time_ms: 450 } : {}) } } };
    }), openings: openings.split("\n").filter(l => l.trim()).map(l => { const [label, moves, ...extra] = l.split("|"); if (moves === undefined || extra.length) throw new Error("Use one opening per line: Name | UCI moves"); return { name: label.trim(), moves: moves.trim() ? moves.trim().split(/\s+/) : [] }; }), repetitions, color_swap: swap, initial_time_ms: seconds * 1000, increment_ms: increment * 1000, stops: { max_plies: maxPlies, max_failures: maxFailures, max_wall_time_ms: minutes * 60_000 } };
    if (format === "comparison") return base;
    return { ...base, schema_version: "2.0", format, anchor: format === "gauntlet" ? selectedAnchor : null };
  }
  async function preview() { setBusy(true); setError(null); try { setPlan(await previewExperiment(configuration())); } catch (e) { setError(String(e)); } finally { setBusy(false); } }
  async function save() { if (!plan || plan.id) return; setBusy(true); setError(null); try { setPlan(await saveExperiment(saveId, plan.configuration)); setSaved(await listExperiments(offset)); } catch (e) { setError(String(e)); } finally { setBusy(false); } }
  async function load(id: string) { setBusy(true); setError(null); try { setPlan(await fetchExperiment(id)); } catch (e) { setError(String(e)); } finally { setBusy(false); } }
  return <section className="model-lab" aria-label="Model Lab">
    <div className="lab-heading"><div><p className="eyebrow">MODEL LAB · EXPERIMENT BUILDER</p><h2>Design a fair comparison</h2><p>Preview a repeatable schedule. Saving a plan starts no games and makes no provider calls.</p></div><span className="lab-pill">DRAFT PLANS</span></div>
    {plan?.id && <button onClick={invalidate} disabled={busy}>Create another draft</button>}
    <fieldset hidden={!!plan?.id} disabled={busy} onChange={invalidate}><legend>Experiment configuration</legend>
      <label>Experiment name<input value={name} maxLength={120} onChange={e => setName(e.target.value)} /></label>
      <label>Format<select aria-label="Experiment format" value={format} onChange={event => { setFormat(event.target.value as "comparison" | TournamentFormat); invalidate(); }}>
        <option value="comparison">Comparison · existing schedule</option><option value="round_robin">Round robin tournament</option><option value="gauntlet">Gauntlet tournament</option><option value="knockout">Knockout tournament</option>
      </select><small>Each selected effort variant is a separate tournament competitor.</small></label>
      {format === "gauntlet" && <label>Gauntlet anchor<select aria-label="Gauntlet anchor" value={selectedAnchor} onChange={event => { setAnchorKey(event.target.value); invalidate(); }}>{tournamentVariants.map(v => <option key={v.key} value={v.key}>{v.label}</option>)}</select><small>The anchor faces every other variant.</small></label>}
      {format === "knockout" && <p className="lab-format-note">Knockout uses the listed competitor order as seeding. Only decisive completed series advance; unresolved draws and non-chess results do not produce a winner.</p>}
      <div className="lab-grid">{entrants.map((e, i) => {
        const choice = choices.find(c => c.key === e.model);
        const levels = choice?.adapter === "stockfish" ? [] : effortLevels.filter(v => choice?.cap.effort_levels?.includes(v));
        return <fieldset key={e.key}><legend>Entrant {e.key}</legend><label>Model {e.key}<select value={e.model} onChange={event => setEntrants(old => old.map((v, j) => j === i ? { ...v, model: event.target.value, efforts: [] } : v))}>{choices.map(c => <option key={c.key} value={c.key}>{c.adapter} · {c.model}</option>)}</select></label>
          {levels.length > 0 ? <div className="lab-efforts"><p>Effort sweep · empty uses {levels[0]}</p>{levels.map(level => <label key={level}><input type="checkbox" checked={e.efforts.includes(level)} onChange={event => setEntrants(old => old.map((v, j) => j === i ? { ...v, efforts: event.target.checked ? [...v.efforts, level] : v.efforts.filter(l => l !== level) } : v))} />{level}</label>)}</div> : <small>Provider default effort; no simulated effort levels.</small>}
          {choice?.adapter === "stockfish" && <label>Target Elo {e.key}<input type="number" min={800} max={3200} value={e.elo} onChange={event => setEntrants(old => old.map((v, j) => j === i ? { ...v, elo: Number(event.target.value) } : v))} /></label>}
        </fieldset>;
      })}</div>
      <button disabled={entrants.length >= 8} onClick={() => { invalidate(); const key = "ABCDEFGH".split("").find(k => !entrants.some(e => e.key === k))!; setEntrants(old => [...old, { key, model: "scripted:deterministic-v1", efforts: [], elo: 1600 }]); }}>Add entrant</button>
      <button disabled={entrants.length <= 2} onClick={() => { invalidate(); setEntrants(old => old.slice(0, -1)); }}>Remove last entrant</button>
      <div className="lab-grid"><label>Opening suite<textarea rows={4} value={openings} onChange={e => setOpenings(e.target.value)} /><small>One line per opening: Name | legal UCI moves. Empty moves use the starting position.</small></label><div className="lab-grid">
        <label>Repetitions<input type="number" min={1} max={20} value={repetitions} onChange={e => setRepetitions(Number(e.target.value))} /></label>
        <label>Initial seconds<input type="number" min={1} max={86400} value={seconds} onChange={e => setSeconds(Number(e.target.value))} /></label>
        <label>Increment seconds<input type="number" min={0} max={60} value={increment} onChange={e => setIncrement(Number(e.target.value))} /></label>
        <label>Maximum plies<input type="number" min={2} max={1000} value={maxPlies} onChange={e => setMaxPlies(Number(e.target.value))} /></label>
        <label>Stop after failures<input type="number" min={1} max={100} value={maxFailures} onChange={e => setMaxFailures(Number(e.target.value))} /></label>
        <label>Wall-time limit minutes<input type="number" min={1} max={1440} value={minutes} onChange={e => setMinutes(Number(e.target.value))} /></label>
        <label className="lab-check"><input type="checkbox" checked={swap} onChange={e => setSwap(e.target.checked)} />Swap colors for every pairing</label>
      </div></div>
      <p>Clock information supplied · fixed effort per entrant variant · legal assist for models · engine assistance for Stockfish. Maximum 512 planned games.{format === "knockout" && ` Knockout needs a power-of-two field; ${tournamentVariants.length} competitors selected.`}</p>
      <button className="primary-button" onClick={() => void preview()}>Preview experiment</button>
    </fieldset>
    {error && <p role="alert">{error}</p>}
    {plan && <article className="lab-preview" aria-label="Experiment preview"><h3>{plan.configuration.name} · {plan.game_count} planned games</h3><p>{plan.id ? "Saved draft" : "Unsaved preview"} · {plan.exhibition ? "Mixed-division exhibition" : "Single assistance division"}</p><code>{plan.configuration_hash}</code>{plan.warnings.filter(w => !w.startsWith("Plan only: no games have started.")).map(w => <p key={w}>{w}</p>)}<p className="lab-save-disclosure">Saving this draft starts no games and makes no provider calls. A saved plan can be prepared as a batch when you choose.</p>{plan.tournament && <p className="lab-tournament-summary">{formatLabel(plan.tournament.format)} · {plan.tournament.series.length} series · provisional ratings use {plan.tournament.rating_spec} within compatible pools.</p>}<button disabled={busy || !!plan.id} onClick={() => void save()}>{plan.id ? "Plan saved" : "Save draft plan"}</button><div className="lab-table lab-schedule-table"><table><thead><tr><th>Game</th>{plan.tournament && <><th>Series</th><th>Round</th></>}<th>White</th><th>Black</th><th>Opening</th><th>Repeat</th></tr></thead><tbody>{plan.schedule.map(g => <tr key={g.number}><td>{g.number}</td>{plan.tournament && <><td>{g.series ?? "—"}</td><td>{g.round ?? "—"}</td></>}<td>{displaySlot(g.white)}</td><td>{displaySlot(g.black)}</td><td>{g.opening}</td><td>{g.repetition}</td></tr>)}</tbody></table></div>{plan.tournament && <div className="lab-table lab-series-table"><h4>{plan.tournament.format === "knockout" ? "Bracket series" : "Tournament pairings"}</h4><table><thead><tr><th>Series</th><th>Round</th><th>White / slot</th><th>Black / slot</th><th>Games</th></tr></thead><tbody>{plan.tournament.series.map(s => <tr key={s.id}><td>{s.id}</td><td>{s.round}</td><td>{displaySlot(s.white)}</td><td>{displaySlot(s.black)}</td><td>{s.numbers.join(", ")}</td></tr>)}</tbody></table></div>}</article>}
    {plan?.id && <ExperimentRunPanel key={plan.id} plan={plan} />}
    <details><summary>Saved experiments · {saved.length}</summary>{saved.map(s => <button key={s.id} disabled={busy} onClick={() => void load(s.id)}>{s.name} · {s.game_count} games</button>)}<div><button disabled={busy || offset === 0} onClick={() => setOffset(Math.max(0, offset - 50))}>Previous plans</button><button disabled={busy || saved.length < 50} onClick={() => setOffset(offset + 50)}>More plans</button></div></details>
  </section>;
}

function formatLabel(format: TournamentFormat) {
  return format === "round_robin" ? "Round robin" : format === "gauntlet" ? "Gauntlet" : "Knockout";
}
function displaySlot(value: string) {
  return value.startsWith("winner:") ? `Winner of ${value.slice("winner:".length)}` : value;
}
