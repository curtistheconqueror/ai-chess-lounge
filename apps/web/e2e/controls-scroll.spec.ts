import { expect, test, type Locator } from "@playwright/test";
import { finishFixtureGames } from "./fixture-games";

test.beforeEach(async ({ request }) => { await finishFixtureGames(request); });

test("open header tools never cover board actions after scrolling from setup", async ({ page, hasTouch }) => {
  await page.goto("/");
  const controls = page.getByRole("region", { name: "Board play controls" });
  await expect(controls).toContainText("Ready to start");
  const tools = page.locator(".lounge-tools");
  const more = controls.locator(".more-menu");
  const press = async (button: Locator) => {
    await button.scrollIntoViewIfNeeded();
    await expect.poll(() => button.evaluate(element => {
      const rect = element.getBoundingClientRect();
      const hit = document.elementFromPoint(rect.x + rect.width / 2, rect.y + rect.height / 2);
      return Boolean(hit && element.contains(hit));
    })).toBe(true);
    if (hasTouch) await button.tap(); else await button.click();
  };
  // The tools menu floats over the page; with it open every board action must still be hittable, and
  // using one of them (an outside press) closes the menu.
  const openTools = async () => {
    if (!(await tools.evaluate(menu => (menu as HTMLDetailsElement).open))) await press(tools.locator("summary"));
    await expect(tools).toHaveAttribute("open", "");
    await expect(page.getByRole("link", { name: "Model Lab", exact: true })).toBeVisible();
  };
  const pressWithToolsOpen = async (button: Locator) => {
    await openTools();
    await press(button);
    await expect(tools).not.toHaveAttribute("open");
  };
  await openTools();
  await expect(page.getByRole("link", { name: "AI leaderboards", exact: true })).toBeVisible();
  await pressWithToolsOpen(controls.getByRole("button", { name: "Seats & game setup", exact: true }));
  await page.getByLabel("Black seat", { exact: true }).selectOption("human");
  // Reproduce CI151: configure below the board, then scroll back with the tools open.
  let creates = 0;
  page.on("request", r => { if (r.method() === "POST" && r.url().endsWith("/api/games")) creates++; });
  await pressWithToolsOpen(controls.getByRole("button", { name: "Play a new match", exact: true }));
  await expect(controls).toContainText("White to move");
  expect(creates).toBe(1);
  const id = page.url().split("/").at(-1)!;
  const namedGame = id.slice(0, 8).toUpperCase();
  await page.getByLabel("Black seat", { exact: true }).scrollIntoViewIfNeeded();
  await pressWithToolsOpen(controls.getByRole("button", { name: "Pause play", exact: true }));
  await expect(controls).toContainText("Match paused");
  await page.getByLabel("Black seat", { exact: true }).scrollIntoViewIfNeeded();
  await pressWithToolsOpen(controls.getByRole("button", { name: "Resume play", exact: true }));
  await expect(controls).toContainText("White to move");
  await page.getByLabel("Black seat", { exact: true }).scrollIntoViewIfNeeded();
  // Secondary actions live in More: open it with the tools menu open, then choose from it.
  await pressWithToolsOpen(more.locator("summary"));
  await expect(more).toHaveAttribute("open", "");
  await press(more.getByRole("button", { name: /^End and start new/ }));
  await expect(page.getByRole("dialog")).toContainText(namedGame);
  await press(page.getByRole("dialog").getByRole("button", { name: "Cancel", exact: true }));
  expect((await (await page.request.get(`/api/games/${id}`)).json()).lifecycle).toBe("running");
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);
  await openTools();
  await tools.locator("summary").focus();
  await page.keyboard.press("Escape");
  await expect(tools).not.toHaveAttribute("open");
});
