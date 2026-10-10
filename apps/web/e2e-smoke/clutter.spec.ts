import { expect, test, type Page } from "@playwright/test";
import { apiMove, controls, createGame, finishAll, fmt, hvh, hvs, openGame, press, shot } from "./helpers";

test.beforeEach(async ({ request }) => { await finishAll(request); });
test.afterEach(async ({ request }) => { await finishAll(request); });
const note = (name: string, v: unknown) => test.info().annotations.push({ type: name, description: fmt(v) });

type State = "empty" | "running" | "engine" | "paused" | "ended";
async function enter(page: Page, state: State) {
  if (state === "empty") { await page.goto("/"); await page.locator(".board").waitFor(); await page.waitForTimeout(700); return; }
  const g = state === "engine" ? await hvs(page.request) : await hvh(page.request);
  if (state !== "engine") { await apiMove(page.request, g.id, "e2e4"); await apiMove(page.request, g.id, "e7e5"); }
  if (state === "paused") await page.request.post(`/api/games/${g.id}/pause`);
  if (state === "ended") await page.request.post(`/api/games/${g.id}/abort`);
  await page.goto(`/games/${g.id}`); await page.locator(".board").waitFor(); await page.waitForTimeout(900);
}
const STATES: State[] = ["empty", "running", "engine", "paused", "ended"];

/** Interactive controls (not board squares) intersecting the first viewport, collapsed disclosures NOT opened. */
const firstViewport = (page: Page) => page.evaluate(() => {
  const vis = (e: Element) => (e as any).checkVisibility({ checkVisibilityCSS: true });
  const items: string[] = [];
  document.querySelectorAll("button, summary, a[href], select, input").forEach(e => {
    if (e.closest(".board") || !vis(e)) return;
    const r = e.getBoundingClientRect();
    if (r.bottom <= 0 || r.top >= innerHeight || r.right <= 0 || r.left >= innerWidth) return;
    items.push(((e.getAttribute("aria-label") || (e as HTMLElement).innerText || e.tagName) as string).trim().replace(/\s+/g, " ").slice(0, 28));
  });
  return items;
});

for (const state of STATES) {
  test(`[S50-${state}] screenshot + first-viewport control budget (<=12 controls besides the board)`, async ({ page }, info) => {
    await enter(page, state);
    await shot(page, info.project.name, `state-${state}`);
    await page.screenshot({ path: `test-results-smoke/screens/${info.project.name}__state-${state}-full.png`, fullPage: true }).catch(() => {});
    const items = await firstViewport(page);
    note("controls-in-first-viewport", { n: items.length, items });
    expect(items.length, `${items.length} controls compete for the first viewport: ${items.join(" | ")}`).toBeLessThanOrEqual(12);
  });
}

for (const state of ["running", "engine", "paused", "ended", "empty"] as State[]) {
  test(`[S51-${state}] no horizontal overflow / sideways scroll`, async ({ page }) => {
    await enter(page, state);
    await page.evaluate(() => document.querySelectorAll("details").forEach(d => { (d as HTMLDetailsElement).open = true; }));
    await page.waitForTimeout(300);
    const m = await page.evaluate(() => {
      const offenders: string[] = [];
      document.querySelectorAll("body *").forEach(e => {
        const r = e.getBoundingClientRect();
        if (r.width && (e as any).checkVisibility?.() && (r.right > innerWidth + 1 || r.left < -1) && !e.closest(".board") && !e.closest("[style*='overflow']"))
          offenders.push(`${e.tagName.toLowerCase()}.${(e as HTMLElement).className?.toString().slice(0, 30)}[${Math.round(r.left)},${Math.round(r.right)}]`);
      });
      return { sw: document.documentElement.scrollWidth, iw: innerWidth, offenders: offenders.slice(0, 6) };
    });
    note("overflow", m);
    expect(m.sw, `scrollWidth ${m.sw} > innerWidth ${m.iw}; ${m.offenders.join(", ")}`).toBeLessThanOrEqual(m.iw);
  });
}

