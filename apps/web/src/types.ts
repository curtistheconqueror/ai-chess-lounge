export type OpponentKind = "stockfish" | "human";

export interface MoveRecord {
  ply: number;
  uci: string;
  san: string;
  actor: string;
  fen: string;
  timestamp: string;
  elapsed_ms: number | null;
}

export interface EngineSummary {
  name: string;
  available: boolean;
  target_elo: number;
  move_time_ms: number;
  version: string | null;
  path: string | null;
}

export interface GameSnapshot {
  id: string;
  status: "active" | "checkmate" | "stalemate" | "draw" | "resigned";
  result: string;
  turn: "white" | "black";
  version: number;
  fen: string;
  initial_fen: string;
  pgn: string;
  legal_moves: string[];
  moves: MoveRecord[];
  last_move: string | null;
  in_check: boolean;
  can_move: boolean;
  opponent: OpponentKind;
  engine: EngineSummary | null;
  strategy_banner: string;
}

export interface ApiError {
  detail: string;
}
