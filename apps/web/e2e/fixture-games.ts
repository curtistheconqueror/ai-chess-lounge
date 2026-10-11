import type { APIRequestContext } from "@playwright/test";

// Use only against the disposable e2e server/database, never a user's preview.
export async function finishFixtureGames(request: APIRequestContext) {
  await resetTableSettings(request);
  await abortLiveMatches(request);
}

/** Ends every live fixture match but leaves the shared next-match settings alone (for tests that set them mid-test). */
export async function abortLiveMatches(request: APIRequestContext) {
  for (let i = 0; i < 200; i++) {
    const live = await request.get("/api/live-match");
    if (live.status() === 404) return;
    if (!live.ok()) throw new Error(`Fixture lookup failed: ${live.status()}`);
    const game = await live.json();
    const aborted = await request.post(`/api/games/${game.id}/abort`);
    if (!aborted.ok()) throw new Error(`Fixture cleanup failed: ${aborted.status()}`);
  }
  throw new Error("Too many live fixtures to clean safely");
}

/** Shared next-match settings persist on the server; each test starts from the documented defaults. */
export const defaultTableSettings = {
  white_seat: "human", black_seat: "stockfish",
  stockfish: { mode: "elo", elo: 1600, skill_level: null }, time_control: "5+2", start_paused: false,
};
export async function resetTableSettings(request: APIRequestContext, settings: object = defaultTableSettings) {
  const current = await request.get("/api/table-settings");
  if (current.status() === 404) return; // Older server without shared settings.
  const doc = await current.json();
  if (JSON.stringify(doc.settings) === JSON.stringify(settings)) return;
  const saved = await request.put("/api/table-settings", { data: { revision: doc.revision, settings } });
  if (!saved.ok()) throw new Error(`Table settings reset failed: ${saved.status()}`);
}
