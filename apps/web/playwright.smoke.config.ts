import { defineConfig, devices } from "@playwright/test";

// Aggressive smoke suite. Requires a disposable server: LOUNGE_E2E_BASE_URL=http://127.0.0.1:4176
// Select a project with --project, e.g. `--project=chromium-desktop`.
const base = process.env.LOUNGE_E2E_BASE_URL ?? "http://127.0.0.1:4176";
const sizes = {
  desktop: { width: 1440, height: 900 },
  laptop: { width: 1280, height: 720 },
  "ipad-portrait": { width: 820, height: 1180 },
  "ipad-landscape": { width: 1180, height: 820 },
  phone: { width: 390, height: 844 },
  "phone-small": { width: 320, height: 700 },
};
const projects = [] as any[];
for (const engine of ["chromium", "webkit"] as const) {
  for (const [name, viewport] of Object.entries(sizes)) {
    const touch = name.startsWith("ipad") || name.startsWith("phone");
    projects.push({
      name: `${engine}-${name}`,
      use: { browserName: engine, viewport, hasTouch: touch, isMobile: false, deviceScaleFactor: 1 },
    });
  }
}
// iPad emulation with real touch + iPad UA (webkit)
projects.push({ name: "webkit-ipad-touch", use: { ...devices["iPad (gen 7)"], browserName: "webkit" } });
projects.push({ name: "webkit-ipad-landscape-touch", use: { ...devices["iPad (gen 7) landscape"], browserName: "webkit" } });

export default defineConfig({
  testDir: "./e2e-smoke",
  outputDir: "./test-results-smoke",
  timeout: 90_000,
  expect: { timeout: 8_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: "list",
  use: { baseURL: base, colorScheme: "dark", trace: "off", actionTimeout: 6000, navigationTimeout: 20000 },
  projects,
});
