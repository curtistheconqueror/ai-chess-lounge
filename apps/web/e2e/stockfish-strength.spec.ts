import { expandedWorkspace, playControls } from "./workspace-fixture";
import { expect, test, type Locator, type Page } from "@playwright/test";
import { abortLiveMatches, finishFixtureGames, resetTableSettings } from "./fixture-games";

test.beforeEach(async ({ request }) => { await finishFixtureGames(request); });

// Next-match settings are shared through the server (debounced PUT); wait for that save before reloading.
const tableSaved = (page: Page) => page.waitForResponse(r => r.url().endsWith("/api/table-settings") && r.request().method() === "PUT");
async function setElo(page: Page, elo: Locator, value: number | string) {
  const saved = tableSaved(page);
  await elo.fill(String(value));
  await expect(elo).toHaveValue(String(value));
  await saved;
}

test("all supported Elo values and full strength persist without editing the current match", async ({ page }) => {
  // CI can lack a native engine; UCI propagation is tested separately with a recording engine.
  const runtime = await (await page.request.get("/api/engine/strength")).json();
  const caps = runtime.available && runtime.elo_min != null ? runtime : {
    available: true, version: "Strength UI fixture", elo_min: 1320, elo_max: 3190, full_strength_available: true,
  };
  if (caps !== runtime) await page.route("**/api/engine/strength", route => route.fulfill({ json: caps }));
  const original = await (await page.request.post("/api/games", { data: { opponent: "human", initial_time_ms: 3600000 } })).json();
  await page.goto(`/games/${original.id}`);
  await expandedWorkspace(page);
  const elo = page.getByRole("spinbutton", { name: "Stockfish target Elo" });
  await expect(page.getByRole("slider", { name: "Stockfish Elo slider" })).toHaveAttribute("max", String(caps.elo_max));
  await expect(elo).toHaveAttribute("min", String(caps.elo_min));
  await page.getByLabel("Stockfish slider increments").selectOption("25");
  const slider = page.getByRole("slider", { name: "Stockfish Elo slider" });
  await slider.focus();
  await page.keyboard.press("Home");
  await expect(elo).toHaveValue(String(caps.elo_min));
  await page.keyboard.press("ArrowRight");
  await expect(elo).toHaveValue(String(caps.elo_min + 25));
  await page.keyboard.press("End");
  await expect(elo).toHaveValue(String(caps.elo_max));
  await setElo(page, elo, 1673);
  const changes = [caps.elo_min, 3100, caps.elo_max];
  for (const value of changes) {
    await setElo(page, elo, value);
    await page.reload();
    await expandedWorkspace(page);
    await expect(elo).toHaveValue(String(value));
    const unchanged = await (await page.request.get(`/api/games/${original.id}`)).json();
    expect(unchanged.fen).toBe(original.fen);
    expect(unchanged.moves).toEqual(original.moves);
    expect(unchanged.black_player.adapter_id).toBe("human");
  }
  await expect(page.getByLabel("Current match Stockfish strength")).toContainText("no Stockfish seat");
  for (const value of [caps.elo_min - 1, caps.elo_max + 1, 1600.5]) {
    await elo.fill(String(value));
    await expect(page.getByRole("button", { name: "New match", exact: true })).toBeDisabled();
    await expect(page.getByRole("alert")).toContainText("whole-number Elo");
  }
  for (const value of changes) {
    // One strength control at a time: the next-match field returns once the live match has ended.
    await abortLiveMatches(page.request);
    await expect(elo).toBeVisible();
    await expect(page.getByLabel("Current black strength", { exact: true })).toHaveCount(0);
    await setElo(page, elo, value);
    const response = page.waitForResponse(r => r.url().endsWith("/api/games") && r.request().method() === "POST");
    await page.getByRole("button", { name: "New match", exact: true }).click();
    const created = await response;
    expect(created.ok()).toBeTruthy();
    expect(created.request().postDataJSON().black_player.settings.target_elo).toBe(value);
    const game = await created.json();
    expect(game.black_player.settings.target_elo).toBe(value);
    expect(game.black_player.settings.full_strength).toBe(false);
    // While the match is live only the current-match control exists; the next-match field is gone.
    await expect(page.getByLabel("Current black strength", { exact: true })).toContainText(`${value} target Elo`);
    await expect(elo).toHaveCount(0);
    await expect(page.getByLabel("Stockfish strength mode", { exact: true })).toHaveCount(0);
  }
  await abortLiveMatches(page.request);
  const mode = page.getByLabel("Stockfish strength mode", { exact: true });
  const fullSaved = tableSaved(page);
  await mode.selectOption("full");
  await fullSaved;
  await page.reload();
  await expandedWorkspace(page);
  await expect(mode).toHaveValue("full");
  const response = page.waitForResponse(r => r.url().endsWith("/api/games") && r.request().method() === "POST");
  await page.getByRole("button", { name: "New match", exact: true }).click();
  const created = await response;
  expect(created.ok()).toBeTruthy();
  expect(created.request().postDataJSON().black_player.settings.full_strength).toBe(true);
  const game = await created.json();
  expect(game.engine.full_strength).toBe(true);
  await expect(page.locator(".player-card").filter({ hasText: "Stockfish full strength" })).toContainText("Full strength · 700 ms budget");
  await expect(page.getByLabel("Current black strength", { exact: true })).toContainText("Full strength");
  // The next-match field is hidden during a live Stockfish match. Another device changing the shared
  // next-match strength reaches this one on focus, and never edits the match already on the board.
  await resetTableSettings(page.request, {
    white_seat: "human", black_seat: "stockfish", stockfish: { mode: "elo", elo: 3100, skill_level: null },
    time_control: "5+2", start_paused: false,
  });
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await expect(page.getByLabel("Current black strength", { exact: true })).toContainText("Full strength");
  await expect(elo).toHaveCount(0);
  expect((await (await page.request.get(`/api/games/${game.id}`)).json()).black_player.settings.full_strength).toBe(true);
  await playControls(page).getByRole("button", { name: "Pause play", exact: true }).click();
  await expect(playControls(page)).toContainText("Match paused");
  // A seat takeover uses the shared next-match strength (3100) and applies only after confirmation.
  await page.getByRole("button", { name: "Apply Black seat", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "Change black player?" })).toBeVisible();
  await expect(page.getByRole("dialog")).toContainText("3100");
  await page.getByRole("button", { name: "Confirm seat change" }).click();
  await expect(page.getByLabel("Current black strength", { exact: true })).toContainText("3100 target Elo");
  const changed = await (await page.request.get(`/api/games/${game.id}`)).json();
  expect(changed.black_player.settings.target_elo).toBe(3100);
  expect(changed.black_player.settings.full_strength).toBe(false);
  expect(changed.fen).toBe(game.fen);
  expect(changed.moves).toEqual(game.moves);
  expect(changed.lifecycle).toBe("paused");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  await page.screenshot({ path: `test-results/stockfish-strength-${test.info().project.name}.png`, fullPage: true });
});
