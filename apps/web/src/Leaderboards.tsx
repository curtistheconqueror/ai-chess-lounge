import { useEffect, useState } from "react";
import { fetchLeaderboards } from "./api";
import type { LeaderboardReport, ComparisonIdentity, ComparisonCounts } from "./types";

const evidenceLabels: Record<string,string> = { recorded_configuration: "configured", recorded_adapter_mapping: "adapter mapping", recorded_connection_mode: "connection mode", declared: "declared", verified_runtime: "UCI runtime", observed_provider_response: "provider response" };
function field(identity: ComparisonIdentity, name: string) {
  const item = identity[name];
  if (!item || typeof item !== "object" || !("value" in item) || item.value === null) return "Unknown";
  return `${Array.isArray(item.value) ? item.value.join(", ") : item.value} · ${evidenceLabels[item.evidence] ?? item.evidence}`;
}
function name(identity: ComparisonIdentity) { return field(identity, "model" in identity ? "model" : "family"); }
function rate(value: number | null) { return value === null ? "Unavailable" : `${(value * 100).toFixed(1)}%`; }
function Result({ count }: { count: ComparisonCounts }) {
  return <><strong>{count.wins} / {count.losses} / {count.draws}</strong><small>Eligible n={count.eligible_games}; total={count.total_games}</small><small>Win {rate(count.win_rate)} · draw {rate(count.draw_rate)} · loss {rate(count.loss_rate)}</small><small>Score {rate(count.score_rate)} · denominator={count.rate_denominator}; forfeit games={count.forfeits}</small>{Object.entries(count.excluded).map(([reason,n]) => <small key={reason}>Excluded {reason}: {n}</small>)}</>;
}

export function Leaderboards() {
  const [report, setReport] = useState<LeaderboardReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [grouping, setGrouping] = useState("exact");
  const [filters, setFilters] = useState<Record<string,string>>({});
  const [color, setColor] = useState("");
  const [forfeits, setForfeits] = useState(true);
  const [refresh, setRefresh] = useState(0);
  const [busy, setBusy] = useState(false);
  useEffect(() => { let active = true; setBusy(true); setError(null); setReport(null); void fetchLeaderboards({ grouping, ...filters, color, include_forfeits: String(forfeits) }).then(data => { if(active) setReport(data); }).catch(e => { if(active) { setReport(null); setError(String(e)); } }).finally(() => { if(active) setBusy(false); }); return () => { active = false; }; }, [grouping, filters, color, forfeits, refresh]);
  return <section className="model-lab comparison-metrics" aria-label="AI leaderboards">
    <div className="lab-heading"><div><p className="eyebrow">MODEL LAB · LOCAL COMPARISONS</p><h2>AI leaderboards</h2><p>Compare recorded games, not invented model catalogs. Free access · bring your own inference.</p></div><span className="lab-pill">LOCAL DATA</span></div>
    <div className="metrics-filter-row"><label>Group by<select aria-label="Leaderboard grouping" value={grouping} onChange={e => setGrouping(e.target.value)}>{["exact","model","version","effort_raw","access","family"].map(v => <option key={v} value={v}>{v === "exact" ? "Exact identity and conditions" : v}</option>)}</select></label><label>Row color<select aria-label="Leaderboard color" value={color} onChange={e => setColor(e.target.value)}><option value="">Both colors</option><option value="white">White</option><option value="black">Black</option></select></label><label className="lab-check"><input type="checkbox" checked={forfeits} onChange={e => setForfeits(e.target.checked)} />Include resignation / timeout forfeits</label><button disabled={busy} onClick={() => setRefresh(v => v + 1)}>Refresh leaderboards</button></div>
    <details><summary>Filter games involving a matching seat</summary><div className="lab-grid">{["model","version","effort","access","provider","broker","harness"].map(f => <label key={f}>{f}<input aria-label={`Leaderboard ${f} filter`} maxLength={f === "effort" ? 512 : 120} value={filters[f] ?? ""} onChange={e => setFilters({ ...filters, [f]: e.target.value })} /><small>Exact value; use unknown for unavailable metadata.</small></label>)}</div></details>
    {busy && <p role="status">Loading comparisons…</p>}{error && <p role="alert">{error}</p>}
    {report && <><p>{report.selected_games} selected games · {report.legacy_games_without_snapshot} legacy games without original metadata. {report.coverage}</p>{report.truncated && <p role="alert">Bounded report: first {report.record_limit} snapshots by match ID/generation; additional records omitted. This is not a complete leaderboard.</p>}
      {report.notices.map(n => <p className="leaderboard-notice" key={n}>{n}</p>)}
      {report.rows.length === 0 ? <p>No matching snapshots yet. Play a new local game or run a comparison, then refresh.</p> : <div className="leaderboard-table-scroll" tabIndex={0} role="region" aria-label="Leaderboard results table"><table><thead><tr><th>Model identity</th><th>Results W / L / D</th><th>Conditions and colors</th></tr></thead><tbody>{report.rows.map(row => <tr key={row.key}><td><strong>{name(row.identity)}</strong><small>Version: {field(row.identity,"version")}</small><small>Underlying: {field(row.identity,"underlying_model")}</small><small>Provider: {field(row.identity,"provider")}; family: {field(row.identity,"family")}</small><small>Effort: {field(row.identity,"effort_raw")}; normalized: {field(row.identity,"effort_normalized")}</small><small>Access: {field(row.identity,"access")} · {String(row.identity.connection_mode)}</small><small>Configured connector: {String(row.identity.connector)}</small><small>Broker: {field(row.identity,"broker")}; harness: {field(row.identity,"harness")}</small><small>Provider-reported models: {field(row.identity,"observed_models")}</small>{row.opt_in_aliases.map(a => <small key={a}>Opt-in alias: {a}</small>)}<details><summary>{row.variants.length} recorded identity variants</summary><pre>{JSON.stringify(row.variants,null,2)}</pre></details></td><td><strong className="leaderboard-mobile-label">Results W / L / D</strong><Result count={row.counts} /></td><td><strong className="leaderboard-mobile-label">Conditions and colors</strong><small>Clock {row.conditions.initial_time_ms / 1000}s + {row.conditions.increment_ms / 1000}s</small><small>Division {row.conditions.divisions.join(" / ")}</small><small>Engine targets {row.conditions.engines.length ? row.conditions.engines.map(e => `${e.target_elo} target · ${e.move_time_ms}ms · ${e.version.value ?? "version unknown"}`).join(" / ") : "None"}</small><small>White n={row.colors.white.eligible_games}; black n={row.colors.black.eligible_games}</small><details><summary>Opening and full conditions</summary><pre>{JSON.stringify(row.conditions,null,2)}</pre></details></td></tr>)}</tbody></table></div>}
      <h3>Head-to-head matchups</h3><p>Counts are games once per matchup, from the left model's perspective. Row color filtering does not change these counts.</p><div className="leaderboard-matchups">{report.head_to_head.map(pair => <article key={pair.left + pair.right}><strong>{name(pair.left_identity)} vs {name(pair.right_identity)}</strong><small>Left version {field(pair.left_identity,"version")} · right version {field(pair.right_identity,"version")}</small><Result count={pair.counts} /><details><summary>Matchup identities and conditions</summary><pre>{JSON.stringify({left:pair.left_identity,right:pair.right_identity,conditions:pair.conditions},null,2)}</pre></details></article>)}</div>
    </>}
  </section>;
}
