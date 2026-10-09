import { expect, test } from "@playwright/test";

test("all supported Elo values and full strength persist without editing the current match", async ({ page }) => {
  // CI can lack a native engine; UCI propagation is tested separately with a recording engine.
  const runtime = await (await page.request.get("/api/engine/strength")).json();
  const caps = runtime.available && runtime.elo_min != null ? runtime : {
    available: true, version: "Strength UI fixture", elo_min: 1320, elo_max: 3190, full_strength_available: true,
  };
  if (caps !== runtime) await page.route("**/api/engine/strength", route => route.fulfill({ json: caps }));
  const original = await (await page.request.post("/api/games", { data: { opponent: "human", initial_time_ms: 3600000 } })).json();
  await page.goto(`/games/${original.id}`);
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
  await elo.fill("1673");
  await expect(elo).toHaveValue("1673");
  const changes = [caps.elo_min, 3100, caps.elo_max];
  for (const value of changes) {
    await elo.fill(String(value));
    await expect(elo).toHaveValue(String(value));
    await page.reload();
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
    await elo.fill(String(value));
    const response = page.waitForResponse(r => r.url().endsWith("/api/games") && r.request().method() === "POST");
    await page.getByRole("button", { name: "New match", exact: true }).click();
    const created = await response;
    expect(created.ok()).toBeTruthy();
    expect(created.request().postDataJSON().black_player.settings.target_elo).toBe(value);
    const game = await created.json();
    expect(game.black_player.settings.target_elo).toBe(value);
    expect(game.black_player.settings.full_strength).toBe(false);
    await expect(page.getByLabel("Current match Stockfish strength")).toContainText(`${value} target Elo`);
  }
  await page.getByLabel("Stockfish strength mode").selectOption("full");
  await page.reload();
  await expect(page.getByLabel("Stockfish strength mode")).toHaveValue("full");
  const response = page.waitForResponse(r => r.url().endsWith("/api/games") && r.request().method() === "POST");
  await page.getByRole("button", { name: "New match", exact: true }).click();
  const created = await response;
  expect(created.ok()).toBeTruthy();
  expect(created.request().postDataJSON().black_player.settings.full_strength).toBe(true);
  const game = await created.json();
  expect(game.engine.full_strength).toBe(true);
  await expect(page.locator(".player-card").filter({ hasText: "Stockfish full strength" })).toContainText("Full strength · 700 ms budget");
  await expect(page.getByLabel("Current match Stockfish strength")).toContainText("full strength");
  await page.getByLabel("Stockfish strength mode").selectOption("rated");
  await elo.fill("3100");
  await expect(page.getByLabel("Current match Stockfish strength")).toContainText("full strength");
  expect((await (await page.request.get(`/api/games/${game.id}`)).json()).black_player.settings.full_strength).toBe(true);
  await page.getByRole("button", { name: "Pause match", exact: true }).click();
  await page.getByRole("button", { name: "Apply Black seat", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "Change black player?" })).toBeVisible();
  await page.getByRole("button", { name: "Confirm seat change" }).click();
  await expect(page.getByLabel("Current match Stockfish strength")).toContainText("3100 target Elo");
  const changed = await (await page.request.get(`/api/games/${game.id}`)).json();
  expect(changed.black_player.settings.target_elo).toBe(3100);
  expect(changed.black_player.settings.full_strength).toBe(false);
  expect(changed.fen).toBe(game.fen);
  expect(changed.moves).toEqual(game.moves);
  expect(changed.lifecycle).toBe("paused");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  await page.screenshot({ path: `test-results/stockfish-strength-${test.info().project.name}.png`, fullPage: true });
});
