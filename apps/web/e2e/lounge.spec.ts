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

test("a remote agent pairs once and becomes a selectable seat", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "desktop", "Remote pairing smoke runs once on desktop.");

  await page.getByLabel("Remote agent name").fill("Lounge Remote Bot");
  await page.getByLabel("Remote agent provider").fill("External Agent Host");
  await page.getByLabel("Remote agent model").fill("frontier-agent-v1");
  const pairingResponse = page.waitForResponse((response) =>
    response.url().endsWith("/api/runner-pairings") && response.request().method() === "POST"
  );
  await page.getByRole("button", { name: "Generate one-time pairing" }).click();
  const pairing = await (await pairingResponse).json() as {
    pairing_id: string;
    pairing_code: string;
    player: { player_id: string };
  };
  await expect(page.locator(".runner-pairing-code")).toContainText("PAIRING CODE");

  const claimed = await page.request.post(
    `/api/runner-pairings/${pairing.pairing_id}/claim`,
    { data: { pairing_code: pairing.pairing_code } },
  );
  expect(claimed.ok()).toBeTruthy();
  const credentials = await claimed.json() as { runner_token: string; signing_key: string };
  await page.getByRole("button", { name: "Refresh" }).click();
  await expect(page.getByLabel("White seat").locator('option[value="remote_runner"]')).toBeEnabled();
  await page.getByLabel("White seat").selectOption("remote_runner");
  await expect(page.getByLabel("White paired agent")).toContainText("Lounge Remote Bot");

  let submitted: Record<string, unknown> | undefined;
  await page.route("**/api/games", async (route) => {
    if (route.request().method() === "POST") {
      submitted = route.request().postDataJSON() as Record<string, unknown>;
      await route.fulfill({
        status: 422,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Remote runner payload captured by the UI test." }),
      });
      return;
    }
    await route.continue();
  });
  await page.getByRole("button", { name: "New match" }).click();
  await expect(page.getByRole("alert")).toContainText("Remote runner payload captured");
  expect(submitted).toMatchObject({
    white_player: {
      player_id: pairing.player.player_id,
      adapter_id: "remote_runner",
      display_name: "Lounge Remote Bot",
      provider: "External Agent Host",
      model: "frontier-agent-v1",
      connection_mode: "remote_runner",
      settings: { runner_id: pairing.player.player_id },
    },
  });
  expect(JSON.stringify(submitted)).not.toContain(credentials.runner_token);
  expect(JSON.stringify(submitted)).not.toContain(credentials.signing_key);
});

