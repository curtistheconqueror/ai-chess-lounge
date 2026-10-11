import { expect, test } from "@playwright/test";
import { finishFixtureGames } from "./fixture-games";

test.beforeEach(async ({ request }) => { await finishFixtureGames(request); });

test("a move lost to a server outage explains itself and the notice clears on reconnect", async ({ page }) => {
  const game = await (await page.request.post("/api/games", { data: { opponent: "human", initial_time_ms: 3_600_000 } })).json();
  await page.goto(`/games/${game.id}`);
  await expect(page.getByLabel("Connection live")).toBeVisible();
  // The server dies while the move request is in flight.
  await page.route("**/api/games/*/moves", route => route.abort("connectionrefused"));
  await page.getByRole("gridcell", { name: "e2 white pawn" }).click();
  await page.getByRole("gridcell", { name: "e4 empty" }).click();
  const notice = page.getByRole("alert").filter({ hasText: "Lost connection to the server" });
  await expect(notice).toBeVisible();
  await expect(page.getByText("Failed to fetch")).toHaveCount(0);
  // No ghost move: the board shows the server position.
  await expect(page.getByRole("gridcell", { name: "e2 white pawn" })).toBeVisible();
  // A proxy in front of a restarting server answers 502: same plain message.
  await page.unroute("**/api/games/*/moves");
  await page.route("**/api/games/*/moves", route => route.fulfill({ status: 502, contentType: "text/plain", body: "Bad Gateway" }));
  await page.getByRole("gridcell", { name: "e2 white pawn" }).click();
  await page.getByRole("gridcell", { name: "e4 empty" }).click();
  await expect(notice).toBeVisible();
  await expect(page.getByText("Bad Gateway")).toHaveCount(0);
  // The live connection comes back (a fresh socket after returning to the tab) and the notice goes.
  await page.unroute("**/api/games/*/moves");
  await page.evaluate(() => document.dispatchEvent(new Event("visibilitychange")));
  await expect(page.getByLabel("Connection live")).toBeVisible();
  await expect(notice).toHaveCount(0);
  await page.getByRole("gridcell", { name: "e2 white pawn" }).click();
  await page.getByRole("gridcell", { name: "e4 empty" }).click();
  await expect.poll(async () => (await (await page.request.get(`/api/games/${game.id}`)).json()).moves.length).toBe(1);
});
