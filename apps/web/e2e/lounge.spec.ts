import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("grid", { name: "Chess board" })).toBeVisible();
  await expect(page.getByRole("gridcell")).toHaveCount(64);
});

test("broadcast shell fits its viewport and captures a visual artifact", async ({ page }, testInfo) => {
  const dimensions = await page.evaluate(() => {
    const board = document.querySelector<HTMLElement>(".board");
    const rect = board?.getBoundingClientRect();
    return {
      clientWidth: document.documentElement.clientWidth,
      scrollWidth: document.documentElement.scrollWidth,
      boardWidth: rect?.width ?? 0,
      boardHeight: rect?.height ?? 0,
    };
  });

  expect(dimensions.scrollWidth).toBeLessThanOrEqual(dimensions.clientWidth + 1);
  expect(Math.abs(dimensions.boardWidth - dimensions.boardHeight)).toBeLessThanOrEqual(1);
  await expect(page.getByRole("button", { name: "Flip board" })).toBeVisible();
  await expect(page.getByRole("tab", { name: "ANALYSIS" })).toBeVisible();
  await expect(page.locator(".player-card")).toHaveCount(2);

  await page.screenshot({
    path: testInfo.outputPath(`lounge-${testInfo.project.name}.png`),
    fullPage: true,
    animations: "disabled",
  });
});

test("move, replay, analysis, and permalink flows remain coherent", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "desktop", "Interaction smoke runs once on desktop.");

  await page.getByRole("gridcell", { name: "e2 white pawn" }).click();
  await expect(page.getByRole("gridcell", { name: "e4 empty" })).toHaveClass(/legal-target/);
  await page.getByRole("gridcell", { name: "e4 empty" }).click();
  await expect(page.locator(".move-row").first()).toContainText("e4");
  await expect(page).toHaveURL(/\/games\/[A-Za-z0-9-]+$/);

  const playerCards = page.locator(".player-card");
  await expect(playerCards.nth(1)).toContainText("Human White");
  await page.getByRole("button", { name: "Flip board" }).click();
  await expect(playerCards.nth(0)).toContainText("Human White");

  await page.getByRole("button", { name: "First position" }).click();
  await expect(page.locator(".broadcast-ribbon")).toContainText("LOCAL REPLAY");
  await page.getByRole("button", { name: "LIVE" }).click();
  await expect(page.locator(".broadcast-ribbon")).not.toContainText("LOCAL REPLAY");

  await page.getByRole("tab", { name: "ANALYSIS" }).click();
  await expect(page.locator(".analysis-panel, .analysis-state")).toBeVisible();
});

test("two credential-free agents start an unattended match", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "desktop", "Automation smoke runs once on desktop.");

  await page.getByLabel("White seat").selectOption("scripted");
  await page.getByLabel("Black seat").selectOption("scripted");
  await page.getByRole("button", { name: "New match" }).click();

  await expect(page.locator(".move-row").first()).toBeVisible({ timeout: 10_000 });
  await expect(page.locator(".player-card")).toContainText([
    "Deterministic Black",
    "Deterministic White",
  ]);
  await expect(page.getByRole("grid", { name: "Chess board" })).toHaveAttribute(
    "aria-label",
    "Chess board",
  );
});

test("OpenAI seats use catalog models, selected effort, and only public settings", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "desktop", "Provider setup smoke runs once on desktop.");

  const allEfforts = ["fast", "balanced", "deep", "maximum"];
  await page.route("**/api/player-adapters", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({
      protocol_version: "1.0",
      adapters: [{
        adapter_id: "openai",
        models: ["gpt-frontier-latest", "gpt-compact-latest", "gpt-preview-unavailable"],
        capabilities: {
          "gpt-frontier-latest": {
            model: "gpt-frontier-latest",
            selectable: true,
            availability: "configured_unverified",
            connection_mode: "direct_api",
            effort_levels: allEfforts,
            structured_output: true,
            credentials_required: true,
          },
          "gpt-compact-latest": {
            model: "gpt-compact-latest",
            selectable: true,
            availability: "configured_unverified",
            connection_mode: "direct_api",
            effort_levels: ["fast", "deep"],
            structured_output: true,
            credentials_required: true,
          },
          "gpt-preview-unavailable": {
            model: "gpt-preview-unavailable",
            selectable: false,
            availability: "credentials_missing",
            connection_mode: "direct_api",
            effort_levels: allEfforts,
            structured_output: true,
            credentials_required: true,
          },
        },
      }],
    }),
  }));

  let submitted: Record<string, unknown> | undefined;
  await page.route("**/api/games", async (route) => {
    if (route.request().method() === "POST") {
      submitted = route.request().postDataJSON() as Record<string, unknown>;
      await route.fulfill({
        status: 422,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Provider setup payload captured by the UI test." }),
      });
      return;
    }
    await route.continue();
  });

  await page.reload();
  await expect(page.getByRole("grid", { name: "Chess board" })).toBeVisible();
  await expect(page.getByLabel("White seat").locator('option[value="openai"]')).toBeEnabled();
  await expect(page.getByLabel("Black seat").locator('option[value="openai"]')).toBeEnabled();

  await page.getByLabel("White seat").selectOption("openai");
  await page.getByLabel("White OpenAI model").selectOption("gpt-frontier-latest");
  await page.getByLabel("White effort").selectOption("maximum");
  await expect(page.getByLabel("White OpenAI model").locator('option[value="gpt-preview-unavailable"]')).toHaveCount(0);

  await page.getByLabel("Black seat").selectOption("openai");
  await page.getByLabel("Black OpenAI model").selectOption("gpt-compact-latest");
  await page.getByLabel("Black effort").selectOption("deep");
  await page.getByRole("button", { name: "New match" }).click();

  await expect(page.getByRole("alert")).toContainText("Provider setup payload captured");
  expect(submitted).toMatchObject({
    white_player: {
      adapter_id: "openai",
      provider: "OpenAI",
      model: "gpt-frontier-latest",
      connection_mode: "direct_api",
      effort: "maximum",
      division: "legal_assist",
      settings: {
        move_timeout_ms: 20_000,
        spectator_delay_ms: 180,
      },
    },
    black_player: {
      adapter_id: "openai",
      provider: "OpenAI",
      model: "gpt-compact-latest",
      connection_mode: "direct_api",
      effort: "deep",
      division: "legal_assist",
      settings: {
        move_timeout_ms: 20_000,
        spectator_delay_ms: 180,
      },
    },
  });
  for (const color of ["white_player", "black_player"]) {
    const player = submitted?.[color] as Record<string, unknown>;
    const settings = player.settings as Record<string, unknown>;
    expect(Object.keys(settings).sort()).toEqual([
      "move_timeout_ms",
      "spectator_delay_ms",
    ]);
  }
});
