import { useEffect, useState } from "react";
import type { ExperimentPlan } from "./ModelLab";
import { isTournamentConfig } from "./ModelLab";
import { controlExperimentRun, createExperimentRun, fetchExperimentRun, fetchExperimentRunMetrics, listExperimentRuns } from "./api";
import { TournamentStandings, type TournamentReport } from "./TournamentStandings";
import { ComparisonMetrics, type ComparisonMetricsData } from "./ComparisonMetrics";

export interface ExperimentRun {
  id: string; experiment_id: string; state: string; revision: number; concurrency: number; deadline: string | null;
  jobs: { id: string; number: number; state: string; result: string | null; has_game: boolean }[];
  report?: TournamentReport;
}
export function ExperimentRunPanel({ plan }: { plan: ExperimentPlan }) {
  const [run, setRun] = useState<ExperimentRun | null>(null);
  const [runs, setRuns] = useState<{ id: string; state: string }[]>([]);
  const [concurrency, setConcurrency] = useState(1);
  const [allowProvider, setAllowProvider] = useState(false);
  const [confirmStart, setConfirmStart] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [metrics, setMetrics] = useState<ComparisonMetricsData | null>(null);
  const [metricsBusy, setMetricsBusy] = useState(false);
  const [metricsError, setMetricsError] = useState<string | null>(null);
  const [runId, setRunId] = useState(() => crypto.randomUUID());
  const hasProvider = plan.configuration.entrants.some(e => e.player.connection_mode === "direct_api");
  const tournament = isTournamentConfig(plan.configuration);
  useEffect(() => { let active = true; void listExperimentRuns(plan.id!).then(items => { if (active) setRuns(items); }).catch(e => { if (active) setError(String(e)); }); return () => { active = false; }; }, [plan.id]);
  useEffect(() => { if (!run || !["running", "paused", "pausing", "ready"].includes(run.state)) return; let active = true; const timer = window.setInterval(() => { void fetchExperimentRun(run.id).then(value => { if (active) setRun(old => old?.id === value.id && old.revision <= value.revision ? value : old); }).catch(e => { if (active) setError(String(e)); }); }, 1000); return () => { active = false; window.clearInterval(timer); }; }, [run?.id, run?.state]);
  async function act(work: () => Promise<ExperimentRun>) { setBusy(true); setError(null); try { const next = await work(); setRun(next); setMetrics(null); setMetricsError(null); setRuns(await listExperimentRuns(plan.id!)); } catch (e) { setError(String(e)); if (run) { try { setRun(await fetchExperimentRun(run.id)); } catch { /* Keep original error. */ } } } finally { setBusy(false); setConfirmStart(false); } }
  async function loadMetrics() {
    if (!run) return;
    setMetricsBusy(true); setMetricsError(null);
    try { setMetrics(await fetchExperimentRunMetrics(run.id)); }
    catch (e) { setMetricsError(String(e)); }
    finally { setMetricsBusy(false); }
  }
  return <section className="lab-run" aria-label="Experiment execution">
    <h3>Run this {tournament ? "tournament" : "comparison"}</h3><p>{plan.game_count} games · {plan.configuration.initial_time_ms / 1000}s + {plan.configuration.increment_ms / 1000}s · {plan.configuration.stops.max_plies} plies per game · stop after {plan.configuration.stops.max_failures} failures · {plan.configuration.stops.max_wall_time_ms / 60000} minutes wall time.</p>
    <p>Limited games are recorded as incomplete, never invented draws. Pausing preserves the original batch deadline.</p>
    {!run && <><label>Concurrent games<select value={concurrency} onChange={e => { setConcurrency(Number(e.target.value)); setRunId(crypto.randomUUID()); }} disabled={busy}>{[1, 2, 3, 4].map(n => <option key={n} value={n}>{n}</option>)}</select></label><button disabled={busy} onClick={() => void act(() => createExperimentRun(plan.id!, runId, concurrency))}>Prepare batch</button></>}
    {runs.length > 0 && <details><summary>Previous runs · {runs.length}</summary>{runs.map(r => <button key={r.id} disabled={busy} onClick={() => void act(() => fetchExperimentRun(r.id))}>{r.id.slice(0, 8)} · {r.state}</button>)}</details>}
    {error && <p role="alert">{error}</p>}
    {run && <><p role="status">Batch {run.state} · {run.jobs.filter(j => ["completed", "failed", "cancelled", "blocked"].includes(j.state)).length}/{run.jobs.length} settled</p>
      {["ready", "paused"].includes(run.state) && <button disabled={busy} onClick={() => { setAllowProvider(false); setConfirmStart(true); }}>{run.state === "paused" ? "Resume batch" : "Start batch"}</button>}
      {confirmStart && <div className="lab-run-confirm" role="group" aria-label="Confirm batch execution"><p>This starts up to {run.concurrency} games at once and may call your configured models.</p>{hasProvider && <label className="lab-check"><input type="checkbox" checked={allowProvider} onChange={e => setAllowProvider(e.target.checked)} />Authorize provider API usage for this batch</label>}<button disabled={busy} onClick={() => setConfirmStart(false)}>Keep batch stopped</button><button disabled={busy || (hasProvider && !allowProvider)} onClick={() => void act(() => controlExperimentRun(run.id, "running", run.revision, allowProvider))}>Confirm start batch</button></div>}
      {run.state === "running" && <button disabled={busy} onClick={() => void act(() => controlExperimentRun(run.id, "paused", run.revision))}>Pause batch</button>}
      {["ready", "running", "paused", "pausing"].includes(run.state) && <button disabled={busy} onClick={() => void act(() => controlExperimentRun(run.id, "cancelled", run.revision))}>Cancel batch</button>}
      {["completed", "cancelled", "stopped"].includes(run.state) && <button onClick={() => { setRun(null); setRunId(crypto.randomUUID()); }}>Prepare another run</button>}
      {run.report && <TournamentStandings report={run.report} />}
      <div className="comparison-metrics-controls"><button disabled={metricsBusy} onClick={() => void loadMetrics()}>{metricsBusy ? "Loading metrics…" : metrics ? "Refresh comparison metrics" : "Load comparison metrics"}</button><small>Metrics are read from this run’s saved results and accepted-move metadata. Loading them makes no model or provider calls.</small></div>
      {metricsError && <p role="alert">{metricsError}</p>}
      {metrics && <ComparisonMetrics data={metrics} currentRevision={run.revision} />}
      <div className="lab-table"><table><thead><tr><th>Game</th><th>Status</th><th>Result</th></tr></thead><tbody>{run.jobs.map(j => <tr key={j.id}><td>{j.has_game ? <a href={`/games/${j.id}`} target="_blank" rel="noreferrer">Game {j.number}</a> : `Game ${j.number}`}</td><td>{j.state === "leased" ? "Preparing / playing" : j.state === "blocked" ? "Not played · prior series unresolved" : j.state}</td><td>{j.result ?? "—"}</td></tr>)}</tbody></table></div>
    </>}
  </section>;
}
