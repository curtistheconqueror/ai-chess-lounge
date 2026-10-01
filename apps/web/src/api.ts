import type { ApiError, GameSnapshot } from "./types";

const apiBase = import.meta.env.VITE_API_BASE ?? "";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${apiBase}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try {
      const payload = (await response.json()) as ApiError;
      message = payload.detail || message;
    } catch {
      // Keep the HTTP status when the response is not JSON.
    }
    throw new Error(message);
  }
  return (await response.json()) as T;
}

export function createGame(stockfishElo: number): Promise<GameSnapshot> {
  return request<GameSnapshot>("/api/games", {
    method: "POST",
    body: JSON.stringify({
      opponent: "stockfish",
      stockfish_elo: stockfishElo,
      engine_move_time_ms: stockfishElo >= 2500 ? 700 : 400,
    }),
  });
}

export function fetchGame(gameId: string): Promise<GameSnapshot> {
  return request<GameSnapshot>(`/api/games/${gameId}`);
}

export function submitMove(
  gameId: string,
  move: string,
  positionVersion: number,
): Promise<GameSnapshot> {
  return request<GameSnapshot>(`/api/games/${gameId}/moves`, {
    method: "POST",
    body: JSON.stringify({ move, position_version: positionVersion }),
  });
}

export function resetGame(gameId: string): Promise<GameSnapshot> {
  return request<GameSnapshot>(`/api/games/${gameId}/reset`, { method: "POST" });
}

export function resignGame(gameId: string): Promise<GameSnapshot> {
  return request<GameSnapshot>(`/api/games/${gameId}/resign`, { method: "POST" });
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
