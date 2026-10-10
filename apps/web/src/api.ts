import type { StockfishChoice } from "./StockfishStrength";
import type { IdentityDeclaration, LeaderboardReport } from "./types";
import type { Consultation } from "./types";
import type {
  ApiError,
  AssistanceDivision,
  ConnectionMode,
  EffortLevel,
  GameAnalysis,
  GameSnapshot,
  MatchEvent,
  PlayerAdapterCatalog,
  PlayerConfigurationInput,
  RunnerPairingResponse,
  RunnerSessionStatus,
} from "./types";

const apiBase = import.meta.env.VITE_API_BASE ?? "";

export class ApiRequestError extends Error {
  constructor(message: string, readonly status: number) { super(message); }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${apiBase}${path}`, {
    ...init,
    cache: "no-store",
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try {
      const payload = (await response.json()) as ApiError;
      const detail: unknown = payload.detail;
      message = typeof detail === "string" ? detail : Array.isArray(detail)
        ? detail.map(item => typeof item?.msg === "string" ? item.msg : "Invalid request field").join("; ")
        : message;
    } catch {
      // Keep the HTTP status when the response is not JSON.
    }
    throw new ApiRequestError(message, response.status);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export interface CreateGameOptions {
  startPaused?: boolean;
  singleGame?: boolean;
  stockfishElo: StockfishChoice;
  initialTimeMs?: number;
  incrementMs?: number;
  whitePlayer: PlayerConfigurationInput;
  blackPlayer: PlayerConfigurationInput;
}

export function createGame({
  startPaused = false,
  singleGame = false,
  stockfishElo,
  initialTimeMs = 300_000,
  incrementMs = 2_000,
  whitePlayer,
  blackPlayer,
}: CreateGameOptions): Promise<GameSnapshot> {
  return request<GameSnapshot>("/api/games", {
    method: "POST",
    body: JSON.stringify({
      start_paused: startPaused,
      single_game: singleGame,
      opponent: "stockfish",
      stockfish_elo: stockfishElo === "full" ? 1600 : stockfishElo,
      stockfish_full_strength: stockfishElo === "full",
      engine_move_time_ms: (stockfishElo === "full" || stockfishElo >= 2500) ? 700 : 400,
      initial_time_ms: initialTimeMs,
      increment_ms: incrementMs,
      white_player: whitePlayer,
      black_player: blackPlayer,
    }),
  });
}

export function fetchGame(gameId: string): Promise<GameSnapshot> {
  return request<GameSnapshot>(`/api/games/${gameId}`);
}

export function suggestToAgent(game: GameSnapshot, move: string | null): Promise<GameSnapshot> {
  return request<GameSnapshot>(`/api/games/${game.id}/human-suggestion`, {
    method: "POST", body: JSON.stringify({ move, expected_revision: game.revision }),
  });
}

/** The newest running or paused match, or null when nothing is live. */
export async function fetchLiveMatch(): Promise<GameSnapshot | null> {
  const response = await fetch(`${apiBase}/api/live-match`, { cache: "no-store" });
  if (response.status === 404) return null;
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  return (await response.json()) as GameSnapshot;
}

export function fetchGameEvents(gameId: string): Promise<MatchEvent[]> {
  return request<MatchEvent[]>(`/api/games/${gameId}/events`);
}

export function abortGame(gameId: string, generation?: number): Promise<GameSnapshot> {
  return request<GameSnapshot>(`/api/games/${gameId}/abort`, {
    method: "POST", body: JSON.stringify({ expected_generation: generation }),
  });
}

export function adjudicateGame(gameId: string, result: "1-0" | "0-1" | "1/2-1/2"): Promise<GameSnapshot> {
  return request<GameSnapshot>(`/api/games/${gameId}/adjudicate`, { method: "POST", body: JSON.stringify({ result }) });
}

export function fetchAnalysis(gameId: string): Promise<GameAnalysis> {
  return request<GameAnalysis>(`/api/games/${gameId}/analysis`);
}

export function fetchPlayerAdapters(): Promise<PlayerAdapterCatalog> {
  return request<PlayerAdapterCatalog>("/api/player-adapters");
}

export function createRunnerPairing(input: {
  comparison?: IdentityDeclaration;
  displayName: string;
  provider: string;
  model: string;
  connectionMode?: ConnectionMode;
  division?: AssistanceDivision;
  effort?: EffortLevel | null;
  moveTimeoutMs?: number;
  maxTurns?: number;
  matchTtlMs?: number;
}): Promise<RunnerPairingResponse> {
  return request<RunnerPairingResponse>("/api/runner-pairings", {
    method: "POST",
    body: JSON.stringify({
      ...(input.comparison ? { comparison: input.comparison } : {}),
      max_turns: input.maxTurns ?? 500,
      match_ttl_ms: input.matchTtlMs ?? 14_400_000,
      display_name: input.displayName,
      provider: input.provider,
      model: input.model,
      ...(input.connectionMode ? { connection_mode: input.connectionMode } : {}),
      ...(input.division ? { division: input.division } : {}),
      ...(input.effort !== undefined ? { effort: input.effort } : {}),
      ...(input.moveTimeoutMs ? { move_timeout_ms: input.moveTimeoutMs } : {}),
    }),
  });
}

export function fetchRunnerSessions(): Promise<RunnerSessionStatus[]> {
  return request<RunnerSessionStatus[]>("/api/runner-sessions");
}

export function submitMove(
  gameId: string,
  move: string,
  positionVersion: number,
  idempotencyKey = crypto.randomUUID(),
): Promise<GameSnapshot> {
  return request<GameSnapshot>(`/api/games/${gameId}/moves`, {
    method: "POST",
    headers: { "Idempotency-Key": idempotencyKey },
    body: JSON.stringify({ move, position_version: positionVersion }),
  });
}

export function resetGame(gameId: string): Promise<GameSnapshot> {
  return request<GameSnapshot>(`/api/games/${gameId}/reset`, { method: "POST" });
}

export function resignGame(gameId: string, color: "white" | "black", positionVersion: number): Promise<GameSnapshot> {
  return request<GameSnapshot>(`/api/games/${gameId}/resign`, {
    method: "POST", body: JSON.stringify({ color, position_version: positionVersion }),
  });
}

export function claimDraw(gameId: string, positionVersion: number, intendedMove: string | null): Promise<GameSnapshot> {
  return request<GameSnapshot>(`/api/games/${gameId}/claim-draw`, {
    method: "POST", body: JSON.stringify({ position_version: positionVersion, intended_move: intendedMove }),
  });
}

export function controlMatch(gameId: string, action: "pause" | "resume", expectedRevision: number): Promise<GameSnapshot> {
  return request<GameSnapshot>(`/api/games/${gameId}/${action}`, {
    method: "POST", body: JSON.stringify({ expected_revision: expectedRevision }),
  });
}

export function changeSeat(gameId: string, color: "white" | "black", player: PlayerConfigurationInput, expectedRevision: number): Promise<GameSnapshot> {
  return request<GameSnapshot>(`/api/games/${gameId}/seats/${color}`, {
    method: "POST", body: JSON.stringify({ player, expected_revision: expectedRevision }),
  });
}

export function retryAgentTurn(gameId: string): Promise<GameSnapshot> {
  return request<GameSnapshot>(`/api/games/${gameId}/retry-agent`, { method: "POST" });
}

export function websocketUrl(gameId: string): string {
  if (apiBase) {
    const url = new URL(apiBase, window.location.href);
    const protocol = url.protocol === "https:" ? "wss:" : "ws:";
    return `${protocol}//${url.host}/ws/games/${gameId}`;
  }
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${window.location.host}/ws/games/${gameId}`;
}

export function revokeRunnerSession(sessionId: string): Promise<void> {
  return request<void>(`/api/runner-sessions/${encodeURIComponent(sessionId)}/revoke`, { method: "POST" });
}

export function requestConsultation(gameId: string, advisor: PlayerConfigurationInput, expectedRevision: number): Promise<GameSnapshot> {
  return request<GameSnapshot>(`/api/games/${gameId}/consultations`, {
    method: "POST", body: JSON.stringify({ advisor, expected_revision: expectedRevision }),
  });
}
export function cancelConsultation(gameId: string, adviceId: string, expectedRevision: number): Promise<GameSnapshot> {
  return request<GameSnapshot>(`/api/games/${gameId}/consultations/${adviceId}/cancel`, {
    method: "POST", body: JSON.stringify({ expected_revision: expectedRevision }),
  });
}
export function playConsultation(gameId: string, advice: Consultation, revision: number): Promise<GameSnapshot> {
  return request<GameSnapshot>(`/api/games/${gameId}/moves`, {
    method: "POST", headers: { "Idempotency-Key": crypto.randomUUID() },
    body: JSON.stringify({ move: advice.move, position_version: advice.position_version, consultation_id: advice.id, consultation_revision: revision }),
  });
}

export function previewExperiment(configuration: import("./ModelLab").ExperimentConfiguration) {
  return request<import("./ModelLab").ExperimentPlan>("/api/experiments/preview", { method: "POST", body: JSON.stringify(configuration) });
}
export function saveExperiment(id: string, configuration: import("./ModelLab").ExperimentConfiguration) {
  return request<import("./ModelLab").ExperimentPlan>("/api/experiments", { method: "POST", body: JSON.stringify({ id, configuration }) });
}
export function listExperiments(offset = 0) {
  return request<import("./ModelLab").ExperimentSummary[]>(`/api/experiments?offset=${offset}`);
}
export function fetchExperiment(id: string) {
  return request<import("./ModelLab").ExperimentPlan>(`/api/experiments/${encodeURIComponent(id)}`);
}

export function createExperimentRun(experimentId: string, id: string, concurrency: number) {
  return request<import("./ExperimentRunPanel").ExperimentRun>(`/api/experiments/${encodeURIComponent(experimentId)}/runs`, { method: "POST", body: JSON.stringify({ id, concurrency }) });
}
export function fetchExperimentRun(id: string) {
  return request<import("./ExperimentRunPanel").ExperimentRun>(`/api/experiment-runs/${encodeURIComponent(id)}`);
}
export function fetchExperimentRunMetrics(id: string) {
  return request<import("./ComparisonMetrics").ComparisonMetricsData>(`/api/experiment-runs/${encodeURIComponent(id)}/metrics`);
}
export async function downloadExperimentRunBundle(id: string): Promise<Blob> {
  const response = await fetch(`${apiBase}/api/experiment-runs/${encodeURIComponent(id)}/bundle`, {
    headers: { Accept: "application/zip" },
  });
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try {
      const payload = (await response.json()) as ApiError;
      const detail: unknown = payload.detail;
      message = typeof detail === "string" ? detail : Array.isArray(detail)
        ? detail.map(item => typeof item?.msg === "string" ? item.msg : "Invalid request field").join("; ")
        : message;
    } catch {
      // Keep the HTTP status when the response is not JSON.
    }
    throw new Error(message);
  }
  return response.blob();
}
export function listExperimentRuns(experimentId: string) {
  return request<{ id: string; state: string }[]>(`/api/experiments/${encodeURIComponent(experimentId)}/runs`);
}
export function controlExperimentRun(id: string, target: "running" | "paused" | "cancelled", expected_revision: number, allow_provider_calls = false) {
  return request<import("./ExperimentRunPanel").ExperimentRun>(`/api/experiment-runs/${encodeURIComponent(id)}/control`, { method: "POST", body: JSON.stringify({ target, expected_revision, allow_provider_calls }) });
}

export function fetchLeaderboards(parameters: Record<string,string>): Promise<LeaderboardReport> {
  const query = new URLSearchParams(Object.entries(parameters).filter(([,value]) => value !== ""));
  return request<LeaderboardReport>(`/api/leaderboards?${query}`);
}
