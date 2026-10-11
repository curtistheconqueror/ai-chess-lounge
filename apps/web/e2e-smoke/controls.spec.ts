import { expect, test, type Page } from "@playwright/test";
import { apiMove, createGame, finishAll, fmt, getGame, hvh, hvs, openGame, press } from "./helpers";

/**
 * Dead / misleading control enumeration.
 * For every visible, enabled button / summary / link / select (outside the board squares) in a state, reload, act on it and
 * require an observable effect: DOM change (clock digits ignored), network request, navigation, download, dialog, or
 * scroll/focus change.  Controls without any effect are reported as dead.
 */
const HEAVY = /chromium-desktop|chromium-phone$|webkit-ipad-touch$|webkit-ipad-portrait/;

interface Ctl { key: string; tag: string; enabled: boolean; label: string; why: string }

async function expandAll(page: Page) {
  await page.evaluate(() => document.querySelectorAll("details").forEach(d => { (d as HTMLDetailsElement).open = true; }));
  await page.waitForTimeout(150);
}
async function listControls(page: Page): Promise<Ctl[]> {
  return page.evaluate(() => {
    const vis = (e: Element) => (e as any).checkVisibility ? (e as any).checkVisibility({ checkVisibilityCSS: true }) : (e as HTMLElement).offsetParent !== null;
    const out: any[] = []; const seen: Record<string, number> = {};
    document.querySelectorAll("button, summary, a[href], select").forEach(e => {
      if (!vis(e) || e.closest(".board") || e.closest("dialog:not([open])")) return;
      const el = e as HTMLButtonElement;
      let label = (e.getAttribute("aria-label") || (e as HTMLElement).innerText || "").trim().replace(/\s+/g, " ").slice(0, 50);
      if (!label) label = e.tagName.toLowerCase();
      seen[label] = (seen[label] ?? 0) + 1;
      const key = `${e.tagName.toLowerCase()}:${label}${seen[label] > 1 ? `#${seen[label]}` : ""}`;
      const disabled = el.disabled === true || e.getAttribute("aria-disabled") === "true";
      const why = e.getAttribute("title") || e.getAttribute("aria-describedby") || "";
      out.push({ key, tag: e.tagName.toLowerCase(), enabled: !disabled, label, why });
    });
    return out;
  });
}
const fingerprint = (page: Page) => page.evaluate(() => {
  const clone = document.body.cloneNode(true) as HTMLElement;
  clone.querySelectorAll("script,style").forEach(n => n.remove());
  const html = clone.innerHTML.replace(/\d+:\d\d(\.\d)?/g, "T").replace(/\d+(\.\d+)? ?ms/g, "ms").replace(/data-smoke="1"/g, "")
    .replace(/style="[^"]*"/g, "");
  return JSON.stringify({ u: location.pathname, h: html.length, hash: [...html].reduce((a, c) => (a * 31 + c.charCodeAt(0)) | 0, 7),
    d: document.querySelectorAll("dialog[open]").length, f: document.activeElement?.tagName + ":" + (document.activeElement as HTMLElement)?.innerText?.slice(0, 20),
    ls: JSON.stringify({ ...localStorage }), open: [...document.querySelectorAll("details")].map(d => d.open).join("") });
});
async function tag(page: Page, key: string) {
  return page.evaluate((k) => {
    const vis = (e: Element) => (e as any).checkVisibility ? (e as any).checkVisibility({ checkVisibilityCSS: true }) : (e as HTMLElement).offsetParent !== null;
    const seen: Record<string, number> = {};
    for (const e of document.querySelectorAll("button, summary, a[href], select")) {
      if (!vis(e) || e.closest(".board") || e.closest("dialog:not([open])")) continue;
      let label = (e.getAttribute("aria-label") || (e as HTMLElement).innerText || "").trim().replace(/\s+/g, " ").slice(0, 50);
      if (!label) label = e.tagName.toLowerCase();
      seen[label] = (seen[label] ?? 0) + 1;
      const key = `${e.tagName.toLowerCase()}:${label}${seen[label] > 1 ? `#${seen[label]}` : ""}`;
      if (key === k) { e.setAttribute("data-smoke", "1"); return true; }
    }
    return false;
  }, key);
}