test("Codex subscription pairing discloses local auth and fixes the Open Agentic profile", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "desktop", "Subscription pairing smoke runs once on desktop.");

  await page.getByLabel("Runner connection type").selectOption("subscription_bridge");
  await page.getByLabel("Remote agent name").fill("Local Codex CLI");
  await page.getByLabel("Codex CLI model").fill("codex-cli-test-model");
  await expect(page.locator(".runner-subscription-disclosure")).toContainText("not uploaded to the Lounge");
  await expect(page.locator(".runner-subscription-disclosure")).toContainText("open_agentic");

  const pairingResponse = page.waitForResponse((response) =>
    response.url().endsWith("/api/runner-pairings") && response.request().method() === "POST"
  );
  await page.getByRole("button", { name: "Generate one-time pairing" }).click();
  const response = await pairingResponse;
  expect(response.ok()).toBeTruthy();
  const body = response.request().postDataJSON() as Record<string, unknown>;
  expect(body).toMatchObject({
    display_name: "Local Codex CLI",
    provider: "OpenAI",
    model: "codex-cli-test-model",
    connection_mode: "subscription_bridge",
    division: "open_agentic",
    effort: null,
    move_timeout_ms: 120_000,
  });

  const pairing = await response.json() as {
    pairing_id: string;
    pairing_code: string;
    player: {
      provider: string;
      model: string;
      connection_mode: string;
      effort: string | null;
      division: string;
    };
  };
  expect(pairing.player).toMatchObject({
    provider: "OpenAI",
    model: "codex-cli-test-model",
    connection_mode: "subscription_bridge",
    effort: null,
    division: "open_agentic",
  });
  const instructions = page.locator(".runner-subscription-instructions");
  await expect(instructions).toContainText(pairing.pairing_id);
  await expect(instructions).toContainText("lounge-subscription-bridge doctor --model MODEL");
  const runCommand = instructions.locator("code").nth(2);
  await expect(runCommand).toHaveText(
    `lounge-subscription-bridge run --pairing-id ${pairing.pairing_id} --model MODEL --authorize-next-match`,
  );
  const runCommandText = await runCommand.textContent();
  expect(runCommandText).not.toContain("codex-cli-test-model");
  expect(runCommandText).not.toContain(pairing.pairing_code);
  await expect(instructions).toContainText("pairing code is prompted locally");

  await page.setViewportSize({ width: 320, height: 700 });
  const mobileLayout = await page.evaluate(() => {
    const panel = document.querySelector<HTMLElement>(".runner-pairing-panel");
    const command = document.querySelector<HTMLElement>(".runner-subscription-instructions code:nth-of-type(3)");
    return {
      viewportWidth: document.documentElement.clientWidth,
      documentWidth: document.documentElement.scrollWidth,
      panelWidth: panel?.clientWidth ?? 0,
      panelScrollWidth: panel?.scrollWidth ?? 0,
      commandWidth: command?.clientWidth ?? 0,
      commandScrollWidth: command?.scrollWidth ?? 0,
    };
  });
  expect(mobileLayout.documentWidth).toBeLessThanOrEqual(mobileLayout.viewportWidth + 1);
  expect(mobileLayout.panelScrollWidth).toBeLessThanOrEqual(mobileLayout.panelWidth + 1);
  expect(mobileLayout.commandScrollWidth).toBeLessThanOrEqual(mobileLayout.commandWidth + 1);
});

test("paused automated turns expose an audited operator retry", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "desktop", "Recovery smoke runs once on desktop.");

  const created = await page.request.post("/api/games", {
    data: {
      opponent: "human",
      white_player: {
        adapter_id: "scripted",
        display_name: "Recovery Test Agent",
        provider: "Lounge Test Harness",
        model: "deterministic-v1",
        connection_mode: "local",
        division: "legal_assist",
        settings: { moves: ["a1a8"], spectator_delay_ms: 0 },
      },
      black_player: {
        adapter_id: "human",
        display_name: "Human Black",
        provider: "Human seat",
        model: "Manual input",
        connection_mode: "human",
        division: "legal_assist",
        settings: {},
      },
    },
  });
  expect(created.ok()).toBeTruthy();
  const game = await created.json() as { id: string };

  await expect.poll(async () => {
    const response = await page.request.get(`/api/games/${game.id}`);
    return (await response.json() as { lifecycle: string }).lifecycle;
  }).toBe("paused");

  await page.goto(`/games/${game.id}`);
  await expect(page.locator(".broadcast-ribbon")).toContainText("RECOVERY PAUSED");
  await page.getByRole("button", { name: "Retry agent turn" }).click();

  await expect.poll(async () => {
    const response = await page.request.get(`/api/games/${game.id}/events`);
    const events = await response.json() as Array<{ type: string }>;
    return events.filter((event) => event.type === "agent.retry_requested").length;
  }).toBe(1);
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

