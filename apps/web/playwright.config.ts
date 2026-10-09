import { defineConfig } from "@playwright/test";

const viewports = [
  { name: "desktop", width: 1440, height: 900 },
  { name: "small-desktop", width: 1024, height: 768 },
  { name: "tablet", width: 768, height: 1024 },
  { name: "phone", width: 390, height: 844 },
  { name: "minimum-phone", width: 320, height: 700 },
];

export default defineConfig({
  testDir: "./e2e",
  outputDir: "./test-results",
  timeout: 30_000,
  expect: { timeout: 8_000 },
  fullyParallel: false,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI
    ? [["list"], ["html", { open: "never", outputFolder: "playwright-report" }]]
    : "list",
  use: {
    baseURL: process.env.LOUNGE_E2E_BASE_URL ?? "http://127.0.0.1:4173",
    channel: process.env.LOUNGE_E2E_CHANNEL,
    launchOptions: { args: ["--autoplay-policy=document-user-activation-required"] },
    colorScheme: "dark",
    reducedMotion: "reduce",
    trace: "retain-on-failure",
  },
  projects: viewports.map(({ name, width, height }) => ({
    name,
    use: { viewport: { width, height } },
  })),
  webServer: process.env.LOUNGE_E2E_BASE_URL ? undefined : {
    command: process.env.CI
      ? "DATABASE_URL=sqlite+aiosqlite:////tmp/ai-chess-lounge-playwright.db python -m uvicorn lounge_api.main:app --app-dir ../../services/api --host 127.0.0.1 --port 4173"
      : "DATABASE_URL=sqlite+aiosqlite:////tmp/ai-chess-lounge-playwright.db ../../.venv/bin/python -m uvicorn lounge_api.main:app --app-dir ../../services/api --host 127.0.0.1 --port 4173",
    url: "http://127.0.0.1:4173/api/health",
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
  },
});
