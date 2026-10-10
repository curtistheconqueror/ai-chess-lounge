import { expandedWorkspace } from "./workspace-fixture";
import { expect, test, type Locator } from "@playwright/test";
import { finishFixtureGames } from "./fixture-games";

test("paused and aborted boards offer a visible path back to play", async ({ page, hasTouch }) => {
  const press = (target: Locator) => hasTouch ? target.tap() : target.click();
  await finishFixtureGames(page.request);
  const created = await page.request.post("/api/games", { data: { opponent: "human", initial_time_ms: 3600000 } });
  const game = await created.json();
  const moved = await (await page.request.post(`/api/games/${game.id}/moves`, { data: { move: "e2e4", position_version: game.version } })).json();
  expect((await page.request.post(`/api/games/${game.id}/pause`, { data: { expected_revision: moved.revision } })).ok()).toBeTruthy();
  await page.goto(`/games/${game.id}`);
  await expandedWorkspace(page);
  await expect(page.getByLabel("Connection live")).toBeVisible();
  const controls = page.getByRole("region", { name: "Board play controls" });
  await expect(controls).toContainText("Match paused");
  await expect(page.locator('[data-square="d7"]')).toBeDisabled();
  await press(controls.getByRole("button", { name: "Resume play" }));
  await expect(controls).toContainText("Black to move");
  await press(page.locator('[data-square="d7"]'));
  await press(page.locator('[data-square="d5"]'));
  await expect(page.locator('[data-square="d5"]')).toHaveAttribute("aria-label", "d5 black pawn");
  await page.getByRole("button", { name: "Abort match", exact: true }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Abort match", exact: true }).click();
  await expect(controls).toContainText("Match aborted");
  await expect(controls).toContainText("final position and history are saved");
  const archived = await (await page.request.get(`/api/games/${game.id}`)).json();
  expect(archived.status).toBe("aborted");
  expect(archived.moves.map((move: { uci: string }) => move.uci)).toEqual(["e2e4", "d7d5"]);
  await page.reload();
  await expandedWorkspace(page);
  await expect(controls).toContainText("Match aborted");
  await page.getByLabel("Black seat", { exact: true }).selectOption("human");
  const nextResponse = page.waitForResponse(response => response.url().endsWith("/api/games") && response.request().method() === "POST");
  await press(controls.getByRole("button", { name: "Play a new match" }));
  const next = await (await nextResponse).json();
  expect(next.id).not.toBe(game.id);
  await expect(page).toHaveURL(new RegExp(`/games/${next.id}$`));
  await expect(controls).toContainText("White to move");
  await press(page.locator('[data-square="e2"]'));
  await press(page.locator('[data-square="e4"]'));
  await expect(page.locator('[data-square="e4"]')).toHaveAttribute("aria-label", "e4 white pawn");
  const preserved = await (await page.request.get(`/api/games/${game.id}`)).json();
  expect([preserved.status, preserved.fen, preserved.version, preserved.revision, preserved.moves]).toEqual(
    [archived.status, archived.fen, archived.version, archived.revision, archived.moves]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBeTruthy();
  await page.request.post(`/api/games/${next.id}/pause`);
});

test("private runner denial stops polling without blocking chess", async ({ page }) => {
  await finishFixtureGames(page.request);
  let requests = 0;
  await page.route("**/api/runner-sessions", route => {
    requests++;
    return route.fulfill({ status: 403, json: { detail: "Private sharing access denied." } });
  });
  await page.clock.install();
  const created = await page.request.post("/api/games", { data: { opponent: "human", initial_time_ms: 3600000 } });
  const game = await created.json();
  await page.goto(`/games/${game.id}`);
  await expandedWorkspace(page);
  await expect(page.getByLabel("Connection live")).toBeVisible();
  await expect(page.getByLabel("Remote runner pairing")).toHaveCount(0);
  const before = requests;
  await page.clock.fastForward(10000);
  expect(requests).toBe(before);
  await expect(page.locator('[data-square="e2"]')).toBeEnabled();
  await page.locator('[data-square="e2"]').click();
  await page.locator('[data-square="e4"]').click();
  await expect(page.locator('[data-square="e4"]')).toHaveAttribute("aria-label", "e4 white pawn");
});

test.describe("request failure feedback", () => {
  test.use({ serviceWorkers: "block" }); // Route mocking must reach the browser network layer in WebKit.
  test("failed resume is explained beside the board without enabling moves", async ({ page }) => {
    await finishFixtureGames(page.request);
    const created = await page.request.post("/api/games", { data: { opponent: "human", start_paused: true } });
    const game = await created.json();
    await page.goto(`/games/${game.id}`);
    await expandedWorkspace(page);
    await expect(page.getByLabel("Connection live")).toBeVisible();
    await page.route(`**/api/games/${game.id}/resume`, route => route.fulfill({ status: 409, json: { detail: "This match changed. Review its current state." } }));
    const controls = page.getByRole("region", { name: "Board play controls" });
    await controls.getByRole("button", { name: "Resume play" }).click();
    await expect(controls.getByRole("alert")).toContainText("This match changed");
    await expect(controls).toContainText("Match paused");
    await expect(page.locator('[data-square="e2"]')).toBeDisabled();
    expect((await (await page.request.get(`/api/games/${game.id}`)).json()).moves).toEqual([]);
  });
});
