import { expandedWorkspace } from "./workspace-fixture";
import { expect, test } from "@playwright/test";

test("approved classic pieces appear on the live board and all comparison surfaces", async ({ page }) => {
  const writes: string[] = [];
  page.on("request", request => { if (request.method() !== "GET") writes.push(request.url()); });
  await page.goto("/board-studio?pieces=compare");
  await expect(page.getByRole("heading", { name: "A clearer classic set." })).toBeVisible();
  await expect(page.getByRole("region", { name: "Previous pieces", exact: true }).locator(".classic-piece")).toHaveCount(0);
  await expect(page.getByRole("region", { name: "Approved pieces", exact: true }).locator(".classic-piece")).toHaveCount(32);
  for (const size of [32, 40, 64]) {
    const specimens = page.getByRole("region", { name: `${size} pixel pieces` });
    await expect(specimens.locator("svg")).toHaveCount(24);
    for (const color of ["white", "black"]) for (const type of ["king", "queen", "rook", "bishop", "knight", "pawn"]) {
      await expect(specimens.getByRole("img", { name: `${color} ${type}`, exact: true })).toHaveCount(2);
    }
    const dimensions = await specimens.locator("svg").evaluateAll(nodes => nodes.map(node => {
      const rect = node.getBoundingClientRect(); return [rect.width, rect.height];
    }));
    expect(dimensions.every(([width, height]) => width === size && height === size)).toBeTruthy();
  }
  for (const finish of ["club", "wood", "glass", "metal"]) {
    await page.getByLabel("Piece comparison finish").selectOption(finish);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  }
  await page.getByLabel("Piece comparison finish").selectOption("club");
  await page.screenshot({ path: `test-results/piece-studio-${test.info().project.name}.png`, fullPage: true });
  await page.getByLabel("Silhouette check").check();
  await expect(page.locator(".classic-eye").first()).toBeHidden();
  await page.screenshot({ path: `test-results/piece-silhouettes-${test.info().project.name}.png`, fullPage: true });
  await page.getByRole("button", { name: "Board finishes", exact: true }).click();
  await expect(page.getByRole("grid", { name: "Chess board" })).toHaveCount(4);
  await expect(page.locator(".classic-piece")).toHaveCount(await page.locator(".piece-svg").count());
  expect(writes).toEqual([]);
  const game = await (await page.request.post("/api/games", { data: { opponent: "human", initial_time_ms: 3600000 } })).json();
  await page.goto(`/games/${game.id}`);
  await expandedWorkspace(page);
  await expect(page.getByRole("gridcell")).toHaveCount(64);
  await expect(page.locator(".piece-svg")).toHaveCount(32);
  await expect(page.locator(".classic-piece")).toHaveCount(32);
  await page.getByRole("gridcell", { name: "g1 white knight" }).click();
  await page.getByRole("gridcell", { name: "f3 empty" }).click();
  await expect(page.getByRole("gridcell", { name: "f3 white knight" }).locator(".classic-piece")).toBeVisible();
  await page.reload();
  await expandedWorkspace(page);
  await expect(page.getByLabel("Connection live")).toBeVisible();
  await expect(page.getByRole("gridcell", { name: "f3 white knight" }).locator(".classic-piece")).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  await page.screenshot({ path: `test-results/approved-live-board-${test.info().project.name}.png`, fullPage: true });
});
