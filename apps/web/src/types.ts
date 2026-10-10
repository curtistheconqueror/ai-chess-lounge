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
  connection_modes?: ConnectionMode[];
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

export interface IdentityDeclaration {
  underlying_model?: string; underlying_provider?: string; model_family?: string;
  model_version?: string; access_route?: string; broker?: string; harness?: string;
  harness_version?: string; effort_raw?: string; listing_opt_in?: boolean; listing_alias?: string;
}
export interface EvidenceValue { value: string | string[] | null; evidence: string }
export interface ComparisonIdentity { [field: string]: EvidenceValue | string }
export interface ComparisonCounts {
  total_games: number; eligible_games: number; wins: number; losses: number; draws: number;
  forfeits: number; rate_denominator: number; excluded: Record<string,number>;
  win_rate: number | null; loss_rate: number | null; draw_rate: number | null; score_rate: number | null;
}
export interface ComparisonConditions {
  initial_time_ms: number; increment_ms: number; divisions: string[];
  engines: { target_elo: number | null; full_strength?: boolean; skill_level?: number; move_time_ms: number; version: EvidenceValue }[];
}
export interface LeaderboardReport {
  selected_games: number; legacy_games_without_snapshot: number; coverage: string;
  truncated: boolean; record_limit: number; notices: string[];
  rows: { key: string; identity: ComparisonIdentity; counts: ComparisonCounts;
    conditions: ComparisonConditions; colors: {white: ComparisonCounts; black: ComparisonCounts};
    variants: ComparisonIdentity[]; opt_in_aliases: string[] }[];
  head_to_head: { left: string; right: string; left_identity: ComparisonIdentity;
    right_identity: ComparisonIdentity; counts: ComparisonCounts; conditions: ComparisonConditions }[];
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
  comparison?: IdentityDeclaration | null;
}

export interface RunnerPairingResponse {
  pairing_id: string;
  pairing_code: string;
  expires_at: string;
  player: PlayerConfiguration;
}

export interface RunnerSessionStatus {
  session_id: string;
  player: PlayerConfiguration;
  player_id: string;
  display_name: string;
  provider: string;
  model: string;
  permissions: string[];
  transport: "webhook" | "websocket_or_http";
  connected: boolean;
  created_at: string;
  expires_at: string;
  last_heartbeat_at: string;
  expired: boolean;
  revoked: boolean;
  match_grant?: { match_id: string; color: string; turns_dispatched: number; max_turns: number; expires_at: string } | null;
}

export type PlayerConfigurationInput = Omit<PlayerConfiguration, "player_id">;

export interface PlayerMoveMetadata {
  provider_model?: string | null;
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
  full_strength?: boolean;
  skill_level?: number | null;
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

export interface Consultation {
  direction?: "ai_to_human" | "human_to_ai";
  id: string; color: "white" | "black"; advisor: PlayerConfiguration;
  position_version: number; revision: number; after_ply: number;
  status: "pending" | "ready" | "failed" | "cancelled" | "stale" | "played";
  timestamp: string; deadline_at: string; move: string | null; san: string | null;
  plan: string | null; threat: string | null; confidence: number | null;
  usage: UsageMetrics | null; latency_ms: number | null; attempts: number; error: string | null;
}

export interface SeatChange {
  color: "white" | "black";
  previous_player: PlayerConfiguration;
  player: PlayerConfiguration;
  after_ply: number;
  position_version: number;
  timestamp: string;
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
  can_claim_draw: boolean;
  draw_claim_moves: string[];
  draw_reason: string | null;
  termination_reason?: string | null;
  seat_history: SeatChange[];
  consultations: Consultation[];
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

export interface MatchEvent {
  sequence: number;
  type: string;
  position_version: number;
  payload: Record<string, unknown>;
  timestamp: string;
}
