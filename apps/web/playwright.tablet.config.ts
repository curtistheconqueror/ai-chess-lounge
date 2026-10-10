import { defineConfig, devices } from "@playwright/test";
import mobile from "./playwright.mobile.config";

export default defineConfig({
  ...mobile,
  outputDir: "./test-results-tablet",
  projects: (["chromium", "webkit"] as const).flatMap(browserName => [
    { name: "portrait", width: 820, height: 1180 },
    { name: "landscape", width: 1180, height: 820 },
  ].map(({ name, width, height }) => ({
    name: `${browserName}-ipad-${name}`,
    use: {
      ...devices["iPad (gen 7)"],
      browserName,
      channel: browserName === "chromium" ? process.env.LOUNGE_E2E_CHANNEL : undefined,
      viewport: { width, height },
      screen: { width, height },
    },
  }))),
});
