export type OpponentKind = "stockfish" | "human";
export type MatchState =
  | "created"
  | "waiting"
  | "running"
  | "paused"
  | "completed"
  | "aborted"
  | "adjudicated";

export interface MoveRecord {
  generation: number;
  ply: number;
  uci: string;
  san: string;
  actor: string;
  fen: string;
  timestamp: string;
  elapsed_ms: number | null;
  white_remaining_ms: number;
  black_remaining_ms: number;
}

export interface EngineSummary {
  name: string;
  available: boolean;
  target_elo: number;
  move_time_ms: number;
  version: string | null;
  path: string | null;
}

export interface ClockSnapshot {
  initial_time_ms: number;
  increment_ms: number;
  white_remaining_ms: number;
  black_remaining_ms: number;
  turn_started_at: string | null;
  deadline_at: string | null;
  server_time: string;
  timed_out_by: "white" | "black" | null;
}

export interface GameSnapshot {
  id: string;
  lifecycle: MatchState;
  status:
    | "waiting"
    | "active"
    | "paused"
    | "checkmate"
    | "stalemate"
    | "draw"
    | "resigned"
    | "timeout"
    | "aborted"
    | "adjudicated";
  result: string;
  turn: "white" | "black";
  version: number;
  revision: number;
  generation: number;
  event_sequence: number;
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
  clock: ClockSnapshot;
  strategy_banner: string;
  created_at: string;
  updated_at: string;
}

export interface ApiError {
  detail: string;
}
