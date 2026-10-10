import { expandedWorkspace } from "./workspace-fixture";
import { expect, test, type Page } from "@playwright/test";
import { pointerMove } from "./pointer-move";
import { finishFixtureGames } from "./fixture-games";
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import type { AddressInfo } from "node:net";

async function board(page: Page) {
  await finishFixtureGames(page.request);
  const response = await page.request.post("/api/games", { data: { opponent: "human", initial_time_ms: 3600000 } });
  expect(response.ok()).toBeTruthy();
  const game = await response.json();
  await page.goto(`/games/${game.id}`);
  await expandedWorkspace(page);
  await expect(page.getByLabel("Connection live")).toBeVisible();
  return game;
}

test("first-touch native audio plays one original tap", async ({ page, browserName }) => {
  test.skip(process.platform === "win32" && browserName === "webkit", "Bundled Windows WebKit has no AudioContext; verify in Linux WebKit and real Safari.");
  await page.addInitScript(() => {
    const probe = { contexts: [] as AudioContext[], starts: [] as number[] };
    Object.assign(window, { mobileAudio: probe });
    const Native = window.AudioContext;
    window.AudioContext = class extends Native {
      constructor() { super(); probe.contexts.push(this); }
      createBufferSource() {
        const source = super.createBufferSource();
        const start = source.start.bind(source);
        source.start = (...args: Parameters<AudioBufferSourceNode["start"]>) => {
          probe.starts.push(source.buffer?.duration ?? 0); start(...args);
        };
        return source;
      }
    };
  });
  await board(page);
  const square = (name: string) => page.locator(`[data-square="${name}"]`);
  await square("e2").tap();
  await expect(square("e4")).toHaveClass(/legal-target/);
  await expect(page.getByRole("status").filter({ hasText: "Sound enabled" })).toBeVisible();
  await square("e4").tap();
  await expect(square("e4")).toHaveAttribute("aria-label", "e4 white pawn");
  await expect.poll(() => page.evaluate(() => (window as any).mobileAudio.starts.length)).toBe(1);
  expect(await page.evaluate(() => (window as any).mobileAudio.contexts[0].state)).toBe("running");
  expect(await page.evaluate(() => (window as any).mobileAudio.starts[0])).toBeCloseTo(.2, 3);
});

