import { expect, test } from "@playwright/test";

test("four board finishes compare the same position without changing a match", async ({ page }) => {
  const writes: string[] = [];
  page.on("request", request => { if (request.method() !== "GET") writes.push(request.url()); });
  await page.goto("/board-studio");
  await expect(page.getByRole("heading", { name: "Choose the board's feel." })).toBeVisible();
  await expect(page.getByRole("grid", { name: "Chess board" })).toHaveCount(4);
  await expect(page.getByRole("gridcell")).toHaveCount(256);
  const pieces = await page.locator(".board-look").evaluateAll(boards => boards.map(board =>
    [...board.querySelectorAll('[role="gridcell"]')].map(square => square.getAttribute("aria-label"))));
  for (const board of pieces) expect(board).toEqual(pieces[0]);
  for (const look of ["club", "wood", "glass", "metal"]) {
    const board = page.locator(`.board-look-${look}`);
    await expect(board.locator(".coordinate")).toHaveCount(16);
    const cells = await board.locator(".square").evaluateAll(elements => elements.map(element => {
      const rect = element.getBoundingClientRect(); return { width: rect.width, height: rect.height };
    }));
    expect(cells.every(cell => cell.width >= 25 && Math.abs(cell.width - cell.height) < 1)).toBeTruthy();
  }
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  await page.screenshot({ path: `test-results/board-studio-${test.info().project.name}.png`, fullPage: true });
  await page.getByRole("button", { name: "Flip all boards" }).click();
  for (const board of await page.getByRole("grid", { name: "Chess board" }).all()) {
    await expect(board.getByRole("gridcell").first()).toHaveAttribute("aria-label", /^h1 /);
  }
  await page.getByLabel("Comparison position").selectOption("start");
  await expect(page.getByRole("gridcell", { name: "e2 white pawn" })).toHaveCount(4);
  await page.getByLabel("Show move highlights").uncheck();
  await expect(page.locator(".square.selected, .square.last-move, .square.legal-target")).toHaveCount(0);
  expect(writes).toEqual([]);
});
