import { expandedWorkspace } from "./workspace-fixture";
import { expect, test } from "@playwright/test";
import { finishFixtureGames } from "./fixture-games";
import { pointerMove } from "./pointer-move";

test("paused AI suggestion preserves board and a second game is refused", async ({ page }) => {
  await finishFixtureGames(page.request);
  const agent = { adapter_id: "scripted", display_name: "Independent practice AI", provider: "Local", model: "deterministic-v1", connection_mode: "local", division: "legal_assist", effort: "balanced", settings: { moves: ["d2d4"] } };
  const created = await page.request.post("/api/games", { data: { opponent: "human", white_player: agent, start_paused: true, single_game: true } });
  expect(created.ok()).toBeTruthy();
  const game = await created.json();
  await page.goto(`/games/${game.id}`);
  await expandedWorkspace(page);
  const panel = page.getByRole("region", { name: "Suggest a move to your AI" });
  await expect(panel).toBeVisible();
  await expect(page.getByLabel("Suggestion mode")).toBeEnabled();
  await page.getByLabel("Suggestion mode").check();
  await page.getByRole("grid", { name: "Chess board" }).scrollIntoViewIfNeeded();
  // Real pointer events exercise the same legal-move path as touch/tap input.
  await pointerMove(page, "e2", "e4");
  await expect(panel).toContainText("Human suggested e4");
  const suggested = await (await page.request.get(`/api/games/${game.id}`)).json();
  expect(suggested.fen).toBe(game.fen);
  expect(suggested.moves).toEqual([]);
  await page.reload();
  await expandedWorkspace(page);
  await expect(panel).toContainText("Human suggested e4");
  await expect(page.getByRole("region", { name: "Game compute usage" })).toContainText("Cost: unknown");
  const rejected = page.waitForResponse(r => r.url().endsWith("/api/games") && r.request().method() === "POST");
  await page.getByRole("button", { name: "New match", exact: true }).click();
  expect((await rejected).status()).toBe(409);
  await expect(page).toHaveURL(new RegExp(game.id));
  await page.getByRole("button", { name: "Resume match", exact: true }).click();
  await expect.poll(async () => (await (await page.request.get(`/api/games/${game.id}`)).json()).moves.length).toBe(1);
  const played = await (await page.request.get(`/api/games/${game.id}`)).json();
  expect(played.moves[0].uci).toBe("d2d4");
  expect(played.consultations[0].status).toBe("played");
  await expect(panel).toHaveCount(0); // Human now has the move.
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  await page.screenshot({ path: `test-results/human-advisor-${test.info().project.name}.png`, fullPage: true });
  await page.request.post(`/api/games/${game.id}/abort`);
});
