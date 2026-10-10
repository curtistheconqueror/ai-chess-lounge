import type { APIRequestContext } from "@playwright/test";

// Use only against the disposable e2e server/database, never a user's preview.
export async function finishFixtureGames(request: APIRequestContext) {
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
