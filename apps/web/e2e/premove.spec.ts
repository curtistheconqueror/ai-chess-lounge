import { expect, test, type Page, type WebSocketRoute } from "@playwright/test";
import { finishFixtureGames } from "./fixture-games";

test.beforeEach(async ({ request }) => { await finishFixtureGames(request); });

// Presentation fixture: a real human-vs-human game whose Black seat is shown as an automated
// player, so the board sees "opponent is thinking" without any provider or engine calls.
function asAutomatedBlack(snapshot: Record<string, any>) {
  snapshot.black_player = { ...snapshot.black_player, adapter_id: "scripted", display_name: "Scripted reply" };
  snapshot.can_move = snapshot.turn === "white";
  return snapshot;
}

async function setup(page: Page) {
  let socket: WebSocketRoute | undefined;
  await page.routeWebSocket("**/ws/games/**", ws => { socket = ws; });
  const game = await (await page.request.post("/api/games", { data: { opponent: "human", initial_time_ms: 3_600_000 } })).json();
  await page.goto(`/games/${game.id}`);
  await expect.poll(() => Boolean(socket)).toBe(true);
  const send = (snapshot: Record<string, any>) => socket!.send(JSON.stringify({ type: "snapshot", payload: asAutomatedBlack(snapshot) }));
  send(game);
  await expect(page.getByLabel("Connection live")).toBeVisible();
  const move = async (uci: string) => {
    const current = await (await page.request.get(`/api/games/${game.id}`)).json();
    return (await page.request.post(`/api/games/${game.id}/moves`, { data: { move: uci, position_version: current.version } })).json();
  };
  const moves = async () => (await (await page.request.get(`/api/games/${game.id}`)).json()).moves.map((m: { uci: string }) => m.uci);
  send(await move("e2e4"));
  await expect(page.getByRole("gridcell", { name: "e4 white pawn" })).toBeVisible();
  return { send, move, moves };
}

test("premove queues during the opponent's turn and plays when the turn arrives", async ({ page }) => {
  const { send, move, moves } = await setup(page);
  await page.getByRole("gridcell", { name: "g1 white knight" }).click();
  await page.getByRole("gridcell", { name: "f3 empty" }).click();
  await expect(page.locator('[data-square="f3"]')).toHaveClass(/premove/);
  await expect(page.locator('[data-square="g1"]')).toHaveClass(/premove/);
  await expect(page.getByRole("gridcell", { name: "f3 white knight" })).toBeVisible();
  expect(await moves()).toEqual(["e2e4"]);
  send(await move("e7e5"));
  await expect.poll(moves).toEqual(["e2e4", "e7e5", "g1f3"]);
  await expect(page.getByRole("gridcell", { name: "f3 white knight" })).toBeVisible();
  await expect(page.locator(".square.premove")).toHaveCount(0);
});

test("dragged premove that becomes illegal is dropped without a request", async ({ page }) => {
  const { send, move, moves } = await setup(page);
  let posts = 0;
  page.on("request", r => { if (r.method() === "POST" && r.url().endsWith("/moves")) posts++; });
  const from = (await page.locator('[data-square="e4"]').boundingBox())!;
  const to = (await page.locator('[data-square="e5"]').boundingBox())!;
  await page.mouse.move(from.x + from.width / 2, from.y + from.height / 2);
  await page.mouse.down();
  await page.mouse.move(to.x + to.width / 2, to.y + to.height / 2, { steps: 8 });
  await page.mouse.up();
  await expect(page.locator('[data-square="e5"]')).toHaveClass(/premove/);
  send(await move("e7e5")); // Blocks the pawn: e4e5 is no longer legal.
  await expect(page.getByRole("gridcell", { name: "e5 black pawn" })).toBeVisible();
  await expect(page.locator(".square.premove")).toHaveCount(0);
  await page.waitForTimeout(400);
  expect(posts).toBe(0);
  expect(await moves()).toEqual(["e2e4", "e7e5"]);
  await expect(page.getByRole("gridcell", { name: "e4 white pawn" })).toBeVisible();
});

test("Escape, right-click and tapping again cancel a premove", async ({ page }) => {
  const { send, move, moves } = await setup(page);
  const queue = async () => {
    await page.getByRole("gridcell", { name: "g1 white knight" }).click();
    await page.getByRole("gridcell", { name: "f3 empty" }).click();
    await expect(page.locator(".square.premove")).toHaveCount(2);
  };
  await queue();
  await page.keyboard.press("Escape");
  await expect(page.locator(".square.premove")).toHaveCount(0);
  await expect(page.getByRole("gridcell", { name: "g1 white knight" })).toBeVisible();
  await queue();
  await page.locator('[data-square="d4"]').click({ button: "right" });
  await expect(page.locator(".square.premove")).toHaveCount(0);
  await queue();
  await page.getByRole("gridcell", { name: "a3 empty" }).click();
  await expect(page.locator(".square.premove")).toHaveCount(0);
  send(await move("e7e5"));
  await page.waitForTimeout(400);
  expect(await moves()).toEqual(["e2e4", "e7e5"]);
});
