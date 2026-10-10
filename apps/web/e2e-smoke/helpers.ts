import { expect, type APIRequestContext, type Page, type Locator } from "@playwright/test";

/* ---------- API helpers (disposable server only) ---------- */
export async function finishAll(request: APIRequestContext) {
  // Next-match settings are shared server-side (Phase B); each test starts from the defaults.
  const current = await request.get("/api/table-settings");
  if (current.ok()) {
    const doc = await current.json();
    const defaults = { white_seat: "human", black_seat: "stockfish", stockfish: { mode: "elo", elo: 1600, skill_level: null }, time_control: "5+2", start_paused: false };
    if (JSON.stringify(doc.settings) !== JSON.stringify(defaults)) await request.put("/api/table-settings", { data: { revision: doc.revision, settings: defaults } });
  }
  for (let i = 0; i < 50; i++) {
    const live = await request.get("/api/live-match");
    if (live.status() === 404) return;
    const g = await live.json();
    await request.post(`/api/games/${g.id}/abort`);
  }
  throw new Error("could not clear table");
}
export async function createGame(request: APIRequestContext, data: Record<string, unknown> = {}) {
  await finishAll(request);
  const r = await request.post("/api/games", { data: { initial_time_ms: 3_600_000, ...data } });
  if (!r.ok()) throw new Error(`create failed ${r.status()} ${await r.text()}`);
  return await r.json();
}
export const getGame = async (request: APIRequestContext, id: string) => (await request.get(`/api/games/${id}`)).json();
export async function apiMove(request: APIRequestContext, id: string, move: string) {
  const g = await getGame(request, id);
  const r = await request.post(`/api/games/${id}/moves`, { data: { move, position_version: g.version } });
  if (!r.ok()) throw new Error(`move ${move} failed ${r.status()} ${await r.text()}`);
  return r.json();
}
export const hvh = (request: APIRequestContext, extra: Record<string, unknown> = {}) =>
  createGame(request, { opponent: "human", ...extra });
export const hvs = (request: APIRequestContext, extra: Record<string, unknown> = {}) =>
  createGame(request, { stockfish_elo: 1400, engine_move_time_ms: 100, ...extra });

/* ---------- Geometry / stability probes ---------- */
export async function installProbe(page: Page) {
  await page.addInitScript(() => {
    (window as any).__ls = [];
    try {
      new PerformanceObserver(list => {
        for (const e of list.getEntries() as any[]) (window as any).__ls.push({ v: e.value, in: e.hadRecentInput, t: Math.round(e.startTime) });
      }).observe({ type: "layout-shift", buffered: true });
    } catch { /* webkit has no layout-shift */ }
  });
}
export interface Box { x: number; y: number; w: number; h: number }
export interface Snap {
  scrollY: number; scrollX: number; docH: number; board: Box | null;
  buttons: Record<string, Box>; ls: number; lsEntries: number;
}
export async function snap(page: Page): Promise<Snap> {
  return page.evaluate(() => {
    const r = (e: Element) => { const b = e.getBoundingClientRect(); return { x: Math.round(b.x * 10) / 10, y: Math.round(b.y * 10) / 10, w: Math.round(b.width * 10) / 10, h: Math.round(b.height * 10) / 10 }; };
    const vis = (e: Element) => (e as any).checkVisibility ? (e as any).checkVisibility() : (e as HTMLElement).offsetParent !== null;
    const board = document.querySelector(".board");
    const buttons: Record<string, any> = {};
    const seen: Record<string, number> = {};
    document.querySelectorAll("button, summary, a[href], select, input").forEach(e => {
      if (!vis(e) || e.closest(".board")) return;
      let n = (e.getAttribute("aria-label") || (e as HTMLElement).innerText || e.textContent || "").trim().replace(/\s+/g, " ").slice(0, 40);
      if (!n) return;
      seen[n] = (seen[n] ?? 0) + 1; if (seen[n] > 1) n += `#${seen[n]}`;
      buttons[n] = r(e);
    });
    const ls = ((window as any).__ls ?? []).filter((x: any) => !x.in);
    return { scrollY: Math.round(window.scrollY), scrollX: Math.round(window.scrollX), docH: document.documentElement.scrollHeight,
      board: board ? r(board) : null, buttons, ls: ls.reduce((a: number, x: any) => a + x.v, 0), lsEntries: ls.length };
  });
}
export interface Delta { scrollY: number; boardViewport: number; boardDoc: number; moved: { name: string; dy: number; dx: number }[]; gone: string[]; appeared: string[]; layoutShift: number; docH: number }
/** Positions compared in DOCUMENT coordinates, so page scroll is reported separately from element relocation. */
export function diff(a: Snap, b: Snap, ignore: RegExp[] = []): Delta {
  const moved: Delta["moved"] = []; const gone: string[] = []; const appeared: string[] = [];
  for (const k of Object.keys(a.buttons)) {
    if (ignore.some(r => r.test(k))) continue;
    if (!b.buttons[k]) { gone.push(k); continue; }
    const dy = (b.buttons[k].y + b.scrollY) - (a.buttons[k].y + a.scrollY);
    const dx = b.buttons[k].x - a.buttons[k].x;
    if (Math.abs(dy) > 2 || Math.abs(dx) > 2) moved.push({ name: k, dy: Math.round(dy), dx: Math.round(dx) });
  }
  for (const k of Object.keys(b.buttons)) if (!a.buttons[k] && !ignore.some(r => r.test(k))) appeared.push(k);
  return {
    scrollY: b.scrollY - a.scrollY,
    boardViewport: a.board && b.board ? Math.round(b.board.y - a.board.y) : NaN,
    boardDoc: a.board && b.board ? Math.round((b.board.y + b.scrollY) - (a.board.y + a.scrollY)) : NaN,
    moved, gone, appeared, layoutShift: Math.round((b.ls - a.ls) * 1000) / 1000, docH: b.docH - a.docH,
  };
}
export async function measure(page: Page, action: () => Promise<unknown>, settleMs = 900) {
  const a = await snap(page);
  await action();
  await page.waitForTimeout(settleMs);
  const b = await snap(page);
  return { a, b, d: diff(a, b) };
}
export const controls = (page: Page) => page.getByRole("region", { name: "Board play controls" });
export async function openGame(page: Page, id: string) {
  await page.goto(`/games/${id}`);
  await page.locator(".board").waitFor();
  await expect(page.getByLabel(/^Connection live/)).toBeVisible({ timeout: 15_000 });
  await page.waitForTimeout(400);
}
export async function press(page: Page, l: Locator) {
  const touch = await page.evaluate(() => navigator.maxTouchPoints > 0);
  await l.scrollIntoViewIfNeeded();
  if (touch) await l.tap(); else await l.click();
}
export async function humanMove(page: Page, from: string, to: string) {
  const board = page.locator(".board");
  const s = board.locator(`[data-square="${from}"]`); const t = board.locator(`[data-square="${to}"]`);
  await s.scrollIntoViewIfNeeded();
  await press(page, s); await press(page, t);
}
export const fmt = (d: unknown) => JSON.stringify(d);
export const SCREENS = "test-results-smoke/screens";
export async function shot(page: Page, project: string, name: string) {
  await page.screenshot({ path: `${SCREENS}/${project}__${name}.png`, fullPage: false }).catch(() => {});
}