test("[S52] In a running game the whole board is visible without scrolling (chess.com parity)", async ({ page }) => {
  await enter(page, "running");
  const m = await page.evaluate(() => { const b = document.querySelector(".board")!.getBoundingClientRect(); return { top: Math.round(b.top), bottom: Math.round(b.bottom), size: Math.round(b.width), vh: innerHeight, vw: innerWidth }; });
  note("board-vs-viewport", m);
  expect(m.bottom, `board spans ${m.top}-${m.bottom}px in a ${m.vh}px viewport (${m.vw}px wide)`).toBeLessThanOrEqual(m.vh);
});

test("[S53] Board starts within the top 200px of the page in a running game (no tall header/ribbon/controls stack above it)", async ({ page }) => {
  await enter(page, "running");
  const top = await page.evaluate(() => Math.round(document.querySelector(".board")!.getBoundingClientRect().top + scrollY));
  note("board-top", top);
  expect(top, `board top at ${top}px`).toBeLessThanOrEqual(200);
});

test("[S54] Resign and Draw are reachable without opening any collapsed section (chess.com parity)", async ({ page }) => {
  await enter(page, "running");
  const visible = await page.evaluate(() => {
    const vis = (e: Element) => (e as any).checkVisibility({ checkVisibilityCSS: true });
    return [...document.querySelectorAll("button")].filter(vis).map(b => (b as HTMLElement).innerText.trim()).filter(t => /resign|draw/i.test(t));
  });
  note("visible-resign-draw", visible);
  expect(visible.length, "Resign/Draw live inside the collapsed 'Match actions & export' disclosure (App.tsx:1507-1521)").toBeGreaterThan(0);
});

test("[S55] 'Flip board' is within 160px of the board (not stranded in the page header)", async ({ page }) => {
  await enter(page, "running");
  const d = await page.evaluate(() => {
    const flip = [...document.querySelectorAll("button")].find(b => /flip board/i.test(b.textContent ?? ""))!.getBoundingClientRect();
    const board = document.querySelector(".board")!.getBoundingClientRect();
    return { flipY: Math.round(flip.top + scrollY), boardTop: Math.round(board.top + scrollY), gap: Math.round(board.top - flip.bottom) };
  });
  note("flip-distance", d);
  expect(Math.abs(d.gap), `Flip board is ${d.gap}px from the board`).toBeLessThanOrEqual(160);
});

test("[S56] The control panel above the board is short (<= 18 words) once a match is running", async ({ page }) => {
  await enter(page, "running");
  const words = (await controls(page).innerText()).split(/\s+/).filter(Boolean).length;
  note("panel-words", words);
  expect(words, `board play-controls panel has ${words} words`).toBeLessThanOrEqual(18);
});

test("[S57] Pause/Resume/End each appear exactly once (no duplicated actions) when disclosures are open", async ({ page }) => {
  await enter(page, "running");
  await page.evaluate(() => document.querySelectorAll("details").forEach(d => { (d as HTMLDetailsElement).open = true; }));
  await page.waitForTimeout(300);
  const labels = await page.evaluate(() => {
    const vis = (e: Element) => (e as any).checkVisibility({ checkVisibilityCSS: true });
    return [...document.querySelectorAll("button")].filter(vis).map(b => (b as HTMLElement).innerText.trim().replace(/\s+/g, " "));
  });
  const pauses = labels.filter(l => /^Pause (play|match)$/.test(l));
  const ends = labels.filter(l => /^(End match…|Abort match|End and start new…)$/.test(l));
  const sets = labels.filter(l => /^Seats & game setup/.test(l));
  note("dupes", { pauses, ends, sets });
  expect.soft(pauses.length, `pause duplicates: ${pauses}`).toBe(1);
  expect.soft(ends.length, `end/abort duplicates: ${ends}`).toBeLessThanOrEqual(2);
  expect.soft(sets.length, `setup shortcut duplicates: ${sets}`).toBe(1);
});

