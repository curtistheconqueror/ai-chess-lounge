import { expect, test } from "@playwright/test";
import { finishFixtureGames } from "./fixture-games";
import { expandedWorkspace } from "./workspace-fixture";

declare global { interface Window { spoken: string[] } }

test.beforeEach(async ({ request }) => { await finishFixtureGames(request); });

test("optional voice says Check and Checkmate for live moves only, and stays silent when off or muted", async ({ page, context }) => {
  await context.addInitScript(() => {
    window.spoken = [];
    // Record what would be spoken without depending on an installed system voice.
    Object.defineProperty(window, "speechSynthesis", {
      configurable: true,
      value: { speak: (u: SpeechSynthesisUtterance) => window.spoken.push(u.text), cancel: () => undefined },
    });
  });
  const game = await (await page.request.post("/api/games", { data: { opponent: "human", initial_time_ms: 3_600_000 } })).json();
  await page.goto(`/games/${game.id}`);
  await expect(page.getByLabel("Connection live")).toBeVisible();
  await expandedWorkspace(page);
  // One move at a time, as in a real game: each reaches the page before the next is played.
  // (A burst arrives as a history gap, which is deliberately silent.)
  const play = async (uci: string) => {
    const current = await (await page.request.get(`/api/games/${game.id}`)).json();
    expect((await page.request.post(`/api/games/${game.id}/moves`, { data: { move: uci, position_version: current.version } })).ok()).toBeTruthy();
    await expect(page.locator(".sr-only[aria-live]")).toContainText(`Position ${current.moves.length + 1}.`);
  };
  // Off by default: a check is not announced.
  await page.getByRole("button", { name: "Test sound", exact: true }).click();
  await play("e2e4"); await play("f7f6"); await play("d1h5"); // Qh5+ is check.
  await expect(page.locator(".move-row")).toHaveCount(2);
  expect(await page.evaluate(() => window.spoken)).toEqual([]);
  // Turned on: the toggle tap unlocks speech, then a check and a mate are announced once each.
  await page.getByLabel("Say “Check” and “Checkmate”").check();
  await expect.poll(() => page.evaluate(() => window.spoken)).toEqual(["Voice on"]);
  await play("g7g6"); await play("h5g6"); // Qxg6+ check.
  await expect.poll(() => page.evaluate(() => window.spoken)).toEqual(["Voice on", "Check"]);
  await play("h7g6"); // A quiet reply is not announced.
  await page.waitForTimeout(300);
  expect(await page.evaluate(() => window.spoken)).toEqual(["Voice on", "Check"]);
  const fresh = await (await page.request.post("/api/games/" + game.id + "/abort")).json();
  expect(fresh.status).not.toBe("active");
  // Fool's mate in a new game: the final move is announced as Checkmate, not Check.
  await finishFixtureGames(page.request);
  const mate = await (await page.request.post("/api/games", { data: { opponent: "human", initial_time_ms: 3_600_000 } })).json();
  await page.close();
  page = await context.newPage(); // The voice preference persists per device.
  await page.goto(`/games/${mate.id}`);
  await expect(page.getByLabel("Connection live")).toBeVisible();
  await page.evaluate(() => { window.spoken = []; });
  await page.getByRole("gridcell", { name: "a2 white pawn" }).click(); // Any gesture; audio/voice stay enabled.
  for (const uci of ["f2f3", "e7e5", "g2g4", "d8h4"]) {
    const current = await (await page.request.get(`/api/games/${mate.id}`)).json();
    await page.request.post(`/api/games/${mate.id}/moves`, { data: { move: uci, position_version: current.version } });
    await expect(page.locator(".sr-only[aria-live]")).toContainText(`Position ${current.moves.length + 1}.`);
  }
  await expect.poll(() => page.evaluate(() => window.spoken.at(-1))).toBe("Checkmate");
  expect(await page.evaluate(() => window.spoken.filter(text => text === "Checkmate").length)).toBe(1);
  // Reloading a finished game never re-announces it.
  await page.reload();
  await expect(page.locator(".board")).toBeVisible();
  await page.waitForTimeout(500);
  expect(await page.evaluate(() => window.spoken)).toEqual([]);
});
