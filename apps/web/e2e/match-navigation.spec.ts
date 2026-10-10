import { expect, test } from "@playwright/test";
import type { GameSnapshot } from "../src/types";
import { finishFixtureGames } from "./fixture-games";

test("connecting controls fit the viewport while moves remain disabled", async ({ page }) => {
  await finishFixtureGames(page.request);
  const response = await page.request.post("/api/games", { data: { opponent: "human" } });
  expect(response.ok()).toBeTruthy();
  const game = await response.json() as GameSnapshot;
  // Keep the connection pending instead of relying on a transient network delay.
  await page.routeWebSocket("**/ws/**", () => {});
  await page.goto(`/games/${game.id}`);
  await expect(page.locator(".match-header small")).toContainText("Match ");
  await expect(page.getByLabel("Connection connecting")).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(
    await page.evaluate(() => document.documentElement.clientWidth + 1),
  );
  await expect(page.getByRole("gridcell", { name: "e2 white pawn" })).toBeDisabled();
  await expect(page.getByRole("gridcell", { name: "e4 empty" })).not.toHaveClass(/legal-target/);
  await expect(page.locator(".move-row")).toHaveCount(0);
});

test("late updates from the previous match cannot replace a new match", async ({ page }) => {
  await finishFixtureGames(page.request);
  const response = await page.request.post("/api/games", {
    data: { opponent: "human", start_paused: true },
  });
  expect(response.ok()).toBeTruthy();
  const previous = await response.json() as GameSnapshot;
  // Retain real sockets so a queued event can be delivered after effect cleanup.
  await page.addInitScript(() => {
    const sockets: WebSocket[] = [];
    const NativeWebSocket = window.WebSocket;
    window.WebSocket = class extends NativeWebSocket {
      constructor(url: string | URL, protocols?: string | string[]) {
        super(url, protocols);
        sockets.push(this);
      }
    };
    Object.assign(window, { navigationTestSockets: sockets });
  });
  await page.goto(`/games/${previous.id}`);
  await expect(page.getByRole("gridcell")).toHaveCount(64);
  await expect(page.getByRole("button", { name: "Resume match", exact: true })).toBeEnabled();
  expect((await page.request.post(`/api/games/${previous.id}/abort`)).ok()).toBeTruthy();
  const created = page.waitForResponse(r => r.url().endsWith("/api/games") && r.request().method() === "POST");
  await page.getByRole("button", { name: "New match", exact: true }).click();
  const nextResponse = await created;
  expect(nextResponse.ok()).toBeTruthy();
  const next = await nextResponse.json() as GameSnapshot;
  await expect(page).toHaveURL(new RegExp(`/games/${next.id}$`));
  await page.evaluate(({ previousId, snapshot }) => {
    const sockets = (window as unknown as { navigationTestSockets: WebSocket[] }).navigationTestSockets;
    const oldSocket = sockets.find(socket => socket.url.includes(previousId));
    if (!oldSocket) throw new Error("Previous match socket was not captured");
    oldSocket.dispatchEvent(new MessageEvent("message", {
      data: JSON.stringify({ type: "snapshot", payload: snapshot }),
    }));
    oldSocket.dispatchEvent(new Event("error"));
  }, { previousId: previous.id, snapshot: previous });
  await expect(page).toHaveURL(new RegExp(`/games/${next.id}$`));
  expect(await page.evaluate(() => localStorage.getItem("ai-chess-lounge:active-game"))).toBe(next.id);
  // The new socket and move path must still work after rejecting the old events.
  await page.getByRole("gridcell", { name: "e2 white pawn" }).click();
  await page.getByRole("gridcell", { name: "e4 empty" }).click();
  await expect(page.locator(".move-row").first()).toContainText("e4");
  await expect(page).toHaveURL(new RegExp(`/games/${next.id}$`));
});