test("[S58] Touch targets of visible buttons are >= 40px tall on touch devices", async ({ page, hasTouch }) => {
  test.skip(!hasTouch, "touch only");
  await enter(page, "running");
  const small = await page.evaluate(() => {
    const vis = (e: Element) => (e as any).checkVisibility({ checkVisibilityCSS: true });
    return [...document.querySelectorAll("button, summary, a[href], select")].filter(e => vis(e) && !e.closest(".board")).map(e => ({ n: ((e as HTMLElement).innerText || e.getAttribute("aria-label") || "").trim().slice(0, 24), h: Math.round(e.getBoundingClientRect().height), w: Math.round(e.getBoundingClientRect().width) }))
      .filter(x => x.h < 40);
  });
  note("small-targets", small);
  expect(small, `small touch targets: ${fmt(small)}`).toEqual([]);
});

test("[S59] No console errors, page errors or failed API calls during a full play session", async ({ page }) => {
  const problems: string[] = [];
  page.on("console", m => { if (m.type() === "error") problems.push(`console: ${m.text().slice(0, 140)}`); });
  page.on("pageerror", e => problems.push(`pageerror: ${e.message.slice(0, 140)}`));
  page.on("response", r => { if (r.status() >= 400 && !/live-match/.test(r.url())) problems.push(`HTTP ${r.status()} ${r.request().method()} ${new URL(r.url()).pathname}`); });
  page.on("requestfailed", r => { if (!/ws\/|events/.test(r.url())) problems.push(`failed ${r.url().slice(0, 80)} ${r.failure()?.errorText}`); });
  await enter(page, "engine");
  await page.locator(".board [data-square='e2']").click(); await page.locator(".board [data-square='e4']").click();
  await page.waitForTimeout(2500);
  await press(page, controls(page).getByRole("button", { name: "Pause play" })); await page.waitForTimeout(600);
  await press(page, controls(page).getByRole("button", { name: "Resume play" })); await page.waitForTimeout(600);
  note("problems", problems);
  expect(problems).toEqual([]);
});

test("[S60] Dialog: Escape closes 'End match…' without ending it, and focus returns to the trigger", async ({ page }) => {
  await enter(page, "running");
  const trigger = controls(page).getByRole("button", { name: "End match…" });
  await press(page, trigger);
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  const focused = await page.evaluate(() => { const a = document.activeElement as HTMLElement; return a && a.tagName === "BUTTON" ? a.innerText.trim() : `<${a?.tagName}>`; });
  note("focus-after-escape", focused);
  expect(focused, `focus after Escape is ${focused}; it should return to the End match… button`).toMatch(/End match/);
  const live = await page.request.get("/api/live-match"); expect(live.ok()).toBe(true);
});

test("[S61] Keyboard: Tab never gets trapped (reaches the page's last control within 120 presses)", async ({ page, browserName, hasTouch }) => {
  test.skip(hasTouch && browserName === "webkit", "touch webkit has no tab focus");
  await enter(page, "running");
  const seen = new Set<string>();
  for (let i = 0; i < 120; i++) {
    await page.keyboard.press("Tab");
    seen.add(await page.evaluate(() => { const a = document.activeElement as HTMLElement; return a ? `${a.tagName}:${(a.getAttribute("aria-label") || a.innerText || "").slice(0, 20)}` : "none"; }));
  }
  note("tab-distinct", seen.size);
  expect(seen.size, "focus cycles among only a few elements (trap?)").toBeGreaterThan(8);
});

test("[S62] Replay: stepping back/forward and LIVE work, and the move list highlights the selected ply", async ({ page }) => {
  await enter(page, "running");
  await press(page, page.getByRole("button", { name: "Previous move" }));
  await expect(page.getByText(/LOCAL REPLAY/)).toBeVisible();
  await press(page, page.getByRole("button", { name: "LIVE", exact: true }));
  await expect(page.getByText(/LOCAL REPLAY/)).toHaveCount(0);
});
