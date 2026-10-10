import { expandedWorkspace } from "./workspace-fixture";
import { expect, test, type Page } from "@playwright/test";
import { finishFixtureGames } from "./fixture-games";

const controls = (page: Page) => page.getByRole("region", { name: "Board play controls" });
test.beforeEach(async ({ request }) => { await finishFixtureGames(request); });
async function show(page: Page, id: string) {
  await page.goto(`/games/${id}`);
  await expandedWorkspace(page);
  await page.bringToFront();
  await expect(page.getByLabel("Connection live")).toBeVisible();
}
async function create(page: Page) {
  return (await page.request.post("/api/games", { data: { opponent: "human", start_paused: true, initial_time_ms: 3600000 } })).json();
}

test("confirmed restart synchronizes separate device sessions and preserves its target", async ({ page, browser, baseURL, hasTouch }) => {
  const original = await create(page);
  const otherContext = await browser.newContext({ baseURL, hasTouch, viewport: page.viewportSize()! });
  const other = await otherContext.newPage();
  await show(other, original.id);
  await show(page, original.id);
  await page.evaluate(() => localStorage.setItem("restart-test-device-marker", "source"));
  expect(await other.evaluate(() => localStorage.getItem("restart-test-device-marker"))).toBeNull();
  await page.getByLabel("Black seat", { exact: true }).selectOption("human");
  await controls(page).getByRole("button", { name: "End and start new…", exact: true }).click();
  await expect(page.getByRole("dialog")).toContainText(original.id.slice(0, 8).toUpperCase());
  const created = page.waitForResponse(r => r.url().endsWith("/api/games") && r.request().method() === "POST");
  await page.getByRole("dialog").getByRole("button", { name: "End and start new", exact: true }).click();
  const next = await (await created).json();
  await expect(page).toHaveURL(new RegExp(`/games/${next.id}$`));
  await expect(controls(page)).toContainText("White to move");
  await other.bringToFront();
  await expect(controls(other)).toContainText("Match aborted");
  await expect(other.getByRole("button", { name: "Reset", exact: true })).toBeDisabled();
  expect((await other.request.post(`/api/games/${original.id}/reset`)).status()).toBe(409);
  await other.reload();
  await expandedWorkspace(other);
  await expect(controls(other)).toContainText("Match aborted");
  await other.goto("/");
  await expandedWorkspace(other);
  await expect(other).toHaveURL(new RegExp(`/games/${next.id}$`));
  await expect(controls(other)).toContainText("White to move");
  await other.locator('[data-square="e2"]').click();
  await other.locator('[data-square="e4"]').click();
  await page.bringToFront();
  await expect(page.locator('[data-square="e4"]')).toHaveAttribute("aria-label", "e4 white pawn");
  const saved = await (await page.request.get(`/api/games/${original.id}`)).json();
  expect([saved.lifecycle, saved.fen, saved.moves, saved.generation]).toEqual(["aborted", original.fen, original.moves, original.generation]);
  expect((await page.request.get("/api/live-match")).ok()).toBeTruthy();
  await otherContext.close();
});

test("restart reveals an older blocking match without silently ending it", async ({ page }) => {
  const older = await create(page);
  const selected = await create(page); // Simulates legacy/API-created multiple tables.
  await show(page, selected.id);
  await page.getByLabel("Black seat", { exact: true }).selectOption("human");
  await controls(page).getByRole("button", { name: "End and start new…", exact: true }).click();
  await page.getByRole("dialog").getByRole("button", { name: "End and start new", exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`/games/${older.id}$`));
  await expect(controls(page)).toContainText("Match paused");
  await expect(controls(page).getByRole("alert")).toContainText(older.id.slice(0, 8).toUpperCase());
  const preserved = await (await page.request.get(`/api/games/${older.id}`)).json();
  expect([preserved.lifecycle, preserved.revision]).toEqual(["paused", older.revision]);
  expect((await (await page.request.get(`/api/games/${selected.id}`)).json()).lifecycle).toBe("aborted");
});

test("two tabs racing New match converge on one current game", async ({ page, context }) => {
  const old = await create(page);
  await page.request.post(`/api/games/${old.id}/abort`);
  const other = await context.newPage();
  for (const tab of [page, other]) {
    await show(tab, old.id);
    await tab.getByLabel("Black seat", { exact: true }).selectOption("human");
  }
  const responses: number[] = [];
  for (const tab of [page, other]) tab.on("response", r => { if (r.url().endsWith("/api/games") && r.request().method() === "POST") responses.push(r.status()); });
  // Dispatch both explicit button activations without changing game IDs.
  await Promise.all([page, other].map(tab => tab.getByRole("button", { name: "New match", exact: true }).evaluate(button => (button as HTMLButtonElement).click())));
  await expect.poll(() => responses.length).toBe(2);
  expect(responses.sort()).toEqual([201, 409]);
  const current = await (await page.request.get("/api/live-match")).json();
  for (const tab of [page, other]) {
    await tab.bringToFront();
    await expect(tab).toHaveURL(new RegExp(`/games/${current.id}$`));
    await expect(controls(tab)).toContainText("White to move");
  }
  await other.close();
});

test("a reset after confirmation opened cannot make restart end a different generation", async ({ page }) => {
  const game = await create(page);
  await show(page, game.id);
  await controls(page).getByRole("button", { name: "End and start new…", exact: true }).click();
  const reset = await (await page.request.post(`/api/games/${game.id}/reset`)).json();
  await page.getByRole("dialog").getByRole("button", { name: "End and start new", exact: true }).click();
  await expect(controls(page).getByRole("alert")).toContainText("was reset");
  const current = await (await page.request.get("/api/live-match")).json();
  expect([current.id, current.generation, current.lifecycle]).toEqual([game.id, reset.generation, "running"]);
});
