import type { Page } from "@playwright/test";

export async function pointerMove(page: Page, from: string, to: string) {
  const board = page.getByRole("grid", { name: "Chess board", exact: true });
  await board.scrollIntoViewIfNeeded();
  const start = await board.locator(`[data-square="${from}"]`).boundingBox();
  const end = await board.locator(`[data-square="${to}"]`).boundingBox();
  if (!start || !end) throw new Error("Board squares are not visible");
  await page.mouse.move(start.x + start.width / 2, start.y + start.height / 2);
  await page.mouse.down();
  await page.mouse.move(end.x + end.width / 2, end.y + end.height / 2, { steps: 8 });
  await page.mouse.up();
}
