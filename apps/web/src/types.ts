export type OpponentKind = "stockfish" | "human";
export type AssistanceDivision =
  | "pure_reasoning"
  | "legal_assist"
  | "tactical_metadata"
  | "engine_assisted"
  | "open_agentic"
  | "human_ai_team";
export type EffortLevel = "fast" | "balanced" | "deep" | "maximum";
export type ConnectionMode =
  | "human"
  | "local"
  | "direct_api"
  | "remote_runner"
  | "subscription_bridge";

export interface AdapterModelCapabilities {
  model: string;
  available?: boolean;
  selectable?: boolean;
  availability?: "configured_unverified" | "credentials_missing" | string;
  connection_mode?: ConnectionMode;
  effort_levels?: string[];
  provider_effort_map?: Partial<Record<EffortLevel, string>>;
  thinking_mode?: string;
  structured_output?: boolean;
  credentials_required?: boolean;
}

export interface PlayerAdapterCatalogEntry {
  adapter_id: string;
  models: string[];
  capabilities: Record<string, AdapterModelCapabilities>;
}

export interface PlayerAdapterCatalog {
  protocol_version: string;
  adapters: PlayerAdapterCatalogEntry[];
}

export interface UsageMetrics {
  input_tokens: number | null;
  output_tokens: number | null;
  reasoning_tokens: number | null;
  estimated_cost_usd: number | null;
}

export interface PlayerConfiguration {
  protocol_version: string;
  player_id: string;
  adapter_id: string;
  display_name: string;
  provider: string;
  model: string;
  connection_mode: ConnectionMode;
  effort: EffortLevel | null;
  division: AssistanceDivision;
  settings: Record<string, unknown>;
}

export type PlayerConfigurationInput = Omit<PlayerConfiguration, "player_id">;

export interface PlayerMoveMetadata {
  protocol_version: string;
  player_id: string;
  adapter_id: string;
  provider: string;
  model: string;
  effort: EffortLevel | null;
  division: AssistanceDivision;
  latency_ms: number;
  plan: string;
  threat: string;
  confidence: number | null;
  usage: UsageMetrics;
  attempt: number;
}
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
  player_metadata: PlayerMoveMetadata | null;
}

export interface EngineSummary {
  name: string;
  available: boolean;
  target_elo: number;
  move_time_ms: number;
  version: string | null;
}

export interface AnalysisPoint {
  ply: number;
  fen: string;
  score_cp: number;
  mate: number | null;
  best_move: string | null;
  pv_san: string[];
  depth: number | null;
  classification: "best" | "excellent" | "good" | "inaccuracy" | "mistake" | "blunder" | null;
}

export interface GameAnalysis {
  game_id: string;
  generation: number;
  position_version: number;
  engine_name: string;
  engine_version: string | null;
  perspective: "white";
  points: AnalysisPoint[];
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
  white_player: PlayerConfiguration;
  black_player: PlayerConfiguration;
  clock: ClockSnapshot;
  strategy_banner: string;
  created_at: string;
  updated_at: string;
}

export interface ApiError {
  detail: string;
}
