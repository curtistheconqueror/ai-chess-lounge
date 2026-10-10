import { expect, test, type Locator } from "@playwright/test";
import { finishFixtureGames } from "./fixture-games";

test.beforeEach(async ({ request }) => { await finishFixtureGames(request); });

test("open header tools never cover board actions after scrolling from setup", async ({ page, hasTouch }) => {
  await page.goto("/");
  const controls = page.getByRole("region", { name: "Board play controls" });
  await expect(controls).toContainText("Ready to start");
  const press = async (button: Locator) => {
    await button.scrollIntoViewIfNeeded();
    await expect.poll(() => button.evaluate(element => {
      const rect = element.getBoundingClientRect();
      const hit = document.elementFromPoint(rect.x + rect.width / 2, rect.y + rect.height / 2);
      return Boolean(hit && element.contains(hit));
    })).toBe(true);
    if (hasTouch) await button.tap(); else await button.click();
  };
  await press(page.locator(".lounge-tools > summary"));
  await expect(page.getByRole("button", { name: "Model Lab", exact: true })).toBeVisible();
  await press(controls.getByRole("button", { name: "Seats & game setup", exact: true }));
  await page.getByLabel("Black seat", { exact: true }).selectOption("human");
  // Reproduce CI151: configure below the board, then scroll back with the tools open.
  await expect(page.locator(".lounge-tools")).toHaveAttribute("open", "");
  let creates = 0;
  page.on("request", r => { if (r.method() === "POST" && r.url().endsWith("/api/games")) creates++; });
  await press(controls.getByRole("button", { name: "Play a new match", exact: true }));
  await expect(controls).toContainText("White to move");
  expect(creates).toBe(1);
  const id = page.url().split("/").at(-1)!;
  const namedGame = id.slice(0, 8).toUpperCase();
  await page.getByLabel("Black seat", { exact: true }).scrollIntoViewIfNeeded();
  await press(controls.getByRole("button", { name: "Pause play", exact: true }));
  await expect(controls).toContainText("Match paused");
  await page.getByLabel("Black seat", { exact: true }).scrollIntoViewIfNeeded();
  await press(controls.getByRole("button", { name: "Resume play", exact: true }));
  await expect(controls).toContainText("White to move");
  await page.getByLabel("Black seat", { exact: true }).scrollIntoViewIfNeeded();
  await press(controls.getByRole("button", { name: /^End and start new/ }));
  await expect(page.getByRole("dialog")).toContainText(namedGame);
  await press(page.getByRole("dialog").getByRole("button", { name: "Cancel", exact: true }));
  expect((await (await page.request.get(`/api/games/${id}`)).json()).lifecycle).toBe("running");
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);
  await page.locator(".lounge-tools > summary").focus();
  await page.keyboard.press("Escape");
  await expect(page.locator(".lounge-tools")).not.toHaveAttribute("open");
});
