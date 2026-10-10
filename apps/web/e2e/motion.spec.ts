import { expect, test, type Page, type WebSocketRoute } from "@playwright/test";
import { finishFixtureGames } from "./fixture-games";

test.use({ reducedMotion: "no-preference" });
test.beforeEach(async ({ page, request }) => {
  await finishFixtureGames(request);
  await page.addInitScript(() => localStorage.setItem("lounge.board-motion.v1", JSON.stringify({ duration: 500, buffer: 600 })));
});
async function create(page: Page, moves: string[] = []) {
  let game = await (await page.request.post("/api/games", { data: { opponent: "human", initial_time_ms: 3600000 } })).json();
  for (const uci of moves) game = await move(page, game.id, uci);
  await page.goto(`/games/${game.id}`);
  await expect(page.getByLabel("Connection live")).toBeVisible();
  return game;
}
async function move(page: Page, id: string, uci: string) {
  const current = await (await page.request.get(`/api/games/${id}`)).json();
  const response = await page.request.post(`/api/games/${id}/moves`, { data: { move: uci, position_version: current.version } });
  expect(response.ok()).toBeTruthy();
  return response.json();
}
const moving = (page: Page) => page.locator(".board");

for (const scenario of [
  { name: "capture", setup: ["e2e4", "d7d5"], move: "e4d5", squares: ["d5"], label: "d5 white pawn", pieces: 31 },
  { name: "castling", setup: ["e2e4", "e7e5", "g1f3", "b8c6", "f1c4", "g8f6"], move: "e1g1", squares: ["g1", "f1"], label: "g1 white king", pieces: 32 },
  { name: "en passant", setup: ["e2e4", "a7a6", "e4e5", "d7d5"], move: "e5d6", squares: ["d6"], label: "d6 white pawn", pieces: 31 },
  { name: "promotion capture", setup: ["a2a4", "h7h5", "a4a5", "h5h4", "a5a6", "h4h3", "a6b7", "h3g2"], move: "b7a8n", squares: ["a8"], label: "a8 white knight", pieces: 29 },
]) {
  test(`authoritative ${scenario.name} translates the expected pieces and settles`, async ({ page }) => {
    const game = await create(page, scenario.setup);
    await move(page, game.id, scenario.move);
    await expect(moving(page)).toHaveAttribute("data-animating", "true");
    const animated = await page.locator(".piece-motion").evaluateAll(nodes => nodes.filter(n => n.getAnimations().some(a => a.playState === "running")).map(n => n.parentElement!.dataset.square));
    expect(animated.sort()).toEqual([...scenario.squares].sort());
    await expect(moving(page)).toHaveAttribute("data-animating", "false");
    await expect(page.getByRole("gridcell", { name: scenario.label, exact: true })).toBeVisible();
    await expect(page.locator(".board .classic-piece")).toHaveCount(scenario.pieces);
    expect(await page.locator(".piece-motion").evaluateAll(nodes => nodes.flatMap(n => n.getAnimations()).length)).toBe(0);
  });
}

test("drag follows the pointer, sends one move and does not replay the dragged piece", async ({ page }) => {
  const game = await create(page);
  await moving(page).scrollIntoViewIfNeeded();
  const from = (await page.locator('[data-square="e2"]').boundingBox())!;
  const to = (await page.locator('[data-square="e4"]').boundingBox())!;
  let posts = 0;
  page.on("request", r => { if (r.method() === "POST" && r.url().endsWith("/moves")) posts++; });
  await page.mouse.move(from.x + from.width / 2, from.y + from.height / 2);
  await page.mouse.down();
  await page.mouse.move(to.x + to.width / 2, to.y + to.height / 2, { steps: 12 });
  const dragged = await page.locator('[data-square="e2"] .piece-motion').boundingBox();
  expect(Math.abs(dragged!.y - to.y)).toBeLessThan(2);
  expect(posts).toBe(0);
  await page.mouse.up();
  await expect(page.getByRole("gridcell", { name: "e4 white pawn" })).toBeVisible();
  await expect(moving(page)).toHaveAttribute("data-animating", "false");
  expect(posts).toBe(1);
  expect((await (await page.request.get(`/api/games/${game.id}`)).json()).moves).toHaveLength(1);
});

