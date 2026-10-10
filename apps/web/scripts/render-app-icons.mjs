import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { chromium } from "@playwright/test";

const source = await readFile(new URL("../public/icons/lounge.svg", import.meta.url), "utf8");
const browser = await chromium.launch({ channel: process.env.LOUNGE_E2E_CHANNEL });
try {
  for (const [size, filename] of [[180, "apple-touch-icon.png"], [192, "lounge-192.png"], [512, "lounge-512.png"]]) {
    const page = await browser.newPage({ viewport: { width: size, height: size }, deviceScaleFactor: 1 });
    await page.setContent(`<style>html,body{margin:0;width:100%;height:100%}svg{display:block;width:100%;height:100%}</style>${source}`);
    await page.screenshot({ path: fileURLToPath(new URL(`../public/icons/${filename}`, import.meta.url)) });
    await page.close();
  }
} finally { await browser.close(); }