test("Claude and OpenAI can be configured as opposing provider seats", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "desktop", "Cross-provider setup smoke runs once on desktop.");

  const allEfforts = ["fast", "balanced", "deep", "maximum"];
  await page.route("**/api/player-adapters", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({
      protocol_version: "1.0",
      adapters: [
        {
          adapter_id: "openai",
          models: ["gpt-frontier-latest"],
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
          },
        },
        {
          adapter_id: "anthropic",
          models: ["claude-opus-5-5", "claude-sonnet-5-5", "claude-unavailable"],
          capabilities: {
            "claude-opus-5-5": {
              model: "claude-opus-5-5",
              selectable: true,
              availability: "configured_unverified",
              connection_mode: "direct_api",
              effort_levels: allEfforts,
              structured_output: true,
              credentials_required: true,
            },
            "claude-sonnet-5-5": {
              model: "claude-sonnet-5-5",
              selectable: true,
              availability: "configured_unverified",
              connection_mode: "direct_api",
              effort_levels: ["fast", "balanced", "deep"],
              structured_output: true,
              credentials_required: true,
            },
            "claude-unavailable": {
              model: "claude-unavailable",
              selectable: false,
              availability: "credentials_missing",
              connection_mode: "direct_api",
              effort_levels: allEfforts,
              structured_output: true,
              credentials_required: true,
            },
          },
        },
      ],
    }),
  }));

  let submitted: Record<string, unknown> | undefined;
  await page.route("**/api/games", async (route) => {
    if (route.request().method() === "POST") {
      submitted = route.request().postDataJSON() as Record<string, unknown>;
      await route.fulfill({
        status: 422,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Cross-provider payload captured by the UI test." }),
      });
      return;
    }
    await route.continue();
  });

  await page.reload();
  await expect(page.getByRole("grid", { name: "Chess board" })).toBeVisible();
  await expect(page.getByLabel("White seat").locator('option[value="anthropic"]')).toBeEnabled();

  await page.getByLabel("White seat").selectOption("anthropic");
  await page.getByLabel("White Claude model").selectOption("claude-opus-5-5");
  await page.getByLabel("White effort").selectOption("maximum");
  await expect(page.getByLabel("White Claude model").locator('option[value="claude-unavailable"]')).toHaveCount(0);

  await page.getByLabel("Black seat").selectOption("openai");
  await page.getByLabel("Black OpenAI model").selectOption("gpt-frontier-latest");
  await page.getByLabel("Black effort").selectOption("deep");
  await page.getByRole("button", { name: "New match" }).click();

  await expect(page.getByRole("alert")).toContainText("Cross-provider payload captured");
  expect(submitted).toMatchObject({
    white_player: {
      adapter_id: "anthropic",
      provider: "Anthropic",
      model: "claude-opus-5-5",
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
      model: "gpt-frontier-latest",
      connection_mode: "direct_api",
      effort: "deep",
      division: "legal_assist",
      settings: {
        move_timeout_ms: 20_000,
        spectator_delay_ms: 180,
      },
    },
  });
  expect(JSON.stringify(submitted).toLowerCase()).not.toContain("api_key");
  expect(JSON.stringify(submitted).toLowerCase()).not.toContain("authorization");
});