test("keyboard square activation plays once and restores input after translation", async ({ page }) => {
  const game = await create(page);
  await page.getByRole("gridcell", { name: "e2 white pawn" }).focus();
  await page.keyboard.press("Enter");
  await page.getByRole("gridcell", { name: "e4 empty" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("gridcell", { name: "e4 white pawn" })).toBeVisible();
  await expect(moving(page)).toHaveAttribute("data-animating", "false");
  await expect(page.getByRole("gridcell", { name: "e7 black pawn" })).toBeEnabled();
  expect((await (await page.request.get(`/api/games/${game.id}`)).json()).moves).toHaveLength(1);
});

test("rapid updates and abort cancel motion; reset and reconnect establish an instant baseline", async ({ page }) => {
  const game = await create(page);
  await move(page, game.id, "e2e4");
  await expect(moving(page)).toHaveAttribute("data-animating", "true");
  await move(page, game.id, "e7e5");
  await expect(page.getByRole("gridcell", { name: "e5 black pawn" })).toBeVisible();
  await expect(moving(page)).toHaveAttribute("data-animating", "false");
  await move(page, game.id, "g1f3");
  await expect(moving(page)).toHaveAttribute("data-animating", "true");
  await page.request.post(`/api/games/${game.id}/abort`);
  await expect(page.locator(".board-play-controls")).toContainText("Match aborted");
  await expect(moving(page)).toHaveAttribute("data-animating", "false");
  await page.reload();
  await expect(page.getByLabel("Connection live")).toBeVisible();
  await expect(moving(page)).toHaveAttribute("data-animating", "false");
  await page.getByRole("button", { name: "First position" }).click();
  await expect(page.getByRole("gridcell", { name: "e2 white pawn" })).toBeVisible();
  await expect(moving(page)).toHaveAttribute("data-animating", "false");
  await page.getByRole("button", { name: "Next move", exact: true }).click();
  await expect(moving(page)).toHaveAttribute("data-animating", "true");
  await page.getByRole("button", { name: "LIVE", exact: true }).click();
  await expect(moving(page)).toHaveAttribute("data-animating", "false");
  const fresh = await create(page);
  await move(page, fresh.id, "e2e4");
  await page.request.post(`/api/games/${fresh.id}/reset`);
  await expect(page.getByRole("gridcell", { name: "e2 white pawn" })).toBeVisible();
  await expect(moving(page)).toHaveAttribute("data-animating", "false");
});

test("automated buffer is visual only, bounded, persisted and respects reduced motion", async ({ page }) => {
  let socket: WebSocketRoute | undefined;
  await page.routeWebSocket("**/ws/games/**", ws => { socket = ws; });
  const game = await (await page.request.post("/api/games", { data: { opponent: "human", initial_time_ms: 3600000 } })).json();
  await page.goto(`/games/${game.id}`);
  await expect.poll(() => Boolean(socket)).toBe(true);
  socket!.send(JSON.stringify({ type: "snapshot", payload: game }));
  await expect(page.getByLabel("Connection live")).toBeVisible();
  const next = await move(page, game.id, "e2e4");
  // Presentation-only fixture: emulate an automated move without making provider calls.
  next.moves[0].player_metadata = { adapter_id: "scripted", latency_ms: 10, usage: {}, plan: "", threat: "" };
  next.can_move = false;
  socket!.send(JSON.stringify({ type: "snapshot", payload: next }));
  await expect(moving(page)).toHaveAttribute("data-animating", "true");
  const timing = await page.locator('[data-square="e4"] .piece-motion').evaluate(el => el.getAnimations()[0].effect!.getTiming());
  expect(timing.delay).toBe(600);
  expect(timing.duration).toBe(500);
  await expect(page.locator(".move-row")).toHaveCount(1); // History is already current.
  const actual = await (await page.request.get(`/api/games/${game.id}`)).json();
  expect(actual.version).toBe(next.version);
  expect(actual.moves).toHaveLength(1);
  await expect(moving(page)).toHaveAttribute("data-animating", "false");
  const reply = await move(page, game.id, "e7e5");
  reply.moves.at(-1).player_metadata = { adapter_id: "scripted", latency_ms: 10, usage: {}, plan: "", threat: "" };
  expect(reply.can_move).toBe(true);
  socket!.send(JSON.stringify({ type: "snapshot", payload: reply }));
  await expect(moving(page)).toHaveAttribute("data-animating", "true");
  expect(await page.locator('[data-square="e5"] .piece-motion').evaluate(el => el.getAnimations()[0].effect!.getTiming().delay)).toBe(0);
  await page.emulateMedia({ reducedMotion: "reduce" });
  await expect(moving(page)).toHaveAttribute("data-animating", "false");
  const last = await move(page, game.id, "g1f3");
  socket!.send(JSON.stringify({ type: "snapshot", payload: last }));
  await expect(page.getByRole("gridcell", { name: "f3 white knight" })).toBeVisible();
  await expect(moving(page)).toHaveAttribute("data-animating", "false");
  await page.locator("summary").filter({ hasText: "Board preferences" }).click();
  await page.getByLabel("Piece transition", { exact: true }).selectOption("150");
  await page.getByLabel("Automated move buffer").selectOption("0");
  expect(await page.evaluate(() => JSON.parse(localStorage.getItem("lounge.board-motion.v1")!))).toEqual({ duration: 150, buffer: 0 });
});

test("a reply mid-flight animates too, resumes the earlier piece where it was drawn, and input settles motion", async ({ page }) => {
  let socket: WebSocketRoute | undefined;
  await page.routeWebSocket("**/ws/games/**", ws => { socket = ws; });
  const game = await (await page.request.post("/api/games", { data: { opponent: "human", initial_time_ms: 3600000 } })).json();
  await page.goto(`/games/${game.id}`);
  await expect.poll(() => Boolean(socket)).toBe(true);
  socket!.send(JSON.stringify({ type: "snapshot", payload: game }));
  await expect(page.getByLabel("Connection live")).toBeVisible();
  const square = (await page.locator('[data-square="e4"]').boundingBox())!;
  const first = await move(page, game.id, "e2e4");
  socket!.send(JSON.stringify({ type: "snapshot", payload: first }));
  await page.waitForFunction(() => Number(document.querySelector('[data-square="e4"] .piece-motion')?.getAnimations()[0]?.currentTime ?? 0) >= 100);
  const second = await move(page, game.id, "e7e5");
  socket!.send(JSON.stringify({ type: "snapshot", payload: second }));
  await expect(page.getByRole("gridcell", { name: "e5 black pawn" })).toBeVisible();
  const flights = await page.locator(".piece-motion").evaluateAll(nodes => nodes.flatMap(n => n.getAnimations().map(a => ({
    square: n.parentElement!.dataset.square,
    duration: Number(a.effect!.getTiming().duration),
    start: String((a.effect as KeyframeEffect).getKeyframes()[0].transform),
  }))));
  expect(flights.map(f => f.square).sort()).toEqual(["e4", "e5"]);
  const resumed = flights.find(f => f.square === "e4")!;
  const startY = Number(/translate\([^,]+,\s*(-?[\d.]+)px\)/.exec(resumed.start)![1]);
  // Strictly inside the two-square path: it continues from mid-flight instead of restarting or snapping.
  expect(startY).toBeGreaterThan(0);
  expect(startY).toBeLessThan(2 * square.height - 1);
  expect(resumed.duration).toBeLessThan(500);
  // Touching the board is never blocked by decoration; it lands every piece at once.
  await expect(moving(page)).toHaveAttribute("data-animating", "true");
  await page.getByRole("gridcell", { name: "g1 white knight" }).click();
  await expect(moving(page)).toHaveAttribute("data-animating", "false");
  await expect(page.getByRole("gridcell", { name: "g1 white knight" })).toHaveClass(/selected/);
  expect(await page.locator(".piece-motion").evaluateAll(nodes => nodes.flatMap(n => n.getAnimations()).length)).toBe(0);
});

test("flip, resize and socket reconnection cancel stale visual positions", async ({ page }) => {
  const sockets: WebSocketRoute[] = [];
  await page.routeWebSocket("**/ws/games/**", ws => { sockets.push(ws); });
  const game = await (await page.request.post("/api/games", { data: { opponent: "human", initial_time_ms: 3600000 } })).json();
  await page.goto(`/games/${game.id}`);
  await expect.poll(() => sockets.length).toBe(1);
  sockets[0].send(JSON.stringify({ type: "snapshot", payload: game }));
  await expect(page.getByLabel("Connection live")).toBeVisible();
  const first = await move(page, game.id, "e2e4");
  sockets[0].send(JSON.stringify({ type: "snapshot", payload: first }));
  await expect(moving(page)).toHaveAttribute("data-animating", "true");
  await page.getByRole("button", { name: "Flip board" }).click();
  await expect(moving(page)).toHaveAttribute("data-animating", "false");
  const second = await move(page, game.id, "e7e5");
  sockets[0].send(JSON.stringify({ type: "snapshot", payload: second }));
  await expect(moving(page)).toHaveAttribute("data-animating", "true");
  const viewport = page.viewportSize()!;
  await page.setViewportSize({ width: viewport.width, height: viewport.height - 160 });
  await expect(moving(page)).toHaveAttribute("data-animating", "false");
  const third = await move(page, game.id, "g1f3");
  sockets[0].send(JSON.stringify({ type: "snapshot", payload: third }));
  await expect(moving(page)).toHaveAttribute("data-animating", "true");
  sockets[0].close();
  await expect(page.getByLabel("Connection offline")).toBeVisible();
  await expect(moving(page)).toHaveAttribute("data-animating", "false");
  const missed = await move(page, game.id, "b8c6");
  await expect.poll(() => sockets.length).toBe(2);
  sockets[1].send(JSON.stringify({ type: "snapshot", payload: missed }));
  await expect(page.getByLabel("Connection live")).toBeVisible();
  await expect(page.getByRole("gridcell", { name: "c6 black knight" })).toBeVisible();
  await expect(moving(page)).toHaveAttribute("data-animating", "false");
});
