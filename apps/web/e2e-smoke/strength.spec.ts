import { expect, test, type Page } from "@playwright/test";
import { controls, createGame, finishAll, fmt, getGame, openGame, press } from "./helpers";

test.beforeEach(async ({ page }) => { await finishAll(page.request); });
test.afterEach(async ({ request }) => { await finishAll(request); });
const note = (name: string, v: unknown) => test.info().annotations.push({ type: name, description: fmt(v) });

async function openSetup(page: Page) {
  const summary = page.locator("summary", { hasText: "Seats & game setup" }).first();
  const open = await summary.evaluate(e => (e.parentElement as HTMLDetailsElement).open);
  if (!open) await press(page, summary);
}
const nextElo = (page: Page) => page.getByLabel("Stockfish target Elo", { exact: true });
const lsKey = "ai-chess-lounge:stockfish-strength";
const cards = (page: Page) => page.locator(".player-card").allInnerTexts();

test("[S20] 'New match' is not offered while a match is live (otherwise it 409s and re-shows the OLD 3100 game)", async ({ page }) => {
  const g = await createGame(page.request, { stockfish_elo: 3100 });
  await page.goto("/");
  await page.locator(".board").waitFor();
  await expect(page.getByLabel(/^Connection live/)).toBeVisible();
  await openSetup(page);
  await nextElo(page).fill("1400");
  const statuses: number[] = [];
  page.on("response", r => { if (r.url().endsWith("/api/games") && r.request().method() === "POST") statuses.push(r.status()); });
  const btn = page.getByRole("button", { name: "New match", exact: true });
  const enabled = await btn.isEnabled();
  if (enabled) { await press(page, btn); await page.waitForTimeout(1500); }
  const live = await (await page.request.get("/api/live-match")).json();
  const shown = (await cards(page)).join(" | ");
  note("evidence", { buttonEnabledWhileLive: enabled, postStatuses: statuses, liveIsOldGame: live.id === g.id, boardStillShows3100: /3100/.test(shown) });
  expect(enabled, "New match button is enabled while a running match exists (App.tsx:1036 newMatchDisabled ignores game.lifecycle; button App.tsx:1345)").toBe(false);
  expect(statuses, "clicking it POSTs /api/games and gets a 409").not.toContain(409);
});

test("[S21] Changing next-match Elo while a match is live never leaves '3100' as the only visible strength without explanation", async ({ page }) => {
  await createGame(page.request, { stockfish_elo: 3100 });
  await page.goto("/");
  await page.locator(".board").waitFor();
  await expect(page.getByLabel(/^Connection live/)).toBeVisible();
  await openSetup(page);
  await nextElo(page).fill("1400");
  const btn = page.getByRole("button", { name: "New match", exact: true });
  if (await btn.isEnabled()) { await press(page, btn); await page.waitForTimeout(1200); }
  const heading = await page.locator("h2").filter({ hasText: /vs/ }).first().innerText().catch(() => "");
  const notice = await page.locator(".board-notice").innerText().catch(() => "");
  note("evidence", { heading, notice: notice.slice(0, 160) });
  // After "applying" 1400 the user must either see 1400 on the board or be told clearly why not, with a one-tap path.
  const ok = /1400/.test(heading) || /End and start new/i.test(notice) && (await page.getByRole("button", { name: /Use .*1400|Apply 1400|Switch to 1400/i }).count()) > 0;
  expect(ok, `heading="${heading}" notice="${notice.slice(0, 90)}…" - setting 1400 silently leaves the live 3100 game`).toBe(true);
});

test("[S22] Next-match Elo 1400 (after the old game ends) is sent to the API and shown on the board", async ({ page }) => {
  await page.goto("/");
  await page.locator(".board").waitFor();
  await openSetup(page);
  await nextElo(page).fill("1400");
  const created = page.waitForResponse(r => r.url().endsWith("/api/games") && r.request().method() === "POST");
  await press(page, page.getByRole("button", { name: "New match", exact: true }));
  const resp = await created; expect(resp.status()).toBe(201 === resp.status() ? 201 : 200);
  const game = await resp.json();
  const api = await getGame(page.request, game.id);
  expect(api.black_player.settings.target_elo).toBe(1400);
  expect(api.black_player.display_name).toBe("Stockfish 1400");
  await expect(page.locator(".player-card").filter({ hasText: "Stockfish 1400" })).toBeVisible();
  await expect(page.locator(".player-card").filter({ hasText: "1400 target Elo" })).toBeVisible();
  expect((await cards(page)).join(" ")).not.toMatch(/3100/);
});

