import { expect, test } from "@playwright/test";
import { expandedWorkspace } from "./workspace-fixture";
import { finishFixtureGames } from "./fixture-games";

test("confirmed current Stockfish Elo reaches every viewer; cancel and stale confirmations change nothing", async ({ page, browser }) => {
  await finishFixtureGames(page.request);
  const original = await (await page.request.post("/api/games", { data: { stockfish_elo: 3100, initial_time_ms: 3600000 } })).json();
  const viewer = await browser.newPage({ baseURL: test.info().project.use.baseURL });
  await page.goto(`/games/${original.id}`);
  await viewer.goto(`/games/${original.id}`);
  await expandedWorkspace(page);
  await expect(page.getByLabel("Connection live")).toBeVisible();
  const edit = page.getByRole("group", { name: "Current black Stockfish" });
  await expect(edit.getByLabel("Current black strength", { exact: true })).toContainText("3100 target Elo");
  await edit.getByLabel("Current black proposed Elo").fill("1400");
  await edit.getByRole("button", { name: "Update current black Stockfish" }).click();
  await expect(page.getByRole("dialog")).toContainText("Update the current Stockfish Elo rating to 1400?");
  await page.getByRole("dialog").getByRole("button", { name: "Cancel", exact: true }).click();
  const cancelled = await (await page.request.get(`/api/games/${original.id}`)).json();
  expect(cancelled.revision).toBe(original.revision);
  expect(cancelled.lifecycle).toBe("running");
  expect(cancelled.black_player).toEqual(original.black_player);
  await edit.getByRole("button", { name: "Update current black Stockfish" }).click();
  await page.getByRole("button", { name: "Confirm strength update" }).click();
  await expect(viewer.getByRole("heading", { name: "Human vs Stockfish 1400", exact: true })).toBeVisible();
  await expect(edit.getByLabel("Current black strength", { exact: true })).toContainText("1400 target Elo");
  const changed = await (await page.request.get(`/api/games/${original.id}`)).json();
  expect(changed.fen).toBe(original.fen); expect(changed.moves).toEqual(original.moves);
  expect(changed.lifecycle).toBe("paused"); expect(changed.engine.target_elo).toBe(1400);
  await edit.getByLabel("Current black proposed Elo").fill("1500");
  await edit.getByRole("button", { name: "Update current black Stockfish" }).click();
  await viewer.request.post(`/api/games/${original.id}/resume`, { data: { expected_revision: changed.revision } });
  await expect(page.getByRole("dialog")).toHaveCount(0);
  const stale = await (await page.request.get(`/api/games/${original.id}`)).json();
  expect(stale.black_player.settings.target_elo).toBe(1400);
  await page.reload(); await expandedWorkspace(page);
  await expect(edit.getByLabel("Current black proposed Elo")).toHaveValue("1400");
  await expect(page.getByRole("group", { name: "Current white Stockfish" })).toHaveCount(0);
  await viewer.close();
});

test("native skill is a distinct persisted mode and current edits target one Stockfish seat", async ({ page, browser }) => {
  await finishFixtureGames(page.request);
  await page.goto("/"); await expandedWorkspace(page);
  await page.getByLabel("Stockfish strength mode", { exact: true }).selectOption("skill");
  const skill = page.getByLabel("Stockfish Skill Level", { exact: true });
  for (const value of ["-1", "21", "1.5"]) {
    await skill.fill(value);
    await expect(page.getByRole("group", { name: "Stockfish strength for next match" }).getByRole("alert")).toContainText("Skill Level from 0 to 20");
    await expect(page.getByRole("button", { name: "New match", exact: true })).toBeDisabled();
  }
  await skill.fill("3"); await page.reload(); await expandedWorkspace(page);
  await expect(skill).toHaveValue("3");
  await page.getByLabel("White seat", { exact: true }).selectOption("stockfish");
  await page.getByLabel("Start paused to review or advise before any agent call").check();
  const creation = page.waitForResponse(r => r.url().endsWith("/api/games") && r.request().method() === "POST");
  await page.getByRole("button", { name: "New match", exact: true }).click();
  const response = await creation; expect(response.ok()).toBe(true);
  const game = await response.json();
  expect(game.white_player.settings.skill_level).toBe(3); expect(game.black_player.settings.skill_level).toBe(3);
  const viewer = await browser.newPage({ baseURL: test.info().project.use.baseURL });
  await viewer.goto(`/games/${game.id}`);
  const white = page.getByRole("group", { name: "Current white Stockfish" });
  await white.getByLabel("Current white proposed Skill Level").fill("21");
  await expect(white.getByRole("button", { name: "Update current white Stockfish" })).toBeDisabled();
  for (const [mode, value, label] of [["skill", "0", "Stockfish skill 0"], ["full", "", "Stockfish full strength"], ["rated", "1400", "Stockfish 1400"]]) {
    await white.getByLabel("Current white strength mode").selectOption(mode);
    if (mode === "skill") await white.getByLabel("Current white proposed Skill Level").fill(value);
    if (mode === "rated") await white.getByLabel("Current white proposed Elo").fill(value);
    await white.getByRole("button", { name: "Update current white Stockfish" }).click();
    await page.getByRole("button", { name: "Confirm strength update" }).click();
    await expect(viewer.getByRole("heading", { name: `${label} vs Stockfish skill 3`, exact: true })).toBeVisible();
    const saved = await (await page.request.get(`/api/games/${game.id}`)).json();
    expect(saved.black_player).toEqual(game.black_player);
    expect(saved.fen).toBe(game.fen); expect(saved.moves).toEqual(game.moves);
    expect(saved.lifecycle).toBe("paused");
    if (mode !== "skill") expect(saved.white_player.settings.skill_level).toBeUndefined();
    else expect(saved.white_player.settings.full_strength).toBe(false);
  }
  await page.reload(); await expandedWorkspace(page);
  await expect(white.getByLabel("Current white proposed Elo")).toHaveValue("1400");
  await expect(page.getByLabel("Current black strength", { exact: true })).toContainText("Skill Level 3 (uncalibrated)");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: `test-results/skill-strength-${test.info().project.name}.png`, fullPage: true });
  await viewer.close();
});
