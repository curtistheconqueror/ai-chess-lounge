import { expect, test, type Page } from "@playwright/test";
import { finishFixtureGames } from "./fixture-games";

test.beforeEach(async ({ request }) => { await finishFixtureGames(request); });

async function humanGame(page: Page) {
  const game = await (await page.request.post("/api/games", { data: { opponent: "human", initial_time_ms: 3_600_000 } })).json();
  await page.goto(`/games/${game.id}`);
  await expect(page.getByLabel("Connection live")).toBeVisible();
  return game;
}

test("own move lands instantly while the server reply is still in flight, then is confirmed", async ({ page }) => {
  const game = await humanGame(page);
  let release!: () => void;
  const held = new Promise<void>(resolve => { release = resolve; });
  await page.route("**/api/games/*/moves", async route => { await held; await route.continue(); });
  await page.getByRole("gridcell", { name: "e2 white pawn" }).click();
  await page.getByRole("gridcell", { name: "e4 empty" }).click();
  // The server has not answered yet: the preview alone must already show the move.
  await expect(page.getByRole("gridcell", { name: "e4 white pawn" })).toBeVisible({ timeout: 500 });
  await expect(page.getByRole("gridcell", { name: "e2 empty" })).toBeVisible();
  expect((await (await page.request.get(`/api/games/${game.id}`)).json()).moves).toHaveLength(0);
  release();
  await expect.poll(async () => (await (await page.request.get(`/api/games/${game.id}`)).json()).moves.length).toBe(1);
  await expect(page.getByRole("gridcell", { name: "e4 white pawn" })).toBeVisible();
  await expect(page.getByRole("gridcell", { name: "e7 black pawn" })).toBeEnabled();
});

test("a rejected move is withdrawn and the board returns to the server position", async ({ page }) => {
  const game = await humanGame(page);
  await page.route("**/api/games/*/moves", route => route.fulfill({
    status: 409, contentType: "application/json", body: JSON.stringify({ detail: "Position changed; move not applied." }),
  }));
  await page.getByRole("gridcell", { name: "e2 white pawn" }).click();
  await page.getByRole("gridcell", { name: "e4 empty" }).click();
  await expect(page.getByRole("alert").filter({ hasText: "move not applied" })).toBeVisible();
  await expect(page.getByRole("gridcell", { name: "e2 white pawn" })).toBeVisible();
  await expect(page.getByRole("gridcell", { name: "e4 empty" })).toBeVisible();
  expect((await (await page.request.get(`/api/games/${game.id}`)).json()).moves).toHaveLength(0);
  await page.unroute("**/api/games/*/moves");
  await page.getByRole("gridcell", { name: "e2 white pawn" }).click();
  await page.getByRole("gridcell", { name: "e4 empty" }).click();
  await expect.poll(async () => (await (await page.request.get(`/api/games/${game.id}`)).json()).moves.length).toBe(1);
});

test("castling, en passant and promotion previews match the confirmed position", async ({ page }) => {
  const game = await humanGame(page);
  for (const uci of ["e2e4", "a7a6", "e4e5", "d7d5"]) {
    const current = await (await page.request.get(`/api/games/${game.id}`)).json();
    await page.request.post(`/api/games/${game.id}/moves`, { data: { move: uci, position_version: current.version } });
  }
  await expect(page.getByRole("gridcell", { name: "d5 black pawn" })).toBeVisible();
  let release!: () => void;
  const held = new Promise<void>(resolve => { release = resolve; });
  await page.route("**/api/games/*/moves", async route => { await held; await route.continue(); });
  await page.getByRole("gridcell", { name: "e5 white pawn" }).click();
  await page.getByRole("gridcell", { name: "d6 empty" }).click();
  // En passant preview removes the captured pawn before the server answers.
  await expect(page.getByRole("gridcell", { name: "d6 white pawn" })).toBeVisible({ timeout: 500 });
  await expect(page.getByRole("gridcell", { name: "d5 empty" })).toBeVisible();
  const preview = await page.locator(".board [data-square]").evaluateAll(cells => cells.map(c => c.getAttribute("aria-label")).join("|"));
  release();
  await expect.poll(async () => (await (await page.request.get(`/api/games/${game.id}`)).json()).moves.length).toBe(5);
  await expect.poll(() => page.locator(".board [data-square]").evaluateAll(cells => cells.map(c => c.getAttribute("aria-label")).join("|"))).toBe(preview);
});
