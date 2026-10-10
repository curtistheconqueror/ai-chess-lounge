import { expect, test } from "@playwright/test";
import { controls, createGame, finishAll, fmt, getGame, humanMove, hvh, hvs, installProbe, measure, openGame, press, shot, snap, diff } from "./helpers";

test.beforeEach(async ({ page }) => { await installProbe(page); await finishAll(page.request); });
test.afterEach(async ({ request }) => { await finishAll(request); });

const note = (name: string, v: unknown) => test.info().annotations.push({ type: name, description: fmt(v) });
const pausePlayToggle = (page: import("@playwright/test").Page) =>
  controls(page).getByRole("button", { name: /^(Pause play|Resume play)$/ });

test("[S01] Pause then Resume never scrolls the page (scrollY unchanged)", async ({ page }, info) => {
  const g = await hvh(page.request);
  await openGame(page, g.id);
  const pause = await measure(page, () => press(page, controls(page).getByRole("button", { name: "Pause play" })));
  await shot(page, info.project.name, "paused");
  const resume = await measure(page, () => press(page, controls(page).getByRole("button", { name: "Resume play" })));
  note("pause", pause.d); note("resume", resume.d);
  expect.soft(pause.d.scrollY, `Pause moved scrollY by ${pause.d.scrollY} (App.tsx:881 scrollIntoView block:start)`).toBe(0);
  expect.soft(resume.d.scrollY, `Resume moved scrollY by ${resume.d.scrollY}`).toBe(0);
});

test("[S02] Pause and Resume share ONE fixed toggle location (button does not relocate)", async ({ page }) => {
  const g = await hvh(page.request);
  await openGame(page, g.id);
  const before = await pausePlayToggle(page).boundingBox();
  const scrollA = await page.evaluate(() => scrollY);
  await press(page, pausePlayToggle(page));
  await page.getByRole("button", { name: "Resume play" }).first().waitFor();
  await page.waitForTimeout(700);
  const after = await pausePlayToggle(page).boundingBox();
  const scrollB = await page.evaluate(() => scrollY);
  const docDy = (after!.y + scrollB) - (before!.y + scrollA);
  const docDx = after!.x - before!.x;
  note("toggle", { before, after, scrollA, scrollB, docDy, docDx });
  expect(Math.abs(docDy), `toggle moved ${docDy}px vertically (document coords)`).toBeLessThanOrEqual(2);
  expect(Math.abs(docDx), `toggle moved ${docDx}px horizontally`).toBeLessThanOrEqual(2);
  // viewport-relative: after the click, user's finger/cursor is still over the control
  expect(Math.abs(after!.y - before!.y), `toggle jumped ${after!.y - before!.y}px in the viewport`).toBeLessThanOrEqual(2);
});

test("[S03] Board does not move when pausing/resuming (document coords)", async ({ page }) => {
  const g = await hvh(page.request);
  await openGame(page, g.id);
  const p = await measure(page, () => press(page, controls(page).getByRole("button", { name: "Pause play" })));
  const r = await measure(page, () => press(page, controls(page).getByRole("button", { name: "Resume play" })));
  note("pause", { boardDoc: p.d.boardDoc, boardViewport: p.d.boardViewport }); note("resume", { boardDoc: r.d.boardDoc, boardViewport: r.d.boardViewport });
  expect.soft(Math.abs(p.d.boardDoc), `board moved ${p.d.boardDoc}px in document on Pause`).toBeLessThanOrEqual(2);
  expect.soft(Math.abs(r.d.boardDoc), `board moved ${r.d.boardDoc}px in document on Resume`).toBeLessThanOrEqual(2);
  expect.soft(Math.abs(p.d.boardViewport), `board moved ${p.d.boardViewport}px in viewport on Pause`).toBeLessThanOrEqual(2);
  expect.soft(Math.abs(r.d.boardViewport), `board moved ${r.d.boardViewport}px in viewport on Resume`).toBeLessThanOrEqual(2);
});

test("[S04] Playing a human move (human vs human) does not scroll or move the board", async ({ page }) => {
  const g = await hvh(page.request);
  await openGame(page, g.id);
  const m = await measure(page, () => humanMove(page, "e2", "e4"));
  await expect.poll(async () => (await getGame(page.request, g.id)).moves.length).toBe(1);
  note("move", m.d);
  const a = m.a, b = await snap(page);
  const d = diff(a, b);
  expect.soft(Math.abs(d.boardDoc), `board moved ${d.boardDoc}px in document`).toBeLessThanOrEqual(2);
  // measure() is taken after humanMove scrolled the board into view; compare scroll only post-action
  const m2 = await measure(page, () => humanMove(page, "e7", "e5"));
  note("move2", m2.d);
  expect.soft(m2.d.scrollY, `scrollY jumped ${m2.d.scrollY} on 2nd move`).toBe(0);
  expect.soft(Math.abs(m2.d.boardDoc), `board moved ${m2.d.boardDoc}px on 2nd move`).toBeLessThanOrEqual(2);
  expect.soft(m2.d.moved.filter(x => !/^\d|^Move|PLAY/i.test(x.name)), `controls relocated: ${fmt(m2.d.moved)}`).toEqual([]);
});

