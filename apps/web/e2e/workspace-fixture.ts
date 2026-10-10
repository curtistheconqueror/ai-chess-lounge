import type { Page } from "@playwright/test";

/** Legacy feature suites exercise the expanded workspace. Disclosure keyboard,
 * focus, shortcut and collapsed-layout behavior are tested in workspace.spec.ts.
 * Setting the fixture state directly avoids unlocking audio before audio tests.
 */
export async function expandedWorkspace(page: Page) {
  await page.locator(".board").waitFor();
  await page.locator(".workspace-section, .lounge-tools").evaluateAll(sections => {
    sections.forEach(section => { (section as HTMLDetailsElement).open = true; });
  });
}
