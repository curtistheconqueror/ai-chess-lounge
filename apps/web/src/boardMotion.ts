import { parseFen } from "./chess";

/** Visual correspondence only. Legality and position always come from the server. */
export function pieceTranslations(before: string, after: string, uci: string | null) {
  if (!uci) return [];
  const old = new Map(parseFen(before).map(s => [s.name, s.piece]));
  const next = new Map(parseFen(after).map(s => [s.name, s.piece]));
  const from = uci.slice(0, 2), to = uci.slice(2, 4);
  const piece = old.get(from), landed = next.get(to);
  if (!piece || !landed || next.get(from) || piece.color !== landed.color
    || (piece.type !== landed.type && !(piece.type === "pawn" && uci.length === 5))) return [];
  const shifts = [{ from, to }];
  const changed = new Set([from, to]);
  if (piece.type === "king" && Math.abs(from.charCodeAt(0) - to.charCodeAt(0)) === 2) {
    const rookFrom = `${to[0] === "g" ? "h" : "a"}${from[1]}`;
    const rookTo = `${to[0] === "g" ? "f" : "d"}${from[1]}`;
    if (old.get(rookFrom)?.type !== "rook" || next.get(rookTo)?.type !== "rook") return [];
    shifts.push({ from: rookFrom, to: rookTo });
    changed.add(rookFrom); changed.add(rookTo);
  }
  if (piece.type === "pawn" && from[0] !== to[0] && !old.get(to)) {
    changed.add(`${to[0]}${from[1]}`); // En passant removes a third square.
  }
  // Missed/rapid snapshots and replay jumps snap to the latest board, never invent a path.
  for (const [square, prior] of old) {
    const current = next.get(square);
    if (!changed.has(square) && (prior?.type !== current?.type || prior?.color !== current?.color)) return [];
  }
  return shifts;
}

const pieceLetters: Record<string, string> = { king: "k", queen: "q", rook: "r", bishop: "b", knight: "n", pawn: "p" };
const promotionTypes: Record<string, string> = { q: "Q", r: "R", b: "B", n: "N" };

/**
 * Display-only preview of a submitted move so the board answers instantly, like chess.com.
 * Never authoritative: the server snapshot replaces it, and a rejection discards it.
 * Only the placement and side to move are meaningful; castling/en passant fields are cleared.
 */
export function previewMove(fen: string, uci: string): { fen: string; capture: boolean } {
  const placement = new Map(parseFen(fen).map(s => [s.name, s.piece ? (s.piece.color === "white"
    ? pieceLetters[s.piece.type].toUpperCase() : pieceLetters[s.piece.type]) : null]));
  const from = uci.slice(0, 2), to = uci.slice(2, 4);
  const piece = placement.get(from);
  if (!piece) return { fen, capture: false };
  let capture = Boolean(placement.get(to));
  placement.set(from, null);
  const white = piece === piece.toUpperCase();
  const promoted = uci[4] ? promotionTypes[uci[4]] : null;
  placement.set(to, promoted ? (white ? promoted : promoted.toLowerCase()) : piece);
  if (piece.toLowerCase() === "k" && Math.abs(from.charCodeAt(0) - to.charCodeAt(0)) === 2) {
    const rookFrom = `${to[0] === "g" ? "h" : "a"}${from[1]}`;
    placement.set(`${to[0] === "g" ? "f" : "d"}${from[1]}`, placement.get(rookFrom) ?? null);
    placement.set(rookFrom, null);
  }
  if (piece.toLowerCase() === "p" && from[0] !== to[0] && !capture) {
    placement.set(`${to[0]}${from[1]}`, null); // En passant.
    capture = true;
  }
  const rows: string[] = [];
  for (let rank = 8; rank >= 1; rank--) {
    let row = "", empty = 0;
    for (let file = 0; file < 8; file++) {
      const occupant = placement.get(`${String.fromCharCode(97 + file)}${rank}`);
      if (!occupant) { empty++; continue; }
      row += (empty || "") + occupant; empty = 0;
    }
    rows.push(row + (empty || ""));
  }
  const parts = fen.split(" ");
  const turn = parts[1] === "b" ? "w" : "b";
  return { fen: `${rows.join("/")} ${turn} - - ${parts[4] ?? 0} ${parts[5] ?? 1}`, capture };
}

/** One easing for every translation so an interrupted flight can be resumed exactly. */
export const motionEasing = [0.2, 0.7, 0.25, 1] as const;
export const motionEasingCss = `cubic-bezier(${motionEasing.join(",")})`;

/** Eased progress (0-1) of `motionEasing` at linear time fraction `t`. */
export function easedProgress(t: number) {
  if (t <= 0) return 0;
  if (t >= 1) return 1;
  const [x1, y1, x2, y2] = motionEasing;
  const curve = (a: number, b: number, s: number) => 3 * a * s * (1 - s) ** 2 + 3 * b * s ** 2 * (1 - s) + s ** 3;
  let low = 0, high = 1, s = t;
  for (let i = 0; i < 30; i++) {
    s = (low + high) / 2;
    if (curve(x1, x2, s) < t) low = s; else high = s;
  }
  return curve(y1, y2, s);
}

/** Where an interrupted translation still has to travel, so the next position can finish it. */
export function remainingFlight(offset: { x: number; y: number }, elapsedMs: number, delayMs: number, durationMs: number) {
  const t = Math.max(0, Math.min(1, (elapsedMs - delayMs) / durationMs));
  const left = 1 - easedProgress(t);
  return { x: offset.x * left, y: offset.y * left, ms: Math.max(1, Math.round(durationMs * (1 - t))) };
}

export const motionStorageKey = "lounge.board-motion.v1";
export function readMotionSettings(): { duration: number; buffer: number } {
  try {
    const value = JSON.parse(localStorage.getItem(motionStorageKey) ?? "null");
    if (value && [0, 150, 300, 500].includes(value.duration) && [0, 150, 300, 600].includes(value.buffer)) return value;
  } catch { /* Optional preference storage. */ }
  return { duration: 300, buffer: 150 };
}