test("mobile tap, pointer drag and large controls preserve legal play", async ({ page }, info) => {
  const game = await board(page);
  const square = (name: string) => page.locator(`[data-square="${name}"]`);
  await square("e2").tap();
  await expect(square("e4")).toHaveClass(/legal-target/);
  await square("e4").tap();
  await expect(square("e4")).toHaveAttribute("aria-label", "e4 white pawn");
  await pointerMove(page, "d7", "d5");
  await expect(square("d5")).toHaveAttribute("aria-label", "d5 black pawn");
  await page.locator(".square-entry summary").tap();
  await page.getByLabel("Move from square").selectOption("g1");
  await page.getByLabel("Move to square").selectOption("f3");
  await page.getByRole("button", { name: "Play move", exact: true }).tap();
  await expect(square("f3")).toHaveAttribute("aria-label", "f3 white knight");
  const current = await (await page.request.get(`/api/games/${game.id}`)).json();
  expect(current.moves.map((move: { uci: string }) => move.uci)).toEqual(["e2e4", "d7d5", "g1f3"]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBeTruthy();
  const small = await page.locator("button:not(.square), select, .square-entry summary").evaluateAll(elements =>
    elements.filter(el => el.getClientRects().length).filter(el => {
      const box = el.getBoundingClientRect(); return box.width < 43.9 || box.height < 43.9;
    }).map(el => el.getAttribute("aria-label") ?? el.textContent));
  expect(small).toEqual([]);
  await page.getByRole("grid").scrollIntoViewIfNeeded();
  await page.screenshot({ path: info.outputPath(`board-${info.project.name}.png`), fullPage: true });
  await page.screenshot({ path: info.outputPath(`viewport-${info.project.name}.png`) });
  await page.getByRole("grid").screenshot({ path: info.outputPath(`detail-${info.project.name}.png`) });
});

test("cancelled pointer and changed position do not submit a stale move", async ({ page }) => {
  const game = await board(page);
  const start = page.locator('[data-square="e2"]');
  await start.scrollIntoViewIfNeeded();
  const a = (await start.boundingBox())!;
  const b = (await page.locator('[data-square="e4"]').boundingBox())!;
  await page.mouse.move(a.x + a.width / 2, a.y + a.height / 2);
  await page.mouse.down();
  await page.mouse.move(b.x + b.width / 2, b.y + b.height / 2, { steps: 4 });
  await start.dispatchEvent("pointercancel", { pointerId: 1 });
  await page.mouse.up();
  expect((await (await page.request.get(`/api/games/${game.id}`)).json()).moves).toEqual([]);
  await page.mouse.move(a.x + a.width / 2, a.y + a.height / 2);
  await page.mouse.down();
  await page.mouse.move(b.x + b.width / 2, b.y + b.height / 2, { steps: 4 });
  await page.request.post(`/api/games/${game.id}/moves`, { data: { move: "d2d4", position_version: game.version } });
  await expect(page.locator('[data-square="d4"]')).toHaveAttribute("aria-label", "d4 white pawn");
  await page.mouse.up();
  const current = await (await page.request.get(`/api/games/${game.id}`)).json();
  expect(current.moves.map((move: { uci: string }) => move.uci)).toEqual(["d2d4"]);
});

test("foreground opens a fresh socket and resynchronizes before play", async ({ page }) => {
  let sockets = 0;
  page.on("websocket", () => { sockets += 1; });
  const game = await board(page);
  const before = sockets;
  await page.evaluate(() => {
    Object.defineProperty(document, "visibilityState", { configurable: true, get: () => "hidden" });
    document.dispatchEvent(new Event("visibilitychange"));
  });
  await expect(page.locator('[data-square="e2"]')).toBeDisabled();
  await page.request.post(`/api/games/${game.id}/moves`, { data: { move: "e2e4", position_version: game.version } });
  await page.evaluate(() => {
    Object.defineProperty(document, "visibilityState", { configurable: true, get: () => "visible" });
    document.dispatchEvent(new Event("visibilitychange"));
  });
  await expect.poll(() => sockets).toBeGreaterThan(before);
  await expect(page.getByLabel("Connection live")).toBeVisible();
  await expect(page.locator('[data-square="e4"]')).toHaveAttribute("aria-label", "e4 white pawn");
  await expect(page.locator('[data-square="d7"]')).toBeEnabled();
});

test("home-screen assets register and never cache match data", async ({ page }) => {
  await board(page);
  const manifest = await (await page.request.get("/manifest.webmanifest")).json();
  expect(manifest.display).toBe("standalone");
  expect(manifest.start_url).toBe("/");
  expect(manifest.icons.map((icon: { sizes: string }) => icon.sizes)).toEqual(["192x192", "512x512"]);
  for (const path of ["/icons/lounge-192.png", "/icons/lounge-512.png", "/icons/apple-touch-icon.png"]) {
    expect((await page.request.get(path)).headers()["content-type"]).toContain("image/png");
  }
  await expect(page.locator('meta[name="viewport"]')).toHaveAttribute("content", /viewport-fit=cover/);
  await page.evaluate(() => navigator.serviceWorker.ready);
  await expect.poll(() => page.evaluate(() => Boolean(navigator.serviceWorker.controller))).toBeTruthy();
  const cached = await page.evaluate(async () => {
    const cache = await caches.open("chess-lounge-offline-v1");
    return (await cache.keys()).map(request => new URL(request.url).pathname);
  });
  expect(cached).toEqual(["/offline.html"]);
});

test("actual host shutdown serves the generic offline page", async ({ page }) => {
  // Shut down a disposable server rather than use WebKit's network-emulation
  // switch, which aborts navigation before a service worker can handle it.
  const assets = new Map([
    ["/sw.js", ["application/javascript", await readFile("public/sw.js", "utf8")]],
    ["/offline.html", ["text/html", await readFile("public/offline.html", "utf8")]],
    ["/", ["text/html", '<meta name="viewport" content="width=device-width,initial-scale=1"><h1>Offline fixture</h1><script>navigator.serviceWorker.register("/sw.js")</script>']],
  ]);
  const server = createServer((request, response) => {
    const asset = assets.get(request.url ?? "/");
    response.writeHead(asset ? 200 : 404, { "Content-Type": asset?.[0] ?? "text/plain" });
    response.end(asset?.[1] ?? "Not found");
  });
  await new Promise<void>(resolve => server.listen(0, "127.0.0.1", resolve));
  const base = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
  try {
    await page.goto(base);
    await page.evaluate(() => navigator.serviceWorker.ready);
    await expect.poll(() => page.evaluate(() => Boolean(navigator.serviceWorker.controller))).toBeTruthy();
    server.closeAllConnections();
    await new Promise<void>(resolve => server.close(() => resolve()));
    await page.goto(`${base}/games/offline-check`);
    await expect(page.getByRole("heading", { name: "The board is offline" })).toBeVisible();
    await expect(page.getByText(/no offline moves are queued/)).toBeVisible();
  } finally { server.closeAllConnections(); server.close(); }
});
