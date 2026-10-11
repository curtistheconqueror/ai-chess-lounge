import type { GameSnapshot, UsageMetrics } from "./types";

export function GameUsage({ game }: { game: GameSnapshot }) {
  const rows: { label: string; usage: UsageMetrics | null; attempts: number }[] = [
    ...game.moves.filter(m => m.player_metadata).map(m => ({
      label: `Ply ${m.ply}: ${m.san}`, usage: m.player_metadata!.usage, attempts: m.player_metadata!.attempt,
    })),
    ...game.consultations.filter(c => c.direction !== "human_to_ai").map(c => ({
      label: `Advice after ply ${c.after_ply} (${c.status})`, usage: c.usage, attempts: c.attempts,
    })),
  ];
  const format = (value: number | null | undefined, cost = false) => value == null ? "unknown" : cost ? `$${value.toFixed(5)}` : value.toLocaleString();
  const total = (key: keyof UsageMetrics, cost = false) => {
    const values = rows.map(r => r.usage?.[key]).filter((n): n is number => n != null);
    return values.length ? `${format(values.reduce((a, b) => a + b, 0), cost)} (${values.length}/${rows.length} records reported)` : "unknown";
  };
  return <section className="consultation-panel" aria-label="Game compute usage">
    <h3>Game compute usage</h3>
    <p>Input: {total("input_tokens")} · Output: {total("output_tokens")}</p>
    <p>Reasoning: {total("reasoning_tokens")} · Cost: {total("estimated_cost_usd", true)}</p>
    <small>Known subtotals only. Reasoning tokens may be included in output; they are never added twice. Missing usage is unknown, not free. Retries, cancelled or failed calls may incur unreported usage; this is not a billing ledger. Cost is the adapter's reported/estimated USD value, without a price assumption.</small>
    <details><summary>Per-move and adviser usage ({rows.length})</summary><ol>
      {rows.map((r, i) => <li key={i}><strong>{r.label}</strong><br />Input {format(r.usage?.input_tokens)} · Output {format(r.usage?.output_tokens)} · Reasoning {format(r.usage?.reasoning_tokens)} · Cost {format(r.usage?.estimated_cost_usd, true)} · Attempts {r.attempts}</li>)}
    </ol></details>
  </section>;
}
