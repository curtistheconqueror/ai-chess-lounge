import { expect, test, type APIRequestContext, type Page } from "@playwright/test";
import { finishFixtureGames } from "./fixture-games";

const controls = (page: Page) => page.getByRole("region", { name: "Board play controls" });
async function fixture(request: APIRequestContext, paused = false) {
  const response = await request.post("/api/games", { data: { opponent: "human", start_paused: paused, initial_time_ms: 3600000 } });
  expect(response.ok()).toBeTruthy();
  return response.json();
}
async function snapshot(request: APIRequestContext, id: string) {
  return (await request.get(`/api/games/${id}`)).json();
}
async function visibility(page: Page, value: "hidden" | "visible") {
  await page.evaluate(value => {
    Object.defineProperty(document, "visibilityState", { configurable: true, get: () => value });
    document.dispatchEvent(new Event("visibilitychange"));
  }, value);
}
test.beforeEach(async ({ request }) => { await finishFixtureGames(request); });

test("fresh and stale saved entries show an explicit start without creating a game", async ({ page, hasTouch }) => {
  const old = await fixture(page.request);
  await page.request.post(`/api/games/${old.id}/abort`);
  let creates = 0;
  page.on("request", r => { if (r.method() === "POST" && r.url().endsWith("/api/games")) creates++; });
  await page.goto("/");
  await expect(controls(page)).toContainText("Ready to start");
  await expect(page.getByLabel("Connection ready")).toBeVisible();
  await expect(page.getByLabel("Match broadcast status")).toContainText("READY TO START");
  await expect(page.locator(".result-badge")).toHaveText("READY");
  await page.evaluate(async oldId => {
    localStorage.setItem("ai-chess-lounge:active-game", oldId);
    await navigator.serviceWorker.ready;
    // Deliberately stale cache data must never become the current match.
    const cache = await caches.open("chess-lounge-offline-v1");
    await cache.put("/api/live-match", new Response(JSON.stringify({ id: oldId, status: "active" })));
  }, old.id);
  await page.reload();
  await expect(controls(page)).toContainText("Ready to start");
  await expect(page).toHaveURL(/\/$/);
  expect(creates).toBe(0);
  await page.getByLabel("Black seat", { exact: true }).selectOption("human");
  const start = controls(page).getByRole("button", { name: "Play a new match" });
  if (hasTouch) await start.tap(); else await start.click();
  await expect(controls(page)).toContainText("White to move");
  expect(creates).toBe(1);
  expect((await snapshot(page.request, old.id)).status).toBe("aborted");
});

test("root discovers a paused table despite stale storage and resumes by touch", async ({ page, hasTouch }, info) => {
  await page.addInitScript(() => localStorage.setItem("ai-chess-lounge:active-game", "missing-old-game"));
  const live = await fixture(page.request, true);
  await page.goto("/");
  await expect(page).toHaveURL(new RegExp(`/games/${live.id}$`));
  await expect(controls(page)).toContainText("Match paused");
  const press = async (selector: ReturnType<Page["locator"]>) => hasTouch ? selector.tap() : selector.click();
  await press(controls(page).getByRole("button", { name: "Resume play" }));
  await expect(controls(page)).toContainText("White to move");
  await press(page.locator('[data-square="e2"]'));
  await press(page.locator('[data-square="e4"]'));
  await expect(controls(page)).toContainText("Black to move");
  const size = page.viewportSize()!;
  await page.setViewportSize({ width: size.height, height: size.width });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBeTruthy();
  await press(page.locator('[data-square="d7"]'));
  await press(page.locator('[data-square="d5"]'));
  await expect(controls(page)).toContainText("White to move");
  await controls(page).scrollIntoViewIfNeeded();
  await page.screenshot({ path: info.outputPath(`entry-${info.project.name}.png`) });
  expect((await snapshot(page.request, live.id)).moves.map((m: { uci: string }) => m.uci)).toEqual(["e2e4", "d7d5"]);
});

