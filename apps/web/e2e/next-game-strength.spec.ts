import { expect, test } from "@playwright/test";
import { finishFixtureGames } from "./fixture-games";
import { expandedWorkspace, playControls } from "./workspace-fixture";

test.beforeEach(async ({ request }) => { await finishFixtureGames(request); });

test("a new Elo is saved for the next game and applies when this game is ended and restarted", async ({ page }) => {
  const live = await (await page.request.post("/api/games", { data: { opponent: "stockfish", stockfish_elo: 3100, initial_time_ms: 600_000 } })).json();
  await page.goto(`/games/${live.id}`);
  await expect(page.getByLabel("Connection live")).toBeVisible();
  await expandedWorkspace(page);
  // Next-game strength is always editable, even while a game is on the board.
  const elo = page.getByLabel("Stockfish target Elo", { exact: true });
  await elo.fill("1397");
  const status = page.getByRole("status", { name: "Next game settings status" });
  await expect(status).toContainText("Stockfish 1397");
  await expect(status).toContainText("saved ✓");
  // The live game is untouched: no mid-game change.
  expect((await (await page.request.get(`/api/games/${live.id}`)).json()).black_player.settings.target_elo).toBe(3100);
  await page.getByRole("button", { name: "End this game and start new…", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText("Stockfish 1397");
  const created = page.waitForResponse(r => r.url().endsWith("/api/games") && r.request().method() === "POST" && r.ok());
  await dialog.getByRole("button", { name: /End and start new|Confirm/ }).first().click();
  const next = await (await created).json();
  expect(next.id).not.toBe(live.id);
  expect(next.black_player.settings.target_elo).toBe(1397);
  expect(next.black_player.settings.reply_pacing_ms).toBe(1000); // Natural pacing by default.
  await expect(page.locator(".player-card").filter({ hasText: "1397" }).first()).toBeVisible();
  await expect(playControls(page)).toContainText(/to move|Waiting for/);
  expect((await (await page.request.get(`/api/games/${live.id}`)).json()).lifecycle).toBe("aborted");
});

test("instant engine pacing is a per-device preference that new games respect", async ({ page }) => {
  await page.goto("/");
  await page.locator(".board").waitFor();
  await expandedWorkspace(page);
  await page.getByLabel("Engine reply pacing").selectOption("0");
  const created = page.waitForResponse(r => r.url().endsWith("/api/games") && r.request().method() === "POST" && r.ok());
  await playControls(page).getByRole("button", { name: "Play a new match", exact: true }).click();
  const game = await (await created).json();
  expect(game.black_player.settings.reply_pacing_ms).toBeUndefined();
  expect(await page.evaluate(() => localStorage.getItem("lounge.engine-pacing.v1"))).toBe("0");
});