test("[S23] Current-seat update 3100 -> 1400: API, board card, heading and a 2nd viewer all agree", async ({ page, browser }) => {
  const g = await createGame(page.request, { stockfish_elo: 3100 });
  const viewer = await browser.newPage({ baseURL: test.info().project.use.baseURL });
  await openGame(page, g.id); await openGame(viewer, g.id);
  await openSetup(page);
  const edit = page.getByRole("group", { name: "Current black Stockfish" });
  await edit.getByLabel("Current black proposed Elo").fill("1400");
  await press(page, edit.getByRole("button", { name: "Update current black Stockfish" }));
  await press(page, page.getByRole("button", { name: "Confirm strength update" }));
  await expect.poll(async () => (await getGame(page.request, g.id)).black_player.settings.target_elo).toBe(1400);
  const api = await getGame(page.request, g.id);
  await expect(page.locator(".player-card").filter({ hasText: "1400 target Elo" })).toBeVisible();
  await expect(viewer.locator(".player-card").filter({ hasText: "1400 target Elo" })).toBeVisible();
  const mine = (await cards(page)).join(" "), theirs = (await cards(viewer)).join(" ");
  note("evidence", { api: api.black_player.settings.target_elo, name: api.black_player.display_name, lifecycle: api.lifecycle });
  expect(mine).not.toMatch(/3100/); expect(theirs).not.toMatch(/3100/);
  expect(api.black_player.display_name).toBe("Stockfish 1400");
  await viewer.close();
});

test("[S24] Current-seat update with the confirmation dialog: Cancel changes nothing, and the match is not left paused without a visible Resume", async ({ page }) => {
  const g = await createGame(page.request, { stockfish_elo: 3100 });
  await openGame(page, g.id); await openSetup(page);
  const edit = page.getByRole("group", { name: "Current black Stockfish" });
  await edit.getByLabel("Current black proposed Elo").fill("2000");
  await press(page, edit.getByRole("button", { name: "Update current black Stockfish" }));
  await press(page, page.getByRole("dialog").getByRole("button", { name: "Cancel", exact: true }));
  expect((await getGame(page.request, g.id)).black_player.settings.target_elo).toBe(3100);
  await edit.getByLabel("Current black proposed Elo").fill("2000");
  await press(page, edit.getByRole("button", { name: "Update current black Stockfish" }));
  await press(page, page.getByRole("button", { name: "Confirm strength update" }));
  await expect.poll(async () => (await getGame(page.request, g.id)).black_player.settings.target_elo).toBe(2000);
  await expect(controls(page).getByRole("button", { name: "Resume play" })).toBeVisible();
  await expect(page.getByRole("dialog")).toHaveCount(0);
});

test("[S25] Skill Level and full strength for the next match reach the API seat config", async ({ page }) => {
  await page.goto("/"); await page.locator(".board").waitFor(); await openSetup(page);
  await page.getByLabel("Stockfish strength mode", { exact: true }).selectOption("skill");
  await page.getByLabel("Stockfish Skill Level", { exact: true }).fill("7");
  const created = page.waitForResponse(r => r.url().endsWith("/api/games") && r.request().method() === "POST");
  await press(page, page.getByRole("button", { name: "New match", exact: true }));
  const game = await (await created).json();
  expect(game.black_player.settings.skill_level).toBe(7);
  await expect(page.locator(".player-card").filter({ hasText: /Skill Level 7|skill 7/i })).toBeVisible();
  await page.request.post(`/api/games/${game.id}/abort`);
  await page.reload(); await page.locator(".board").waitFor(); await openSetup(page);
  await expect(page.getByLabel("Stockfish Skill Level", { exact: true })).toHaveValue("7");
  await page.getByLabel("Stockfish strength mode", { exact: true }).selectOption("full");
  const created2 = page.waitForResponse(r => r.url().endsWith("/api/games") && r.request().method() === "POST");
  await press(page, page.getByRole("button", { name: "New match", exact: true }));
  const g2 = await (await created2).json();
  expect(g2.black_player.settings.full_strength).toBe(true);
  await expect(page.locator(".player-card").filter({ hasText: /full strength/i })).toBeVisible();
});

