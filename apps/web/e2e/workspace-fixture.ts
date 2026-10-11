import type { Locator, Page } from "@playwright/test";

/** Legacy feature suites exercise the expanded workspace. Disclosure keyboard,
 * focus, shortcut and collapsed-layout behavior are tested in workspace.spec.ts.
 * Setting the fixture state directly avoids unlocking audio before audio tests.
 *
 * Only the right-rail workspace sections are opened. The "Lounge tools" and "More"
 * menus are floating overlays: opening them here would cover the top bar and the
 * board actions, so tests open them explicitly (openLoungeTools / chooseMore).
 */
export async function expandedWorkspace(page: Page) {
  await page.locator(".board").waitFor();
  // Includes the collapsed "Experimental" live-strength switch inside setup when a Stockfish game is live.
  await page.locator(".workspace-section, .experimental-strength").evaluateAll(sections => {
    sections.forEach(section => { (section as HTMLDetailsElement).open = true; });
  });
}

/** The action bar under the board: status, Match ID and the four fixed action slots. */
export const playControls = (page: Page): Locator => page.getByRole("region", { name: "Board play controls" });

async function ensureMenuOpen(menu: Locator) {
  const open = await menu.evaluate(element => (element as HTMLDetailsElement).open);
  if (!open) await menu.locator("summary").click();
}

/** Opens the action bar's "More" menu (if closed) and returns its item group. */
export async function openMore(page: Page): Promise<Locator> {
  const menu = playControls(page).locator("details.more-menu");
  await ensureMenuOpen(menu);
  return menu.getByRole("group", { name: "More" });
}

/** Opens the "More" menu (if closed) and clicks one of its items. */
export async function chooseMore(page: Page, name: string | RegExp) {
  const items = await openMore(page);
  await items.getByRole("button", { name, exact: typeof name === "string" }).click();
}

/** Opens the floating "Lounge tools" menu and returns it for assertions. */
export async function openLoungeTools(page: Page): Promise<Locator> {
  const menu = page.locator("details.lounge-tools");
  await ensureMenuOpen(menu);
  return menu;
}

/** Opens the "Lounge tools" menu and follows one of its links ("Model Lab" or "AI leaderboards"). */
export async function openToolsPage(page: Page, name: "Model Lab" | "AI leaderboards") {
  const menu = await openLoungeTools(page);
  await menu.getByRole("link", { name, exact: true }).click();
}
