import { useEffect, useRef } from "react";
import type { GameAnalysis, GameSnapshot } from "./types";

type Color = "white" | "black";
type Outcome = "win" | "loss" | "draw" | "neutral";

// A little personality: one line per finished game, picked from the game id so it never flickers.
const flavor: Record<Outcome, string[]> = {
  win: [
    "The engine is recalculating its life choices.",
    "Clean finish. Stockfish didn't see that one coming.",
    "That's how it's done.",
    "Somewhere, a silicon chip just sighed.",
  ],
  loss: [
    "Stockfish sends its regards. Run it back?",
    "Every master lost a thousand games first.",
    "Close enough to sting. Rematch?",
    "The engine won this round. Not the war.",
  ],
  draw: ["Honors even.", "Neither side blinked.", "A handshake across the board."],
  neutral: ["What a game.", "The board has spoken.", "A result for the history books."],
};

const howItEnded: Record<string, string> = {
  checkmate: "by checkmate",
  timeout: "on time",
  resignation: "by resignation",
  stalemate: "by stalemate",
  insufficient_material: "by insufficient material",
  fivefold_repetition: "by repetition",
  threefold_repetition: "by repetition",
  seventyfive_moves: "by the 75-move rule",
  fifty_move_rule: "by the fifty-move rule",
  adjudicated: "by adjudication",
};

function pick(lines: string[], seed: string) {
  let hash = 0;
  for (const char of seed) hash = (hash * 31 + char.charCodeAt(0)) >>> 0;
  return lines[hash % lines.length];
}

/** chess.com-style end-of-game card over the board. Presentation only: it never changes the game. */
export function ResultCard({ game, perspective, analysis, onClose, onRematch, onNewOpponent, onReview }: {
  game: GameSnapshot;
  perspective: Color | null;
  analysis: GameAnalysis | null;
  onClose: () => void;
  onRematch: () => void;
  onNewOpponent: () => void;
  onReview: () => void;
}) {
  const card = useRef<HTMLDivElement>(null);
  useEffect(() => {
    card.current?.focus({ preventScroll: true });
    const onKey = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const winner: Color | null = game.result === "1-0" ? "white" : game.result === "0-1" ? "black" : null;
  const outcome: Outcome = !winner ? "draw" : !perspective ? "neutral" : winner === perspective ? "win" : "loss";
  const name = (color: Color) => game[`${color}_player`].display_name;
  const opponent = perspective ? name(perspective === "white" ? "black" : "white") : "";
  const title = outcome === "win" ? `You beat ${opponent}!`
    : outcome === "loss" ? `${name(winner!)} wins`
    : outcome === "neutral" ? `${name(winner!)} wins`
    : "Draw";
  const how = howItEnded[game.termination_reason ?? ""] ?? "";

  // Move quality for the player's own moves, only when the analysis covers most of the game.
  const parity = perspective === "white" ? 1 : 0;
  const mine = (analysis?.points ?? []).filter(point => point.ply > 0 && point.ply % 2 === parity && point.classification);
  const ownMoves = Math.ceil((game.moves.length - (1 - parity)) / 2);
  const stats = perspective && ownMoves > 0 && mine.length >= ownMoves / 2 ? {
    best: mine.filter(point => point.classification === "best").length,
    excellent: mine.filter(point => point.classification === "excellent").length,
    misses: mine.filter(point => point.classification === "mistake" || point.classification === "blunder").length,
  } : null;

  return <div className="result-backdrop" onPointerDown={event => { if (event.target === event.currentTarget) onClose(); }}>
    <div ref={card} className={`result-card ${outcome}`} role="region" aria-label="Game result" aria-live="polite" tabIndex={-1}>
      <button className="result-close" aria-label="Close result" onClick={onClose}>×</button>
      <div className="result-head">
        {outcome === "win" && <span className="result-trophy" aria-hidden="true">♔</span>}
        <h2>{title}</h2>
        {how && <p className="result-how">{how}</p>}
        <p className="result-flavor">{pick(flavor[outcome], game.id)}</p>
      </div>
      {stats && <div className="result-stats" aria-label="Your move quality">
        <span className="best"><b>{stats.best}</b>Best</span>
        <span className="excellent"><b>{stats.excellent}</b>Excellent</span>
        <span className="misses"><b>{stats.misses}</b>Misses</span>
      </div>}
      <div className="result-actions">
        <button className="primary-button" onClick={onRematch}>Rematch</button>
        <button onClick={onNewOpponent}>New opponent</button>
      </div>
      <button className="result-review" onClick={onReview}>Review game</button>
    </div>
  </div>;
}