test("Gemini exposes model-specific effort and can face Claude", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "desktop", "Gemini provider setup smoke runs once on desktop.");

  const allEfforts = ["fast", "balanced", "deep", "maximum"];
  await page.route("**/api/player-adapters", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({
      protocol_version: "1.0",
      adapters: [
        {
          adapter_id: "google",
          models: ["gemini-3.8-flash", "gemini-3.5-flash", "gemini-unavailable"],
          capabilities: {
            "gemini-3.8-flash": {
              model: "gemini-3.8-flash",
              selectable: true,
              availability: "configured_unverified",
              connection_mode: "direct_api",
              effort_levels: ["fast", "balanced", "deep"],
              provider_effort_map: { fast: "low", balanced: "medium", deep: "high" },
              thinking_mode: "level",
              structured_output: true,
              credentials_required: true,
            },
            "gemini-3.5-flash": {
              model: "gemini-3.5-flash",
              selectable: true,
              availability: "configured_unverified",
              connection_mode: "direct_api",
              effort_levels: allEfforts,
              provider_effort_map: { fast: "minimal", balanced: "low", deep: "medium", maximum: "high" },
              thinking_mode: "level",
              structured_output: true,
              credentials_required: true,
            },
            "gemini-unavailable": {
              model: "gemini-unavailable",
              selectable: false,
              availability: "credentials_missing",
              connection_mode: "direct_api",
              effort_levels: allEfforts,
              structured_output: true,
              credentials_required: true,
            },
          },
        },
        {
          adapter_id: "anthropic",
          models: ["claude-opus-5-5"],
          capabilities: {
            "claude-opus-5-5": {
              model: "claude-opus-5-5",
              selectable: true,
              availability: "configured_unverified",
              connection_mode: "direct_api",
              effort_levels: allEfforts,
              structured_output: true,
              credentials_required: true,
            },
          },
        },
      ],
    }),
  }));

  let submitted: Record<string, unknown> | undefined;
  await page.route("**/api/games", async (route) => {
    if (route.request().method() === "POST") {
      submitted = route.request().postDataJSON() as Record<string, unknown>;
      await route.fulfill({
        status: 422,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Gemini payload captured by the UI test." }),
      });
      return;
    }
    await route.continue();
  });

  await page.reload();
  await expect(page.getByRole("grid", { name: "Chess board" })).toBeVisible();
  await expect(page.getByLabel("White seat").locator('option[value="google"]')).toBeEnabled();

  await page.getByLabel("White seat").selectOption("google");
  await page.getByLabel("White Gemini model").selectOption("gemini-3.8-flash");
  await expect(page.getByLabel("White effort").locator('option[value="maximum"]')).toHaveCount(0);
  await page.getByLabel("White effort").selectOption("deep");
  await expect(page.getByLabel("White Gemini model").locator('option[value="gemini-unavailable"]')).toHaveCount(0);

  await page.getByLabel("Black seat").selectOption("anthropic");
  await page.getByLabel("Black Claude model").selectOption("claude-opus-5-5");
  await page.getByLabel("Black effort").selectOption("maximum");
  await page.getByRole("button", { name: "New match" }).click();

  await expect(page.getByRole("alert")).toContainText("Gemini payload captured");
  expect(submitted).toMatchObject({
    white_player: {
      adapter_id: "google",
      provider: "Google",
      model: "gemini-3.8-flash",
      connection_mode: "direct_api",
      effort: "deep",
      division: "legal_assist",
      settings: {
        move_timeout_ms: 20_000,
        spectator_delay_ms: 180,
      },
    },
    black_player: {
      adapter_id: "anthropic",
      provider: "Anthropic",
      model: "claude-opus-5-5",
      connection_mode: "direct_api",
      effort: "maximum",
      division: "legal_assist",
      settings: {
        move_timeout_ms: 20_000,
        spectator_delay_ms: 180,
      },
    },
  });
  expect(JSON.stringify(submitted).toLowerCase()).not.toContain("api_key");
  expect(JSON.stringify(submitted).toLowerCase()).not.toContain("x-goog-api-key");
});

test("OpenRouter can face a local Ollama model without invented effort", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "desktop", "Open ecosystem setup smoke runs once on desktop.");

  await page.route("**/api/player-adapters", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({
      protocol_version: "1.0",
      adapters: [
        {
          adapter_id: "openrouter",
          models: ["openai/gpt-6.1-sol"],
          capabilities: {
            "openai/gpt-6.1-sol": {
              model: "openai/gpt-6.1-sol",
              selectable: true,
              availability: "configured_unverified",
              connection_mode: "direct_api",
              effort_levels: ["fast", "balanced", "deep", "maximum"],
              structured_output: true,
              credentials_required: true,
            },
          },
        },
        {
          adapter_id: "ollama",
          models: ["llama-chess:latest"],
          capabilities: {
            "llama-chess:latest": {
              model: "llama-chess:latest",
              selectable: true,
              availability: "configured_unverified",
              connection_mode: "local",
              effort_levels: [],
              structured_output: true,
              credentials_required: false,
            },
          },
        },
      ],
    }),
  }));

  let submitted: Record<string, unknown> | undefined;
  await page.route("**/api/games", async (route) => {
    if (route.request().method() === "POST") {
      submitted = route.request().postDataJSON() as Record<string, unknown>;
      await route.fulfill({
        status: 422,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Open ecosystem payload captured by the UI test." }),
      });
      return;
    }
    await route.continue();
  });

  await page.reload();
  await page.getByLabel("White seat").selectOption("openrouter");
  await page.getByLabel("White OpenRouter model").selectOption("openai/gpt-6.1-sol");
  await page.getByLabel("White effort").selectOption("deep");
  await page.getByLabel("Black seat").selectOption("ollama");
  await page.getByLabel("Black Ollama model").selectOption("llama-chess:latest");
  await expect(page.getByLabel("Black effort")).toBeDisabled();
  await expect(page.getByLabel("Black effort")).toHaveValue("");
  await page.getByRole("button", { name: "New match" }).click();

  await expect(page.getByRole("alert")).toContainText("Open ecosystem payload captured");
  expect(submitted).toMatchObject({
    white_player: {
      adapter_id: "openrouter",
      provider: "OpenRouter",
      model: "openai/gpt-6.1-sol",
      connection_mode: "direct_api",
      effort: "deep",
    },
    black_player: {
      adapter_id: "ollama",
      provider: "Ollama",
      model: "llama-chess:latest",
      connection_mode: "local",
      effort: null,
    },
  });
  expect(JSON.stringify(submitted).toLowerCase()).not.toContain("api_key");
  expect(JSON.stringify(submitted).toLowerCase()).not.toContain("base_url");
  expect(JSON.stringify(submitted).toLowerCase()).not.toContain("authorization");
});

