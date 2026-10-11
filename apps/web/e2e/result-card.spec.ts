import { expect, test, type Page, type WebSocketRoute } from "@playwright/test";
import { finishFixtureGames } from "./fixture-games";

test.beforeEach(async ({ request }) => { await finishFixtureGames(request); });

// Presentation fixture: a real human-vs-human game shown with Black as an automated seat,
// so the board sees a single human ("you") without any engine or provider calls.
async function setup(page: Page) {
  let socket: WebSocketRoute | undefined;
  await page.routeWebSocket("**/ws/games/**", ws => { socket = ws; });
  const game = await (await page.request.post("/api/games", { data: { opponent: "human", initial_time_ms: 3_600_000 } })).json();
  await page.goto(`/games/${game.id}`);
  await expect.poll(() => Boolean(socket)).toBe(true);
  const send = (snapshot: Record<string, any>) => {
    snapshot.black_player = { ...snapshot.black_player, adapter_id: "scripted", connection_mode: "local", display_name: "Stockfish 1600" };
    socket!.send(JSON.stringify({ type: "snapshot", payload: snapshot }));
  };
  send(game);
  await expect(page.getByLabel("Connection live")).toBeVisible();
  const play = async (uci: string) => {
    const current = await (await page.request.get(`/api/games/${game.id}`)).json();
    const next = await (await page.request.post(`/api/games/${game.id}/moves`, { data: { move: uci, position_version: current.version } })).json();
    send(next);
    await expect(page.locator(".sr-only[aria-live]")).toContainText(`Position ${next.moves.length}.`);
  };
  return { game, play };
}

test("winning by checkmate shows the flavored result card, crowns your king and offers a rematch", async ({ page }) => {
  const { game, play } = await setup(page);
  for (const uci of ["e2e4", "e7e5", "f1c4", "b8c6", "d1h5", "g8f6"]) await play(uci);
  await expect(page.getByRole("region", { name: "Game result" })).toHaveCount(0);
  await play("h5f7"); // Scholar's mate.
  const card = page.getByRole("region", { name: "Game result" });
  await expect(card).toContainText("You beat Stockfish 1600!");
  await expect(card).toContainText("by checkmate");
  await expect(card.locator(".result-flavor")).not.toBeEmpty();
  await expect(page.locator('[data-square="e1"] .king-mark.won')).toBeVisible();
  await expect(page.locator('[data-square="e8"] .king-mark.mated')).toBeVisible();
  await page.screenshot({ path: "C:/Users/curti/AppData/Local/Temp/claude/C--Users-curti-AppData-Roaming-Claude-scratch-workspaces-e15b1e54-5dd4-485a-8b06-16c0186adbe6-1e0bd925-c1dd-4c33-960b-85ac41d0aede-scratch-2026-10-10-75759a/a8badc4c-9927-4b6a-9c54-5990404cce3e/scratchpad/result-win-" + test.info().project.name + ".png" });
  await page.keyboard.press("Escape");
  await expect(card).toHaveCount(0);
  await expect(page.locator('[data-square="e1"] .king-mark.won')).toBeVisible(); // Badges stay on the final position.
  // Reopening the finished game later does not replay the celebration.
  await page.reload();
  await expect(page.locator(".board")).toBeVisible();
  await page.waitForTimeout(400);
  await expect(page.getByRole("region", { name: "Game result" })).toHaveCount(0);
  expect((await (await page.request.get(`/api/games/${game.id}`)).json()).termination_reason).toBe("checkmate");
});

test("losing shows the opponent's win with its own tone, and Rematch starts a new game", async ({ page }) => {
  const { play } = await setup(page);
  for (const uci of ["f2f3", "e7e5", "g2g4", "d8h4"]) await play(uci); // Fool's mate against you.
  const card = page.getByRole("region", { name: "Game result" });
  await expect(card).toContainText("Stockfish 1600 wins");
  await expect(card).toContainText("by checkmate");
  await expect(page.locator('[data-square="e1"] .king-mark.mated')).toBeVisible();
  await page.screenshot({ path: "C:/Users/curti/AppData/Local/Temp/claude/C--Users-curti-AppData-Roaming-Claude-scratch-workspaces-e15b1e54-5dd4-485a-8b06-16c0186adbe6-1e0bd925-c1dd-4c33-960b-85ac41d0aede-scratch-2026-10-10-75759a/a8badc4c-9927-4b6a-9c54-5990404cce3e/scratchpad/result-loss-" + test.info().project.name + ".png" });
  const created = page.waitForResponse(r => r.url().endsWith("/api/games") && r.request().method() === "POST" && r.ok());
  await card.getByRole("button", { name: "Rematch" }).click();
  await created;
  await expect(card).toHaveCount(0);
});
