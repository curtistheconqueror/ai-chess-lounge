import { useState } from "react";

export interface MetricInterval {
  low: number;
  high: number;
  level: number;
  method: string;
}

export interface MetricUsage {
  total: number | null;
  observed_moves: number;
  missing_moves: number;
}

export interface MetricCompetitor {
  key: string;
  entrant: string;
  effort: string | null;
  provider: string;
  model: string;
  division: string;
  profile_hash: string;
  pool: string;
  games: {
    scheduled: number;
    started: number;
    settled: number;
    chess_completed: number;
    wins: number;
    draws: number;
    losses: number;
    limited: number;
    failed: number;
    cancelled: number;
    pending: number;
  };
  strength: {
    score_points: number;
    score_rate: number | null;
    opening_blocks: number;
    opening_mean: number | null;
    interval: MetricInterval | null;
    interval_unavailable_reason: string | null;
  };
  reliability: {
    agent_failure_events: number;
    illegal_move_events: number;
    timeouts: number;
  };
  efficiency: {
    accepted_moves: number;
    retries_observed: number;
    latency_ms: { count: number; mean: number | null; p50: number | null; p95: number | null };
    usage: {
      input_tokens: MetricUsage;
      output_tokens: MetricUsage;
      reasoning_tokens: MetricUsage;
      estimated_cost_usd: MetricUsage;
    };
  };
}

export interface EffortComparison {
  entrant: string;
  left: string;
  right: string;
  matched_blocks: number;
  score_delta: number | null;
  interval: MetricInterval | null;
  interval_unavailable_reason: string | null;
}

export interface ComparisonMetricsData {
  schema_version: string;
  run_id: string;
  experiment_id: string;
  configuration_hash: string;
  run_state: string;
  source_revision: number;
  generated_at: string;
  unresolved_slots: number;
  competitors: MetricCompetitor[];
  effort_comparisons?: EffortComparison[];
  notices: string[];
}

const usageFields = [
  ["input_tokens", "Input tokens"],
  ["output_tokens", "Output tokens"],
  ["reasoning_tokens", "Reasoning tokens"],
  ["estimated_cost_usd", "Adapter-reported cost estimate"],
] as const;

function count(value: number | null | undefined): string {
  return value == null ? "—" : value.toLocaleString();
}

function scorePercent(value: number | null): string {
  return value == null ? "—" : `${(value * 100).toFixed(1)}%`;
}

function intervalLabel(value: MetricInterval): string {
  return `${Math.round(value.level * 100)}% · ${scorePercent(value.low)}–${scorePercent(value.high)}`;
}

function usageLabel(field: string, data: MetricUsage, acceptedMoves: number): string {
  if (data.total == null || data.observed_moves === 0) {
    return `Unknown (${data.observed_moves}/${acceptedMoves} accepted moves reported)`;
  }
  const coverage = `${data.observed_moves}/${acceptedMoves} accepted moves`;
  return field === "estimated_cost_usd"
    ? `$${data.total.toFixed(4)} estimate · ${coverage}`
    : `${count(data.total)} reported · ${coverage}`;
}

