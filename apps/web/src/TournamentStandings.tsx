import type { TournamentFormat } from "./ModelLab";

export interface TournamentReport {
  format: TournamentFormat;
  status: "running" | "completed" | "unresolved";
  champion: string | null;
  standings: {
    key: string;
    division: string;
    played: number;
    wins: number;
    draws: number;
    losses: number;
    points: number;
    no_results: number;
    rating: number;
    rated_games: number;
    pool: string;
    rank: number;
  }[];
  series: {
    id: string;
    round: number;
    white: string | null;
    black: string | null;
    state: "pending" | "completed" | "unresolved";
    winner: string | null;
    score: [number, number];
  }[];
  rating_spec?: string;
  rating_notice?: string;
}

export function TournamentStandings({ report }: { report: TournamentReport }) {
  const label = report.format === "round_robin" ? "Round robin" : report.format === "gauntlet" ? "Gauntlet" : "Knockout";
  return <section className="tournament-report" aria-label="Tournament report">
    <h4>{label} standings · {report.status}</h4>
    {report.champion ? <p><strong>Champion:</strong> {report.champion}</p> : report.format === "knockout" && report.status === "unresolved" ? <p>No champion: at least one series ended without a decisive chess result.</p> : null}
    <p className="lab-rating-disclosure">{report.rating_notice ?? "Ratings are provisional and tournament-local."}</p>
    <p className="lab-rating-disclosure">Ranks and ratings use separate pools for assistance division, time control, and protocol version. Failed and limited games are shown as no-results and do not count as chess losses or rating games.</p>
    <div className="lab-table"><table><thead><tr><th>Rank</th><th>Competitor</th><th>Division</th><th>Played</th><th>W–D–L</th><th>Points</th><th>No-results</th><th>Provisional Elo</th><th>Rated games</th><th>Pool</th></tr></thead>
      <tbody>{report.standings.map(row => <tr key={`${row.pool}:${row.key}`}><td>{row.rank}</td><td>{row.key}</td><td>{row.division}</td><td>{row.played}</td><td>{row.wins}–{row.draws}–{row.losses}</td><td>{row.points.toFixed(1)}</td><td>{row.no_results}</td><td>{row.rated_games === 0 ? "Unrated" : row.rating.toFixed(1)}</td><td>{row.rated_games}</td><td>{row.pool}</td></tr>)}</tbody>
    </table></div>
    {report.series.length > 0 && <div className="lab-table"><h4>{report.format === "knockout" ? "Knockout series" : "Tournament pairings"}</h4><table><thead><tr><th>Round</th><th>Series</th><th>White</th><th>Black</th><th>Score</th><th>State</th><th>Winner</th></tr></thead>
      <tbody>{report.series.map(item => <tr key={item.id}><td>{item.round}</td><td>{item.id}</td><td>{item.white ?? "Waiting for prior result"}</td><td>{item.black ?? "Waiting for prior result"}</td><td>{item.score[0]}–{item.score[1]}</td><td>{item.state}</td><td>{item.winner ?? "—"}</td></tr>)}</tbody>
    </table></div>}
  </section>;
}