test("runner authorization limits and revoke control", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "desktop", "Trust lifecycle runs once on desktop.");
  await page.goto("/");
  await page.getByLabel("Remote agent name").fill("Trust Control Bot");
  await page.getByLabel("Runner turn limit").fill("20");
  await page.getByLabel("Runner authorization minutes").fill("10");
  const pairingResponse = page.waitForResponse((response) =>
    response.url().endsWith("/api/runner-pairings") && response.request().method() === "POST"
  );
  await page.getByRole("button", { name: "Generate one-time pairing" }).click();
  const pairing = await (await pairingResponse).json();
  expect(pairing.player.settings.max_turns).toBe(20);
  expect(pairing.player.settings.match_ttl_ms).toBe(600000);
  const claimed = await page.request.post(`/api/runner-pairings/${pairing.pairing_id}/claim`, {
    data: { pairing_code: pairing.pairing_code },
  });
  const credentials = await claimed.json();
  await page.getByRole("button", { name: "Refresh", exact: true }).click();
  const revoke = page.getByRole("button", { name: "Revoke Trust Control Bot", exact: true });
  await expect(revoke).toBeVisible();
  await revoke.click();
  await expect(page.getByRole("alert")).toContainText("Runner access revoked");
  await expect(revoke).toHaveCount(0);
  const heartbeat = await page.request.post("/api/runner-sessions/heartbeat", {
    headers: { Authorization: `Bearer ${credentials.runner_token}` },
  });
  expect(heartbeat.status()).toBe(401);
  const audit = await page.request.get(`/api/runner-sessions/${credentials.session_id}/audit`);
  expect((await audit.json()).map((event: { kind: string }) => event.kind)).toEqual(["session.claimed", "session.revoked"]);
});

