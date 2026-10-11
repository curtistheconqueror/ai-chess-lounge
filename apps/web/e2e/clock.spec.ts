import { expect, test } from "@playwright/test";
import { finishFixtureGames } from "./fixture-games";

test.beforeEach(async ({ request }) => { await finishFixtureGames(request); });

test("running clock ticks locally, shows tenths and warns under ten seconds with no board DOM churn", async ({ page }) => {
  const game = await (await page.request.post("/api/games", { data: { opponent: "human", initial_time_ms: 12_000 } })).json();
  await page.goto(`/games/${game.id}`);
  await expect(page.getByLabel("Connection live")).toBeVisible();
  // Count board subtree mutations while only the clock should be changing.
  await page.evaluate(() => {
    const board = document.querySelector(".board")!;
    (window as unknown as { boardMutations: number }).boardMutations = 0;
    new MutationObserver(records => { (window as unknown as { boardMutations: number }).boardMutations += records.length; })
      .observe(board, { subtree: true, childList: true, attributes: true, characterData: true });
  });
  const white = page.locator(".player-card.white .player-clock");
  await expect(white).toHaveText(/^0:0\d\.\d$/, { timeout: 5_000 });
  await expect(white).toHaveClass(/urgent/);
  const first = await white.textContent();
  await expect.poll(() => white.textContent(), { timeout: 2_000 }).not.toBe(first);
  await expect(page.locator(".player-card.black .player-clock")).toHaveText("0:12");
  expect(await page.evaluate(() => (window as unknown as { boardMutations: number }).boardMutations)).toBe(0);
  await page.request.post(`/api/games/${game.id}/abort`);
});
