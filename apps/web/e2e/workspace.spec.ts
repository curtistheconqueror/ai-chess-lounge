import { expect, test } from "@playwright/test";
import { finishFixtureGames } from "./fixture-games";

test.beforeEach(async ({ request }) => { await finishFixtureGames(request); });

test("board leads, live metrics stay visible and every workspace opens by keyboard", async ({ page }, info) => {
  const game = await (await page.request.post("/api/games", { data: { opponent: "human", start_paused: true } })).json();
  await page.goto(`/games/${game.id}`);
  await expect(page.getByLabel("Connection live")).toBeVisible();
  await expect(page.locator(".board .classic-piece")).toHaveCount(32);
  await expect(page.getByLabel("White seat", { exact: true })).not.toBeVisible();
  await expect(page.locator(".telemetry-grid")).toContainText("Evaluation");
  await expect(page.getByRole("tab", { name: "MOVES", exact: true })).toBeVisible();
  await page.getByRole("tab", { name: "MOVES", exact: true }).focus();
  await page.keyboard.press("End");
  await expect(page.getByRole("tab", { name: "FEN", exact: true })).toBeFocused();
  await expect(page.getByRole("tabpanel")).toHaveAttribute("aria-labelledby", "detail-tab-fen");
  await page.keyboard.press("Home");
  await expect(page.getByRole("tab", { name: "MOVES", exact: true })).toBeFocused();
  const layout = await page.evaluate(() => ({
    overflow: document.documentElement.scrollWidth > innerWidth,
    board: document.querySelector(".board")!.getBoundingClientRect().toJSON(),
    header: document.querySelector(".match-header")!.getBoundingClientRect().toJSON(),
  }));
  expect(layout.overflow).toBe(false);
  expect(layout.board.width).toBeGreaterThan(Math.min(380, page.viewportSize()!.width - 100, page.viewportSize()!.height - 430));
  await page.screenshot({ path: `test-results/workspace-${info.project.name}.png`, fullPage: true });
  for (const label of ["Strategy & live telemetry", "Seats & game setup", "Connections & API access", "Board preferences", "Match actions & export"]) {
    const summary = page.locator(".workspace-section > summary").filter({ hasText: label });
    await summary.focus();
    await page.keyboard.press("Enter");
    await expect(summary.locator("..")).toHaveAttribute("open", "");
  }
  await expect(page.getByLabel("White seat", { exact: true })).toBeVisible();
  await expect(page.getByLabel("Black seat", { exact: true })).toBeVisible();
  await expect(page.getByLabel("Runner turn limit")).toBeVisible();
  await expect(page.getByRole("button", { name: "Apply White seat", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Test sound", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Export PGN", exact: true })).toBeVisible();
  await page.getByRole("tab", { name: "FEN", exact: true }).click();
  await expect(page.getByRole("button", { name: "Download match JSON" })).toBeVisible();
  await expect(page.locator(".board-play-controls")).toContainText(game.id.slice(0, 8).toUpperCase());
  await expect(page.locator(".board-play-controls").getByRole("button", { name: /^End and start new/ })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);
});

test("board setup shortcut opens and focuses the retained seat controls", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Seats & game setup", exact: true }).click();
  await expect(page.locator("#seats-setup > summary")).toBeFocused();
  await page.getByLabel("Black seat", { exact: true }).selectOption("human");
  await page.getByRole("button", { name: "New match", exact: true }).click();
  await expect(page.locator(".board-play-controls")).toContainText("White to move");
});