test("human seats support drag, confirmation, and reconnect", async ({ page, request }, testInfo) => {
  test.skip(!["desktop", "phone"].includes(testInfo.project.name), "Human acceptance on desktop and phone.");
  const created = await request.post("/api/games", { data: { opponent: "human" } });
  const game = await created.json();
  await page.goto(`/games/${game.id}`);
  const from = page.getByRole("gridcell", { name: "e2 white pawn" });
  const to = page.getByRole("gridcell", { name: "e4 empty" });
  await expect(from).toBeEnabled();
  if (testInfo.project.name === "desktop") await from.dragTo(to);
  else { await from.click(); await to.click(); }
  await expect(page.getByRole("gridcell", { name: "e4 white pawn" })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("gridcell", { name: "e4 white pawn" })).toBeEnabled();
  await expect(page.locator(".move-row").first()).toContainText("e4");
  await page.getByRole("button", { name: "Resign Black", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "Resign Black?" })).toBeVisible();
  await page.getByRole("button", { name: "Cancel", exact: true }).click();
  expect((await (await request.get(`/api/games/${game.id}`)).json()).status).toBe("active");
  await page.getByRole("button", { name: "Resign Black", exact: true }).click();
  await page.getByRole("button", { name: "Confirm resignation" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect.poll(async () => (await (await request.get(`/api/games/${game.id}`)).json()).result).toBe("1-0");
  await expect(page.getByRole("button", { name: "Resign Black", exact: true })).toBeDisabled();
});

test("promotion supports both colors, underpromotion, and keyboard cancel", async ({ page, request }, testInfo) => {
  test.skip(!["desktop", "phone"].includes(testInfo.project.name), "Promotion acceptance on desktop and phone.");
  let game = await (await request.post("/api/games", { data: { opponent: "human" } })).json();
  for (const move of ["a2a4", "h7h5", "a4a5", "h5h4", "a5a6", "h4h3", "a6b7", "h3g2"]) {
    const response = await request.post(`/api/games/${game.id}/moves`, { data: { move, position_version: game.version } });
    expect(response.ok()).toBeTruthy();
    game = await response.json();
  }
  await page.goto(`/games/${game.id}`);
  await page.getByRole("gridcell", { name: "b7 white pawn" }).click();
  await page.getByRole("gridcell", { name: "a8 black rook" }).click();
  await expect(page.getByRole("dialog", { name: "Choose your piece" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page.getByRole("gridcell", { name: "b7 white pawn" }).click();
  await page.getByRole("gridcell", { name: "a8 black rook" }).click();
  await page.getByRole("button", { name: "Promote to knight" }).click();
  await expect(page.getByRole("gridcell", { name: "a8 white knight" })).toBeVisible();
  await page.getByRole("gridcell", { name: "g2 black pawn" }).click();
  await page.getByRole("gridcell", { name: "h1 white rook" }).click();
  await page.getByRole("button", { name: "Promote to rook" }).click();
  await expect(page.getByRole("gridcell", { name: "h1 black rook" })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("gridcell", { name: "h1 black rook" })).toBeVisible();
});

test("announced repetition claim is durable without playing the intended move", async ({ page, request }, testInfo) => {
  test.skip(testInfo.project.name !== "desktop", "Draw acceptance runs once.");
  let game = await (await request.post("/api/games", { data: { opponent: "human" } })).json();
  for (const move of ["g1f3", "g8f6", "f3g1", "f6g8", "g1f3", "g8f6", "f3g1"]) {
    game = await (await request.post(`/api/games/${game.id}/moves`, { data: { move, position_version: game.version } })).json();
  }
  await page.goto(`/games/${game.id}`);
  await page.getByRole("button", { name: "Claim draw", exact: true }).click();
  await expect(page.getByLabel("Intended draw-claim move")).toHaveValue("f6g8");
  await page.getByRole("button", { name: "Confirm draw claim" }).click();
  await expect.poll(async () => (await (await request.get(`/api/games/${game.id}`)).json()).status).toBe("draw");
  await page.reload();
  await expect(page.getByRole("gridcell", { name: "f6 black knight" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Claim draw", exact: true })).toBeDisabled();
  const restored = await (await request.get(`/api/games/${game.id}`)).json();
  expect(restored.moves).toHaveLength(7);
  expect(restored.result).toBe("1/2-1/2");
});

test("paused seat takeover preserves the board and restores the human", async ({ page }, testInfo) => {
  test.skip(!["desktop", "phone"].includes(testInfo.project.name), "Takeover smoke on desktop and phone.");
  await page.getByLabel("Black seat").selectOption("human");
  await page.getByRole("button", { name: "New match" }).click();
  await page.getByRole("gridcell", { name: "e2 white pawn" }).click();
  await page.getByRole("gridcell", { name: "e4 empty" }).click();
  await expect(page.locator(".move-row").first()).toContainText("e4");
  await page.getByRole("button", { name: "Pause match", exact: true }).click();
  await expect(page.getByRole("button", { name: "Resume match", exact: true })).toBeVisible();
  await page.getByLabel("White seat").selectOption("scripted");
  await page.getByRole("button", { name: "Apply White seat" }).click();
  await expect(page.getByRole("dialog", { name: "Change white player?" })).toBeVisible();
  await page.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(page.getByRole("dialog")).not.toBeVisible();
  await page.getByRole("button", { name: "Apply White seat" }).click();
  await page.getByRole("button", { name: "Confirm seat change" }).click();
  await expect(page.locator(".player-card").filter({ hasText: "Deterministic White" })).toBeVisible();
  await expect(page.getByRole("gridcell", { name: "e4 white pawn" })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("button", { name: "Resume match", exact: true })).toBeVisible();
  await page.getByText("Seat history · 1 changes · exhibition", { exact: true }).click();
  await expect(page.locator(".seat-history ol")).toContainText("Deterministic White");
  await page.getByRole("button", { name: "Restore previous white player" }).click();
  await page.getByRole("button", { name: "Confirm seat change" }).click();
  await expect(page.locator(".seat-history summary")).toContainText("2 changes");
  const response = await page.request.get(`/api/games/${page.url().split("/").pop()}`);
  const game = await response.json();
  expect(game.moves).toHaveLength(1);
  expect(game.seat_history).toHaveLength(2);
  expect(game.pgn).toContain('[SeatChanges "2"]');
  expect(game.lifecycle).toBe("paused");
  await page.screenshot({ path: testInfo.outputPath(`takeover-${testInfo.project.name}.png`), fullPage: true, animations: "disabled" });
  await page.getByRole("button", { name: "Resume match", exact: true }).click();
  await page.getByRole("gridcell", { name: "e7 black pawn" }).click();
  await page.getByRole("gridcell", { name: "e5 empty" }).click();
  await expect(page.locator(".move-row").first()).toContainText("e5");
});

test("a concurrent lifecycle change dismisses a stale takeover dialog", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "desktop", "Revision smoke runs once on desktop.");
  await page.getByRole("button", { name: "Pause match", exact: true }).click();
  await page.getByRole("button", { name: "Apply White seat" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  const url = `/api/games/${page.url().split("/").pop()}`;
  const game = await (await page.request.get(url)).json();
  expect((await page.request.post(url + "/resume", { data: { expected_revision: game.revision } })).ok()).toBeTruthy();
  await expect(page.getByRole("dialog")).not.toBeVisible();
  await expect(page.getByRole("button", { name: "Pause match", exact: true })).toBeVisible();
});

test("human consultation suggests without moving and needs confirmation", async ({ page }, testInfo) => {
  test.skip(!["desktop", "phone"].includes(testInfo.project.name), "Consultation on desktop and phone.");
  await page.getByLabel("Black seat").selectOption("human");
  const created = page.waitForResponse(r => r.url().endsWith("/api/games") && r.request().method() === "POST");
  await page.getByRole("button", { name: "New match", exact: true }).click();
  await created;
  await page.getByLabel("Adviser model").selectOption("scripted:deterministic-v1");
  await page.getByRole("button", { name: "Request suggestion", exact: true }).click();
  await expect(page.getByRole("button", { name: "Review suggested move", exact: true })).toBeVisible();
  const url = `/api/games/${page.url().split("/").pop()}`;
  const advice = await (await page.request.get(url)).json();
  expect(advice.moves).toHaveLength(0);
  expect(advice.consultations[0].status).toBe("ready");
  expect(advice.pgn).toContain('Human-AI Team exhibition');
  await page.reload();
  await expect(page.getByRole("button", { name: "Review suggested move", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Review suggested move", exact: true }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(page.getByRole("dialog")).not.toBeVisible();
  await page.screenshot({ path: testInfo.outputPath(`consultation-${testInfo.project.name}.png`), fullPage: true, animations: "disabled" });
  await page.getByRole("button", { name: "Review suggested move", exact: true }).click();
  await page.getByRole("button", { name: "Confirm suggested move", exact: true }).click();
  await expect(page.locator(".move-row").first()).toBeVisible();
  const played = await (await page.request.get(url)).json();
  expect(played.moves).toHaveLength(1);
  expect(played.moves[0].actor).toBe("human:white");
  expect(played.consultations[0].status).toBe("played");
  await page.getByRole("button", { name: "Request suggestion", exact: true }).click();
  await expect(page.getByRole("button", { name: "Review suggested move", exact: true })).toBeVisible();
  const black = await (await page.request.get(url)).json();
  expect(black.consultations.at(-1).color).toBe("black");
  expect(black.moves).toHaveLength(1);
});

test("a human can ignore advice and stale confirmation closes", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "desktop", "Consultation race smoke runs on desktop.");
  await page.getByRole("button", { name: "Request suggestion", exact: true }).click();
  await expect(page.getByRole("button", { name: "Review suggested move", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Review suggested move", exact: true }).click();
  const url = `/api/games/${page.url().split("/").pop()}`;
  const game = await (await page.request.get(url)).json();
  expect((await page.request.post(url + "/pause", { data: { expected_revision: game.revision } })).ok()).toBeTruthy();
  await expect(page.getByRole("dialog")).not.toBeVisible();
  await expect(page.getByRole("button", { name: "Review suggested move", exact: true })).not.toBeVisible();
  await page.getByRole("button", { name: "Resume match", exact: true }).click();
  await page.getByRole("gridcell", { name: "e2 white pawn" }).click();
  await page.getByRole("gridcell", { name: "e4 empty" }).click();
  await expect(page.locator(".move-row").first()).toContainText("e4");
  const result = await (await page.request.get(url)).json();
  expect(result.consultations[0].status).toBe("stale");
  expect(result.moves[0].uci).toBe("e2e4");
});

test("Model Lab previews and saves a color-swapped plan without launching games", async ({ page }, testInfo) => {
  test.skip(!["desktop", "phone"].includes(testInfo.project.name), "Lab acceptance runs on desktop and phone.");
  const matchUrl = page.url();
  await page.getByRole("button", { name: "Model Lab", exact: true }).click();
  const lab = page.getByRole("region", { name: "Model Lab", exact: true });
  await lab.getByRole("textbox", { name: "Experiment name", exact: true }).fill(`Lab acceptance ${testInfo.project.name}`);
  await lab.getByRole("button", { name: "Preview experiment", exact: true }).click();
  const preview = lab.getByRole("article", { name: "Experiment preview", exact: true });
  await expect(preview).toContainText("6 planned games");
  await expect(preview.getByRole("row")).toHaveCount(7);
  await expect(preview).toContainText("Unsaved preview");
  const savedResponse = page.waitForResponse(r => r.url().endsWith("/api/experiments") && r.request().method() === "POST");
  await preview.getByRole("button", { name: "Save draft plan", exact: true }).click();
  const saved = await (await savedResponse).json();
  await expect(preview).toContainText("Saved draft");
  expect(page.url()).toBe(matchUrl);
  await page.reload();
  await page.getByRole("button", { name: "Model Lab", exact: true }).click();
  await lab.getByText(/Saved experiments ·/).click();
  await lab.getByRole("button", { name: `Lab acceptance ${testInfo.project.name} · 6 games`, exact: true }).last().click();
  await expect(preview).toContainText(saved.configuration_hash);
  const width = await page.evaluate(() => ({ client: document.documentElement.clientWidth, scroll: document.documentElement.scrollWidth }));
  expect(width.scroll).toBeLessThanOrEqual(width.client + 1);
  await page.screenshot({ path: testInfo.outputPath(`lab-${testInfo.project.name}.png`), fullPage: true, animations: "disabled" });
  await lab.getByRole("textbox", { name: "Opening suite" }).fill("Bad | e2e5");
  await expect(preview).not.toBeVisible();
  await lab.getByRole("button", { name: "Preview experiment", exact: true }).click();
  await expect(lab.getByRole("alert")).toBeVisible();
});