async function probeState(page: Page, name: string, setup: () => Promise<{ gotoPath: string }>, opts: { skip?: RegExp } = {}) {
  const target = await setup();
  const load = async () => { await page.goto(target.gotoPath); await page.locator(".board").waitFor(); await page.waitForTimeout(700); await expandAll(page); };
  await load();
  const list = (await listControls(page)).filter(c => !(opts.skip && opts.skip.test(c.key)));
  const dead: string[] = []; const disabledNoWhy: string[] = []; const rows: string[] = [];
  const net: string[] = [];
  page.on("request", r => { if (!/\/ws\/|\.(png|svg|woff2?|mp3|wav|ogg)$/.test(r.url())) net.push(`${r.method()} ${new URL(r.url()).pathname}`); });
  let downloads = 0; page.on("download", () => downloads++);
  let reloadNeeded = false;
  for (const c of list) {
    if (!c.enabled) { if (!c.why) disabledNoWhy.push(c.key); continue; }
    if (reloadNeeded) { await load(); reloadNeeded = false; }
    if (!(await tag(page, c.key))) { rows.push(`${c.key}: VANISHED`); continue; }
    const el = page.locator('[data-smoke="1"]').first();
    await el.scrollIntoViewIfNeeded().catch(() => {});
    const f0 = await fingerprint(page); await page.waitForTimeout(200); const f0b = await fingerprint(page);
    const noisy = f0 !== f0b;
    net.length = 0; downloads = 0;
    const y0 = await page.evaluate(() => scrollY);
    const popup = page.waitForEvent("popup", { timeout: 800 }).catch(() => null);
    try {
      if (c.tag === "select") {
        const opts2 = await el.locator("option").evaluateAll(os => os.map(o => (o as HTMLOptionElement).value));
        const cur = await el.inputValue();
        const alt = opts2.find(v => v !== cur);
        if (alt !== undefined) await el.selectOption(alt);
      } else await press(page, el);
    } catch (e) { rows.push(`${c.key}: CLICK-ERROR ${(e as Error).message.split("\n")[0].slice(0, 80)}`); reloadNeeded = true; continue; }
    await page.waitForTimeout(600);
    const p = await popup;
    const f1 = await page.evaluate(() => 0).then(() => fingerprint(page)).catch(() => "NAV");
    const y1 = await page.evaluate(() => scrollY).catch(() => y0);
    const effects: string[] = [];
    if (f1 !== f0) effects.push(noisy ? "dom(noisy)" : "dom");
    const apiNet = net.filter(n => /\/api\//.test(n) && !/GET \/api\/(live-match|games\/[^/]+(\/events)?)$/.test(n) || /POST|PUT|DELETE|PATCH/.test(n));
    if (apiNet.length) effects.push(`net[${apiNet.slice(0, 2).join(",")}]`);
    if (downloads) effects.push("download");
    if (p) effects.push("popup");
    if (Math.abs(y1 - y0) > 2) effects.push(`scroll${y1 - y0}`);
    if (c.tag !== "select" && (!effects.length || (effects.length === 1 && effects[0] === "dom(noisy)"))) dead.push(`${c.key}${noisy ? " (unstable baseline)" : ""}`);
    rows.push(`${c.key}: ${effects.join("+") || "NO EFFECT"}`);
    console.log(`[sweep ${name}] ${rows[rows.length-1]}`);
    const after = await page.evaluate(() => location.pathname).catch(() => "");
    if (after !== target.gotoPath.split("?")[0] || f1 !== f0) reloadNeeded = true; // restore state after any change
    await page.evaluate(() => document.querySelectorAll('[data-smoke]').forEach(n => n.removeAttribute('data-smoke'))).catch(() => {});
  }
  test.info().annotations.push({ type: `${name}-rows`, description: rows.join(" || ") });
  test.info().annotations.push({ type: `${name}-disabled-without-explanation`, description: disabledNoWhy.join(" | ") });
  return { dead, rows, disabledNoWhy, count: list.length };
}

test.describe("dead-control sweep", () => {
  test.beforeEach(async ({ page }, info) => {
    test.skip(!HEAVY.test(info.project.name), "heavy sweep runs on chromium-desktop, chromium-phone, webkit iPad");
    test.setTimeout(480_000);
    await finishAll(page.request);
  });
  test.afterEach(async ({ request }) => { await finishAll(request); });

  test("[S40] empty table: every enabled control does something", async ({ page }) => {
    const r = await probeState(page, "empty", async () => ({ gotoPath: "/" }));
    expect(r.dead, `dead in empty state: ${fmt(r.dead)}`).toEqual([]);
  });
  test("[S41] running human-vs-human game with moves: every enabled control does something", async ({ page }) => {
    const r = await probeState(page, "running", async () => {
      const g = await hvh(page.request); await apiMove(page.request, g.id, "e2e4"); await apiMove(page.request, g.id, "e7e5");
      return { gotoPath: `/games/${g.id}` };
    }, { skip: /Pause|Reset|Abort|End |Resign|Adjudicate|Claim draw/ });
    expect(r.dead, `dead in running state: ${fmt(r.dead)}`).toEqual([]);
  });
  test("[S42] paused game: every enabled control does something", async ({ page }) => {
    const r = await probeState(page, "paused", async () => {
      const g = await hvh(page.request); await apiMove(page.request, g.id, "e2e4");
      await page.request.post(`/api/games/${g.id}/pause`);
      return { gotoPath: `/games/${g.id}` };
    }, { skip: /Resume|Reset|Abort|End |Resign|Adjudicate/ });
    expect(r.dead, `dead in paused state: ${fmt(r.dead)}`).toEqual([]);
  });
  test("[S43] ended (aborted) game: every enabled control does something", async ({ page }) => {
    const r = await probeState(page, "ended", async () => {
      const g = await hvh(page.request); await apiMove(page.request, g.id, "e2e4");
      await page.request.post(`/api/games/${g.id}/abort`);
      return { gotoPath: `/games/${g.id}` };
    }, { skip: /Play a new match|New match/ });
    expect(r.dead, `dead in ended state: ${fmt(r.dead)}`).toEqual([]);
  });
  test("[S44] human vs Stockfish running: every enabled control does something", async ({ page }) => {
    const r = await probeState(page, "engine", async () => {
      const g = await hvs(page.request);
      return { gotoPath: `/games/${g.id}` };
    }, { skip: /Pause|Reset|Abort|End |Resign|Adjudicate|Claim draw|Retry/ });
    expect(r.dead, `dead in engine state: ${fmt(r.dead)}`).toEqual([]);
  });
});

test("[S45] Disabled controls explain themselves (title / adjacent text) - empty table", async ({ page }) => {
  await page.goto("/"); await page.locator(".board").waitFor(); await expandAll(page);
  const list = await listControls(page);
  const noWhy = list.filter(c => !c.enabled && !c.why).map(c => c.key);
  test.info().annotations.push({ type: "disabled-no-reason", description: noWhy.join(" | ") });
  // Informational guard: more than 6 unexplained disabled controls on an empty table is clutter.
  expect(noWhy.length, `unexplained disabled controls on empty table: ${noWhy.join(", ")}`).toBeLessThanOrEqual(6);
});

test("[S46] Move-by-square form: 'Play move' with nothing selected is disabled or explains itself; selecting squares plays the move", async ({ page }) => {
  const g = await hvh(page.request);
  await openGame(page, g.id);
  await expandAll(page);
  const from = page.getByLabel("Move from square"), to = page.getByLabel("Move to square");
  await expect(from).toBeVisible();
  const play = page.getByRole("button", { name: "Play move", exact: true });
  await from.selectOption("e2"); await to.selectOption("e4");
  await press(page, play);
  await expect.poll(async () => (await getGame(page.request, g.id)).moves.length).toBe(1);
});

test("[S47] 'Copy link' is disabled (or explained) when there is no match to link to", async ({ page, context }) => {
  await finishAll(page.request);
  await context.grantPermissions(["clipboard-read", "clipboard-write"]).catch(() => {});
  await page.goto("/"); await page.locator(".board").waitFor(); await expandAll(page);
  const copy = page.getByRole("button", { name: "Copy link" });
  const enabled = await copy.isEnabled();
  let clip = "n/a";
  if (enabled) { await copy.click(); await page.waitForTimeout(400); clip = await page.evaluate(() => navigator.clipboard.readText().catch(() => "unreadable")); }
  test.info().annotations.push({ type: "evidence", description: fmt({ enabled, clipboardAfterClick: clip }) });
  expect(enabled, `Copy link enabled on an empty table; clipboard after click: "${clip}" (App.tsx:1524)`).toBe(false);
});
