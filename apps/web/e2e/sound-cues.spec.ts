import { expect, test, type Page } from "@playwright/test";
import { expandedWorkspace } from "./workspace-fixture";
import { finishFixtureGames } from "./fixture-games";

declare global { interface Window { cueStarts: { rate: number; at: number }[] } }

test.beforeEach(async ({ request }) => { await finishFixtureGames(request); });

async function recordStarts(page: Page) {
  await page.addInitScript(() => {
    window.cueStarts = [];
    const Native = window.AudioContext;
    window.AudioContext = class extends Native {
      createBufferSource() {
        const source = super.createBufferSource();
        const start = source.start.bind(source);
        source.start = (when?: number, ...rest: number[]) => {
          window.cueStarts.push({ rate: source.playbackRate.value, at: (when ?? 0) - this.currentTime });
          start(when, ...rest);
        };
        return source;
      }
    };
  });
}

test("check, castle, capture and game-end cues are distinct taps of the selected wood; single-tap mode keeps one", async ({ page }) => {
  await recordStarts(page);
  const game = await (await page.request.post("/api/games", { data: { opponent: "human", initial_time_ms: 3_600_000 } })).json();
  await page.goto(`/games/${game.id}`);
  await expandedWorkspace(page);
  await expect(page.getByLabel("Connection live")).toBeVisible();
  await page.getByRole("button", { name: "Test sound", exact: true }).click();
  await expect.poll(() => page.evaluate(() => window.cueStarts.length)).toBe(1);
  const play = async (uci: string) => {
    const current = await (await page.request.get(`/api/games/${game.id}`)).json();
    const response = await page.request.post(`/api/games/${game.id}/moves`, { data: { move: uci, position_version: current.version } });
    expect(response.ok()).toBeTruthy();
  };
  const since = async (from: number) => page.evaluate(n => window.cueStarts.slice(n), from);
  const cue = async (uci: string, taps: number) => {
    const before = await page.evaluate(() => window.cueStarts.length);
    await play(uci);
    await expect.poll(() => page.evaluate(() => window.cueStarts.length)).toBe(before + taps);
    return since(before);
  };
  for (const uci of ["e2e4", "e7e5", "g1f3", "b8c6", "f1c4", "g8f6"]) await cue(uci, 1);
  const castle = await cue("e1g1", 2);
  expect(castle[1].at).toBeGreaterThan(0.05);
  const capture = await cue("f6e4", 1);
  expect(capture[0].rate).toBeLessThan(1);
  const check = await cue("c4f7", 2);
  expect(check[1].rate).toBeGreaterThan(1.2);
  await page.getByLabel("Varied cues").uncheck();
  const single = await cue("e8f7", 1); // Kxf7: capture, single tap when variety is off.
  expect(single[0].rate).toBe(1);
  await page.getByLabel("Varied cues").check();
  const before = await page.evaluate(() => window.cueStarts.length);
  // Resignation ends the game without a move: the end cue still sounds.
  const current = await (await page.request.get(`/api/games/${game.id}`)).json();
  const resigned = await page.request.post(`/api/games/${game.id}/resign`, { data: { color: "white", position_version: current.version } });
  expect(resigned.ok()).toBeTruthy();
  expect((await resigned.json()).status).not.toBe("active");
  await expect.poll(() => page.evaluate(() => window.cueStarts.length)).toBe(before + 2);
  expect((await since(before))[0].rate).toBeLessThan(1);
});