export function ComparisonMetrics({
  data,
  currentRevision,
}: {
  data: ComparisonMetricsData;
  currentRevision: number;
}) {
  const [poolFilter, setPoolFilter] = useState("all");
  const pools = [...new Set(data.competitors.map(row => row.pool))].sort((left, right) => left.localeCompare(right));
  const activePool = poolFilter === "all" || pools.includes(poolFilter) ? poolFilter : "all";
  const competitors = activePool === "all" ? data.competitors : data.competitors.filter(row => row.pool === activePool);
  const visibleKeys = new Set(competitors.map(row => row.key));
  const byKey = new Map(data.competitors.map(row => [row.key, row]));
  const stale = data.source_revision < currentRevision;
  return <section className="comparison-metrics" aria-label="Comparison metrics">
    <div className="comparison-metrics-heading"><h3>Comparison metrics</h3><p>Read-only snapshot · {new Date(data.generated_at).toLocaleString()}</p></div>
    <div className="metrics-filter-row">
      <label>Filter comparison pool
        <select aria-label="Filter comparison pool" value={activePool} onChange={event => setPoolFilter(event.target.value)}>
          <option value="all">All pools (separate groups) · {data.competitors.length} competitors</option>
          {pools.map(pool => <option key={pool} value={pool}>{pool} ({data.competitors.filter(row => row.pool === pool).length})</option>)}
        </select>
      </label>
      <small role="status">Showing {competitors.length} of {data.competitors.length} competitors. Pools group division, clock, and protocol.</small>
    </div>
    {stale && <p role="status" className="metrics-stale">The run changed after this snapshot. Refresh metrics to include newer results.</p>}
    <p className="metrics-disclosure">Scores describe these scheduled games. This report makes no calibrated Elo or general-intelligence claim.</p>
    {data.unresolved_slots > 0 && <p>{data.unresolved_slots} bracket slots have no resolved opponent yet.</p>}

    <section aria-label="Chess strength metrics"><h4>Chess results and strength</h4>
      <div className="lab-table"><table><thead><tr><th>Competitor</th><th>Division / pool</th><th>Completed</th><th>W–D–L</th><th>Score points</th><th>Game score</th><th>Opening-block mean</th><th>95% block interval</th><th>Blocks</th></tr></thead>
        <tbody>{competitors.map(row => <tr key={row.key}>
          <td>{row.key}<small>{row.provider} · {row.model} · {row.effort ?? "default effort"}</small></td>
          <td>{row.division}<small>{row.pool}</small></td>
          <td>{count(row.games.chess_completed)}</td><td>{row.games.wins}–{row.games.draws}–{row.games.losses}</td>
          <td>{row.games.chess_completed ? row.strength.score_points.toFixed(1) : "—"}</td>
          <td>{scorePercent(row.strength.score_rate)}</td><td>{scorePercent(row.strength.opening_mean)}</td>
          <td>{row.strength.interval ? intervalLabel(row.strength.interval) : `Unavailable · ${row.strength.interval_unavailable_reason ?? "No complete estimate."}`}</td>
          <td>{count(row.strength.opening_blocks)}</td>
        </tr>)}</tbody>
      </table></div>
      <p className="metrics-method">The interval applies to the equal-weight mean of complete initial-position blocks, not the game-weighted score or an Elo rating. Independent blocks are an explicit, unverified assumption; the estimate is conditional on these opponents.</p>
    </section>

    <section aria-label="Reliability metrics"><h4>Reliability and game completion</h4>
      <div className="lab-table"><table><thead><tr><th>Competitor</th><th>Scheduled</th><th>Started</th><th>Settled</th><th>Chess results</th><th>Wins–draws–losses</th><th>Limited</th><th>Failed</th><th>Cancelled</th><th>Pending</th><th>Agent failures</th><th>Illegal moves</th><th>Timeouts</th></tr></thead>
        <tbody>{competitors.map(row => <tr key={row.key}><td>{row.key}</td><td>{row.games.scheduled}</td><td>{row.games.started}</td><td>{row.games.settled}</td><td>{row.games.chess_completed}</td><td>{row.games.wins}–{row.games.draws}–{row.games.losses}</td><td>{row.games.limited}</td><td>{row.games.failed}</td><td>{row.games.cancelled}</td><td>{row.games.pending}</td><td>{row.reliability.agent_failure_events}</td><td>{row.reliability.illegal_move_events}</td><td>{row.reliability.timeouts}</td></tr>)}</tbody>
      </table></div>
      <p className="metrics-method">Limited, failed, cancelled, and unresolved games are no-results, not chess losses. Failure events are attributed to the active seat; game-level failure counts are reflected for both competitors.</p>
    </section>

    <section aria-label="Efficiency metrics"><h4>Accepted-move efficiency and reported usage</h4>
      <div className="lab-table"><table><thead><tr><th>Competitor</th><th>Accepted moves</th><th>Observed retries</th><th>Latency p50</th><th>Latency p95</th>{usageFields.map(([field, label]) => <th key={field}>{label}</th>)}</tr></thead>
        <tbody>{competitors.map(row => <tr key={row.key}><td>{row.key}</td><td>{count(row.efficiency.accepted_moves)}</td><td>{row.efficiency.accepted_moves ? count(row.efficiency.retries_observed) : "—"}</td>
          <td>{row.efficiency.latency_ms.p50 == null ? "Unknown" : `${Math.round(row.efficiency.latency_ms.p50)} ms`}</td>
          <td>{row.efficiency.latency_ms.p95 == null ? "Unknown" : `${Math.round(row.efficiency.latency_ms.p95)} ms`}</td>
          {usageFields.map(([field]) => <td key={field}>{usageLabel(field, row.efficiency.usage[field], row.efficiency.accepted_moves)}</td>)}
        </tr>)}</tbody>
      </table></div>
      <p className="metrics-method">Latency and usage cover accepted moves only. Missing usage is unknown; partial cost sums are estimates, not provider bills. Reasoning tokens are reported separately and are not added to output tokens.</p>
    </section>

    <section aria-label="Effort response metrics"><h4>Effort response</h4>
      {(data.effort_comparisons ?? []).filter(item => visibleKeys.has(item.left) && visibleKeys.has(item.right)).length === 0 ? <p>No effort sweeps are configured for the selected pool.</p> : <div className="lab-table"><table><thead><tr><th>Entrant</th><th>Left variant</th><th>Right variant</th><th>Right − left score</th><th>95% paired interval</th><th>Matched opening blocks</th></tr></thead>
        <tbody>{data.effort_comparisons!.filter(item => visibleKeys.has(item.left) && visibleKeys.has(item.right)).map((item, index) => <tr key={`${item.entrant}:${item.left}:${item.right}:${index}`}><td>{item.entrant}</td><td>{byKey.get(item.left)?.effort ?? item.left}</td><td>{byKey.get(item.right)?.effort ?? item.right}</td>
          <td>{item.score_delta == null ? "—" : `${item.score_delta >= 0 ? "+" : ""}${(item.score_delta * 100).toFixed(1)} percentage points`}</td>
          <td>{item.interval ? intervalLabel(item.interval) : `Unavailable · ${item.interval_unavailable_reason ?? "No complete matched estimate."}`}</td><td>{item.matched_blocks}</td>
        </tr>)}</tbody>
      </table></div>}
      {data.effort_comparisons?.some(item => visibleKeys.has(item.left) && visibleKeys.has(item.right) && item.interval) && <p className="metrics-method">Effort comparisons are descriptive matched outcomes, not proof that effort caused a strength change. The interval is conditional on matched independent opening blocks.</p>}
    </section>

    <section aria-label="Metrics notices"><h4>Scope and assumptions</h4><ul>{data.notices.map((notice, index) => <li key={`${index}:${notice}`}>{notice}</li>)}</ul></section>
  </section>;
}