test("[S26] Next-match strength persists across reload in the same browser", async ({ page }) => {
  await page.goto("/"); await page.locator(".board").waitFor(); await openSetup(page);
  await nextElo(page).fill("1850");
  await page.reload(); await page.locator(".board").waitFor(); await openSetup(page);
  await expect(nextElo(page)).toHaveValue("1850");
});

test("[S27] A second browser context (e.g. the iPad) sees the same default next-match strength as the first (not independent per-device)", async ({ page, browser }) => {
  await page.goto("/"); await page.locator(".board").waitFor(); await openSetup(page);
  await nextElo(page).fill("2200");
  const other = await browser.newContext({ baseURL: test.info().project.use.baseURL, viewport: { width: 1280, height: 720 } });
  const p2 = await other.newPage(); await p2.goto("/"); await p2.locator(".board").waitFor(); await openSetup(p2);
  const v = await nextElo(p2).inputValue();
  note("evidence", { firstDevice: 2200, secondDevice: v, storage: "localStorage per browser (StockfishStrength.tsx:25 stockfishChoiceKey, App.tsx:147-153)" });
  await other.close();
  expect(v, "next-match strength is per-browser localStorage only").toBe("2200");
});

test("[S28] The Elo slider and the number box stay in sync and the label never shows a stale value", async ({ page }) => {
  await page.goto("/"); await page.locator(".board").waitFor(); await openSetup(page);
  await nextElo(page).fill("3100");
  const slider = page.getByLabel("Stockfish Elo slider", { exact: true });
  await expect(slider).toHaveValue("3100");
  await slider.fill("1500");
  await expect(nextElo(page)).toHaveValue("1500");
  await page.getByLabel("Stockfish slider increments", { exact: true }).selectOption("25");
  await expect(nextElo(page)).toHaveValue("1500");
  await slider.fill("10");
  const v = Number(await nextElo(page).inputValue());
  expect(v).toBe(1320 + 10 * 25);
});

test("[S29] Out-of-range Elo (3200, stored from an older build) is flagged and recoverable after reload", async ({ page }) => {
  await page.addInitScript(([k]) => { if (!sessionStorage.getItem("seeded")) { localStorage.setItem(k, "3200"); sessionStorage.setItem("seeded", "1"); } }, [lsKey]);
  await page.goto("/"); await page.locator(".board").waitFor(); await openSetup(page);
  const newMatch = page.getByRole("button", { name: "New match", exact: true });
  const disabled = await newMatch.isDisabled();
  const alert = await page.getByRole("alert").first().innerText().catch(() => "");
  note("evidence", { stored: 3200, newMatchDisabled: disabled, alert });
  // Correct behaviour: either clamp to the supported range (3190) on load, or explain. Disabled + silent alert far below the fold = stuck.
  const value = Number(await nextElo(page).inputValue());
  expect(value, `stored 3200 is outside 1320-3190; field shows ${value}, New match disabled=${disabled}`).toBeLessThanOrEqual(3190);
});

test("[S30] Board shows a finished match's strength as ended, not as 'Current match' (aborted game vs next-match panel)", async ({ page }) => {
  const g = await createGame(page.request, { stockfish_elo: 3100 });
  await openGame(page, g.id);
  await page.request.post(`/api/games/${g.id}/abort`);
  await page.reload(); await page.locator(".board").waitFor(); await openSetup(page);
  const line = await page.locator(".stockfish-current").innerText();
  note("evidence", { line });
  expect(line, "an ended match is still labelled 'Current match … 3100 target Elo' in the next-match fieldset (StockfishStrength.tsx:89)").not.toMatch(/Current match: black: 3100/);
});