test("[S05] Human move + Stockfish reply: no scroll jump, board and controls hold still", async ({ page }) => {
  const g = await hvs(page.request);
  await openGame(page, g.id);
  await page.locator(".board").scrollIntoViewIfNeeded();
  const a = await snap(page);
  await humanMove(page, "e2", "e4");
  await expect.poll(async () => (await getGame(page.request, g.id)).moves.length, { timeout: 20_000 }).toBeGreaterThanOrEqual(2);
  await page.waitForTimeout(1200);
  const b = await snap(page);
  const d = diff(a, b);
  note("after-reply", { ...d, scrollA: a.scrollY, scrollB: b.scrollY });
  expect.soft(d.scrollY, `scrollY ${a.scrollY}->${b.scrollY}`).toBe(0);
  expect.soft(Math.abs(d.boardDoc), `board moved ${d.boardDoc}px (doc)`).toBeLessThanOrEqual(2);
  const rel = d.moved.filter(x => !/^(Next move|Previous move|First position|Replay position|MOVES|ANALYSIS|PGN|FEN)/.test(x.name));
  expect.soft(rel, `controls relocated after Stockfish reply: ${fmt(rel)}`).toEqual([]);
});

test("[S06] Pause/Resume during an engine game keeps the board put (Stockfish seat)", async ({ page }) => {
  const g = await hvs(page.request);
  await openGame(page, g.id);
  const p = await measure(page, () => press(page, controls(page).getByRole("button", { name: "Pause play" })));
  const r = await measure(page, () => press(page, controls(page).getByRole("button", { name: "Resume play" })));
  note("pause", p.d); note("resume", r.d);
  expect.soft(p.d.scrollY, `Pause scrollY ${p.d.scrollY}`).toBe(0);
  expect.soft(r.d.scrollY, `Resume scrollY ${r.d.scrollY}`).toBe(0);
  expect.soft(Math.abs(p.d.boardViewport), `Pause board viewport shift ${p.d.boardViewport}`).toBeLessThanOrEqual(2);
});

test("[S07] Scrolled to the board, Pause keeps scroll position (user scrolled down to board)", async ({ page }) => {
  const g = await hvh(page.request);
  await openGame(page, g.id);
  await page.evaluate(() => window.scrollTo(0, 120));
  await page.waitForTimeout(200);
  const y0 = await page.evaluate(() => scrollY);
  await press(page, controls(page).getByRole("button", { name: "Pause play" }));
  await page.waitForTimeout(800);
  const y1 = await page.evaluate(() => scrollY);
  note("scroll", { y0, y1 });
  expect(y1, `user scroll ${y0} became ${y1} after Pause`).toBe(y0);
});

test("[S08] Layout-shift score for a Pause/Resume cycle is under 0.02 (chromium only)", async ({ page, browserName }) => {
  test.skip(browserName !== "chromium", "layout-shift API is chromium-only");
  const g = await hvh(page.request);
  await openGame(page, g.id);
  const a = await snap(page);
  await press(page, controls(page).getByRole("button", { name: "Pause play" })); await page.waitForTimeout(700);
  await press(page, controls(page).getByRole("button", { name: "Resume play" })); await page.waitForTimeout(700);
  const b = await snap(page);
  note("cls", { delta: b.ls - a.ls, entries: b.lsEntries - a.lsEntries });
  expect(b.ls - a.ls).toBeLessThan(0.02);
});

test("[S09] End match / start new match: page does not jump (scrollY stable, no board reflow beyond the intended swap)", async ({ page }) => {
  const g = await hvh(page.request);
  await openGame(page, g.id);
  await press(page, controls(page).getByRole("button", { name: "End match…" }));
  const dlg = page.getByRole("dialog");
  await expect(dlg).toBeVisible();
  const a = await snap(page);
  await press(page, dlg.getByRole("button", { name: /^(End match|Confirm|Abort)/ }).first());
  await expect(controls(page)).toContainText(/Match aborted|Match finished/);
  await page.waitForTimeout(800);
  const b = await snap(page);
  const d = diff(a, b);
  note("end", d);
  expect.soft(Math.abs(d.boardDoc), `board moved ${d.boardDoc}px when the match ended`).toBeLessThanOrEqual(2);
  expect.soft(d.scrollY, `scrollY jumped ${d.scrollY} when the match ended`).toBe(0);
});

test("[S10] Starting a new match from the empty table does not move the page or board unexpectedly", async ({ page }) => {
  await page.goto("/");
  await page.locator(".board").waitFor();
  await expect(controls(page)).toContainText("Ready to start");
  await page.waitForTimeout(600);
  const a = await snap(page);
  await press(page, controls(page).getByRole("button", { name: "Play a new match" }));
  await expect(controls(page)).toContainText(/to move|Waiting for/, { timeout: 15_000 });
  await page.waitForTimeout(900);
  const b = await snap(page);
  const d = diff(a, b);
  note("new", d);
  expect.soft(d.scrollY, `scrollY ${a.scrollY}->${b.scrollY} on Play a new match`).toBe(0);
  expect.soft(Math.abs(d.boardDoc), `board moved ${d.boardDoc}px in doc on starting`).toBeLessThanOrEqual(2);
});

test("[S11] Board play-controls panel height is identical in every table state (no reflow of the board)", async ({ page }) => {
  const heights: Record<string, number> = {};
  const h = async () => { await page.waitForTimeout(500); return Math.round((await snap(page)).board!.y + (await page.evaluate(() => scrollY))); };
  await page.goto("/"); await page.locator(".board").waitFor();
  await page.waitForTimeout(500); heights.empty = await h();
  const g = await hvh(page.request);
  await openGame(page, g.id); heights.running = await h();
  await page.request.post(`/api/games/${g.id}/pause`); await page.reload(); await page.locator(".board").waitFor(); heights.paused = await h();
  await page.request.post(`/api/games/${g.id}/abort`); await page.reload(); await page.locator(".board").waitFor(); heights.ended = await h();
  note("boardTopByState", heights);
  const vals = Object.values(heights);
  expect(Math.max(...vals) - Math.min(...vals), `board top (document y) per state: ${fmt(heights)}`).toBeLessThanOrEqual(2);
});