test("terminal deep link preserves review and a conflicting new match opens the existing table", async ({ page }) => {
  const archive = await fixture(page.request);
  await page.request.post(`/api/games/${archive.id}/abort`);
  const before = await snapshot(page.request, archive.id);
  const live = await fixture(page.request, true);
  await page.goto(`/games/${archive.id}`);
  await expect(controls(page)).toContainText("Match aborted");
  await expect(page).toHaveURL(new RegExp(`/games/${archive.id}$`));
  await controls(page).getByRole("button", { name: "Play a new match" }).click();
  await expect(page).toHaveURL(new RegExp(`/games/${live.id}$`));
  await expect(controls(page)).toContainText("Match paused");
  await expect(controls(page).getByRole("alert")).toContainText("already on the table");
  const after = await snapshot(page.request, archive.id);
  expect([after.fen, after.moves, after.status, after.revision]).toEqual([before.fen, before.moves, before.status, before.revision]);
  expect((await snapshot(page.request, live.id)).lifecycle).toBe("paused");
});

test("missing deep link offers the current table without silently replacing review", async ({ page }) => {
  const live = await fixture(page.request, true);
  await page.goto("/games/missing-entry-fixture");
  await expect(controls(page).getByRole("alert")).toContainText("shared match is unavailable");
  await expect(page).toHaveURL(/missing-entry-fixture$/);
  await controls(page).getByRole("link", { name: "Open current table" }).click();
  await expect(page).toHaveURL(new RegExp(`/games/${live.id}$`));
  await expect(controls(page)).toContainText("Match paused");
});

test("foreground refresh explains remotely paused and ended games before enabling moves", async ({ page }) => {
  const live = await fixture(page.request);
  await page.goto(`/games/${live.id}`);
  await expect(controls(page)).toContainText("White to move");
  await visibility(page, "hidden");
  await expect(page.locator('[data-square="e2"]')).toBeDisabled();
  await page.request.post(`/api/games/${live.id}/pause`);
  await visibility(page, "visible");
  await expect(controls(page)).toContainText("Match paused");
  await expect(page.locator('[data-square="e2"]')).toBeDisabled();
  await visibility(page, "hidden");
  await page.request.post(`/api/games/${live.id}/abort`);
  await visibility(page, "visible");
  await expect(controls(page)).toContainText("Match aborted");
  await expect(controls(page).getByRole("button", { name: "Play a new match" })).toBeEnabled();
  expect((await snapshot(page.request, live.id)).moves).toEqual([]);
});

test("storage unavailable does not prevent fresh entry or selecting a match", async ({ page }) => {
  await page.addInitScript(() => {
    for (const method of ["getItem", "setItem", "removeItem"]) {
      Object.defineProperty(Storage.prototype, method, { value: () => { throw new DOMException("Storage unavailable", "SecurityError"); } });
    }
  });
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  const live = await fixture(page.request, true);
  await page.goto("/");
  await expect(controls(page)).toContainText("Match paused");
  await expect(page).toHaveURL(new RegExp(`/games/${live.id}$`));
  expect(errors).toEqual([]);
});

test("finished review links return to an active table without creating or resuming games", async ({ page }) => {
  const archive = await fixture(page.request);
  expect((await page.request.post(`/api/games/${archive.id}/adjudicate`, { data: { result: "1-0" } })).ok()).toBeTruthy();
  const live = await fixture(page.request);
  const mutations: string[] = [];
  page.on("request", r => { if (r.method() === "POST") mutations.push(r.url()); });
  await page.goto(`/games/${archive.id}`);
  await expect(controls(page)).toContainText("Match finished");
  await expect(page.locator('[data-square="e2"]')).toBeDisabled();
  await controls(page).getByRole("link", { name: "Open current table" }).click();
  await expect(page).toHaveURL(new RegExp(`/games/${live.id}$`));
  await expect(controls(page)).toContainText("White to move");
  await expect(page.locator('[data-square="e2"]')).toBeEnabled();
  expect(mutations).toEqual([]);
});

test.describe("entry network recovery", () => {
  test.use({ serviceWorkers: "block" }); // Deterministic browser-level response mocking.
  test("failed lookup stays visible and current-table navigation retries safely", async ({ page }) => {
    const live = await fixture(page.request, true);
    await page.route("**/api/live-match", route => route.fulfill({ status: 503, body: "Unavailable" }));
    await page.goto("/");
    await expect(controls(page).getByRole("alert")).toContainText("503");
    await expect(page.locator('[data-square="e2"]')).toBeDisabled();
    await page.unroute("**/api/live-match");
    await controls(page).getByRole("link", { name: "Open current table" }).click();
    await expect(page).toHaveURL(new RegExp(`/games/${live.id}$`));
    await expect(controls(page)).toContainText("Match paused");
    expect((await snapshot(page.request, live.id)).lifecycle).toBe("paused");
  });
});
