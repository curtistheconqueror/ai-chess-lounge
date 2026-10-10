import { defineConfig, devices } from "@playwright/test";
import base from "./playwright.config";

export default defineConfig({
  ...base,
  testMatch: /mobile\.spec\.ts/,
  testIgnore: [],
  outputDir: "./test-results-mobile",
  use: { ...base.use, channel: undefined, launchOptions: {} },
  projects: (["chromium", "webkit"] as const).flatMap(browserName => [320, 390, 430].map(width => ({
    name: `${browserName}-${width}`,
    use: {
      ...devices[browserName === "webkit" ? "iPhone 13" : "Pixel 7"],
      browserName,
      channel: browserName === "chromium" ? process.env.LOUNGE_E2E_CHANNEL : undefined,
      launchOptions: { args: browserName === "chromium" ? ["--autoplay-policy=document-user-activation-required"] : [] },
      viewport: { width, height: 844 },
      screen: { width, height: 844 },
    },
  }))),
});
