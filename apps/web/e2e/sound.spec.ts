import { expect, test, type Page, type WebSocketRoute } from "@playwright/test";

type Probe = {
  starts: { duration: number; peak: number; rms: number; gain: number }[];
  contexts: AudioContext[];
  gains: GainNode[];
  outputPeak: number;
  active: number;
  maxActive: number;
};
declare global { interface Window { soundProbe: Probe } }

async function probe(page: Page) {
  await page.addInitScript(() => {
    // Observe native Web Audio; do not replace rendering with a fake player.
    const result: Probe = { starts: [], contexts: [], gains: [], outputPeak: 0, active: 0, maxActive: 0 };
    const playing = new Set<AudioBufferSourceNode>();
    window.soundProbe = result;
    const NativeContext = window.AudioContext;
    window.AudioContext = class extends NativeContext {
      constructor(options?: AudioContextOptions) {
        super(options);
        result.contexts.push(this);
      }
      createGain() {
        const gain = super.createGain();
        result.gains.push(gain);
        const analyser = this.createAnalyser();
        analyser.fftSize = 256;
        gain.connect(analyser);
        const data = new Float32Array(256);
        const timer = setInterval(() => {
          if (this.state === "closed") { clearInterval(timer); return; }
          analyser.getFloatTimeDomainData(data);
          for (const value of data) result.outputPeak = Math.max(result.outputPeak, Math.abs(value));
        }, 5);
        return gain;
      }
      createBufferSource() {
        const source = super.createBufferSource();
        const start = source.start.bind(source);
        const stop = source.stop.bind(source);
        const finished = () => { playing.delete(source); result.active = playing.size; };
        source.addEventListener("ended", finished);
        source.stop = (...args: Parameters<AudioBufferSourceNode["stop"]>) => { finished(); stop(...args); };
        source.start = (...args: Parameters<AudioBufferSourceNode["start"]>) => {
          const samples = source.buffer!.getChannelData(0);
          let peak = 0, energy = 0;
          for (const sample of samples) { peak = Math.max(peak, Math.abs(sample)); energy += sample * sample; }
          result.starts.push({ duration: source.buffer!.duration, peak, rms: Math.sqrt(energy / samples.length),
            gain: result.gains.at(-1)!.gain.value });
          playing.add(source);
          result.active = playing.size;
          result.maxActive = Math.max(result.maxActive, result.active);
          start(...args);
        };
        return source;
      }
    };
  });
}

async function count(page: Page) { return page.evaluate(() => window.soundProbe.starts.length); }
async function createBoard(page: Page) {
  const response = await page.request.post("/api/games", { data: { opponent: "human", initial_time_ms: 3600000 } });
  expect(response.ok()).toBeTruthy();
  const game = await response.json();
  await page.goto(`/games/${game.id}`);
  await expect(page.getByLabel("Connection live")).toBeVisible();
  return game;
}

test("native audio unlock, wooden signal, one sound per move and fuller capture", async ({ page }) => {
  await probe(page);
  const game = await createBoard(page);
  expect(await page.evaluate(() => window.soundProbe.contexts.length)).toBe(0);
  expect(await count(page)).toBe(0);
  await page.getByRole("button", { name: "Test sound", exact: true }).click();
  await expect(page.getByRole("status").filter({ hasText: "Test sound sent" })).toBeVisible();
  await expect.poll(() => page.evaluate(() => window.soundProbe.outputPeak)).toBeGreaterThan(0.01);
  expect(await page.evaluate(() => window.soundProbe.contexts[0].state)).toBe("running");
  const sound = await page.evaluate(() => window.soundProbe.starts[0]);
  expect(sound.duration).toBeCloseTo(0.16, 3);
  expect(sound.peak).toBeGreaterThan(0.1);
  expect(sound.peak).toBeLessThan(0.8);
  expect(sound.rms).toBeGreaterThan(0.02);
  expect(sound.gain).toBeCloseTo(0.4, 2);

  await page.getByRole("gridcell", { name: "e2 white pawn" }).click();
  await page.getByRole("gridcell", { name: "e4 empty" }).click();
  await expect(page.getByRole("gridcell", { name: "e4 white pawn" })).toBeVisible();
  await expect.poll(() => count(page)).toBe(2); // HTTP + socket must not double play.
  let current = await (await page.request.get(`/api/games/${game.id}`)).json();
  await page.request.post(`/api/games/${game.id}/moves`, { data: { move: "d7d5", position_version: current.version } });
  await expect.poll(() => count(page)).toBe(3);
  current = await (await page.request.get(`/api/games/${game.id}`)).json();
  await page.request.post(`/api/games/${game.id}/moves`, { data: { move: "e4d5", position_version: current.version } });
  await expect.poll(() => count(page)).toBe(4);
  expect(await page.evaluate(() => window.soundProbe.starts.at(-1)!.duration)).toBeCloseTo(0.19, 3);
  await page.evaluate(() => window.soundProbe.contexts[0].suspend());
  await page.getByRole("button", { name: "Test sound", exact: true }).click();
  await expect.poll(() => count(page)).toBe(5);
  expect(await page.evaluate(() => window.soundProbe.contexts[0].state)).toBe("running");
  await test.info().attach("native-audio-signal.json", { body: JSON.stringify(await page.evaluate(() => ({
    starts: window.soundProbe.starts, outputPeak: window.soundProbe.outputPeak,
  }))), contentType: "application/json" });
  await page.screenshot({ path: `test-results/wooden-sound-${test.info().project.name}.png`, fullPage: true });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
});

test("live moves before a gesture are dropped, not queued for later", async ({ page }) => {
  await probe(page);
  const game = await createBoard(page);
  await page.request.post(`/api/games/${game.id}/moves`, { data: { move: "e2e4", position_version: game.version } });
  await expect(page.getByRole("gridcell", { name: "e4 white pawn" })).toBeVisible();
  expect(await count(page)).toBe(0);
  expect(await page.evaluate(() => window.soundProbe.contexts.length)).toBe(0);
  await page.getByRole("button", { name: "Test sound", exact: true }).click();
  await expect.poll(() => count(page)).toBe(1);
  await expect(page.getByRole("status").filter({ hasText: "Test sound sent" })).toBeVisible();
});

test("mute, zero volume, persistence, keyboard unlock and replay stay correct", async ({ page }) => {
  await probe(page);
  const game = await createBoard(page);
  await page.getByRole("button", { name: "Test sound", exact: true }).focus();
  await page.keyboard.press("Enter");
  await expect.poll(() => count(page)).toBe(1);
  const mute = page.getByRole("button", { name: "Mute board sounds" });
  await mute.click();
  await expect(mute).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("button", { name: "Test sound", exact: true })).toBeDisabled();
  await page.request.post(`/api/games/${game.id}/moves`, { data: { move: "e2e4", position_version: game.version } });
  await expect(page.getByRole("gridcell", { name: "e4 white pawn" })).toBeVisible();
  expect(await count(page)).toBe(1);
  await expect.poll(() => page.evaluate(() => window.soundProbe.gains[0].gain.value)).toBeLessThan(0.001);
  await page.reload();
  await expect(mute).toHaveAttribute("aria-pressed", "true");
  expect(await count(page)).toBe(0); // No history audio on reload.
  await mute.click();
  const volume = page.getByRole("slider", { name: "Board sound volume" });
  await volume.focus();
  await page.keyboard.press("Home");
  await expect(volume).toHaveValue("0");
  await expect(page.getByRole("button", { name: "Test sound", exact: true })).toBeDisabled();
  const current = await (await page.request.get(`/api/games/${game.id}`)).json();
  await page.request.post(`/api/games/${game.id}/moves`, { data: { move: "e7e5", position_version: current.version } });
  await expect(page.getByRole("gridcell", { name: "e5 black pawn" })).toBeVisible();
  expect(await count(page)).toBe(0);
  await volume.focus();
  await page.keyboard.press("ArrowRight");
  await expect(volume).toHaveValue("5");
  await page.getByRole("button", { name: "Test sound", exact: true }).click();
  await expect.poll(() => count(page)).toBe(1);
  await expect.poll(() => page.evaluate(() => window.soundProbe.gains[0].gain.value)).toBeCloseTo(0.05, 2);
  await page.getByRole("button", { name: "First position", exact: true }).click();
  const before = await (await page.request.get(`/api/games/${game.id}`)).json();
  await page.request.post(`/api/games/${game.id}/moves`, { data: { move: "g1f3", position_version: before.version } });
  await expect(page.locator(".move-row")).toHaveCount(2);
  expect(await count(page)).toBe(1); // Background live feed while replaying is quiet.
  await page.reload();
  await expect(volume).toHaveValue("5");
  expect(await count(page)).toBe(0);
});

test("socket baseline, duplicate update, history gap and reset are silent", async ({ page }) => {
  await probe(page);
  const game = await (await page.request.post("/api/games", { data: { opponent: "human" } })).json();
  let socket: WebSocketRoute | undefined;
  await page.routeWebSocket("**/ws/games/**", ws => { socket = ws; });
  await page.goto(`/games/${game.id}`);
  await expect(page.getByRole("gridcell", { name: "e2 white pawn" })).toBeVisible();
  await page.getByRole("button", { name: "Test sound", exact: true }).click();
  await expect.poll(() => count(page)).toBe(1);
  let current = await (await page.request.post(`/api/games/${game.id}/moves`, { data: { move: "e2e4", position_version: game.version } })).json();
  await expect.poll(() => Boolean(socket)).toBeTruthy();
  socket!.send(JSON.stringify({ type: "snapshot", payload: current })); // Reconnect baseline with a missed move.
  await expect(page.getByRole("gridcell", { name: "e4 white pawn" })).toBeVisible();
  socket!.send(JSON.stringify({ type: "snapshot", payload: current }));
  current = await (await page.request.post(`/api/games/${game.id}/moves`, { data: { move: "e7e5", position_version: current.version } })).json();
  current = await (await page.request.post(`/api/games/${game.id}/moves`, { data: { move: "g1f3", position_version: current.version } })).json();
  socket!.send(JSON.stringify({ type: "snapshot", payload: current })); // Gap of two plies.
  await expect(page.getByRole("gridcell", { name: "f3 white knight" })).toBeVisible();
  expect(await count(page)).toBe(1);
  current = await (await page.request.post(`/api/games/${game.id}/reset`)).json();
  socket!.send(JSON.stringify({ type: "snapshot", payload: current }));
  await expect(page.getByRole("gridcell", { name: "e2 white pawn" })).toBeVisible();
  expect(await count(page)).toBe(1);
});

test("unavailable browser audio does not break board play", async ({ page }) => {
  await page.addInitScript(() => {
    window.AudioContext = class { constructor() { throw new Error("Audio unavailable fixture"); } } as unknown as typeof AudioContext;
    localStorage.setItem("ai-chess-lounge:board-sound", "invalid-json");
  });
  await createBoard(page);
  await page.getByRole("button", { name: "Test sound", exact: true }).click();
  await expect(page.getByRole("status").filter({ hasText: "Audio is blocked" })).toBeVisible();
  await page.getByRole("gridcell", { name: "e2 white pawn" }).click();
  await page.getByRole("gridcell", { name: "e4 empty" }).click();
  await expect(page.getByRole("gridcell", { name: "e4 white pawn" })).toBeVisible();
});

test("sound dashboard renders twelve distinct bounded samples without changing game default", async ({ page }) => {
  await probe(page);
  await page.goto("/sound-lab");
  await expect(page.getByRole("heading", { name: "Find your wooden sound." })).toBeVisible();
  await expect(page.locator(".sound-card")).toHaveCount(12);
  expect(await count(page)).toBe(0);
  const fingerprints: string[] = [];
  for (let id = 1; id <= 12; id++) {
    await page.getByRole("button", { name: `Replay Sound ${id}`, exact: true }).click();
    await expect.poll(() => count(page)).toBe(id);
    const sample = await page.evaluate(() => window.soundProbe.starts.at(-1)!);
    expect(sample.peak).toBeGreaterThan(0.1);
    expect(sample.peak).toBeLessThan(0.8);
    expect(sample.duration).toBeLessThanOrEqual(0.251);
    expect(sample.rms).toBeGreaterThan(0.02);
    fingerprints.push(JSON.stringify({ duration: sample.duration, peak: sample.peak, rms: sample.rms }));
  }
  expect(new Set(fingerprints).size).toBe(12);
  expect(await page.evaluate(() => window.soundProbe.maxActive)).toBe(1);
  const energies = await page.evaluate(() => window.soundProbe.starts.map(sample => sample.rms ** 2 * sample.duration));
  expect(Math.max(...energies) / Math.min(...energies)).toBeLessThan(2.5);
  await page.getByRole("button", { name: "Mute board sounds" }).click();
  for (let id = 1; id <= 12; id++) {
    await expect(page.getByRole("button", { name: `Replay Sound ${id}`, exact: true })).toBeDisabled();
  }
  expect(await count(page)).toBe(12);
  await page.getByRole("button", { name: "Mute board sounds" }).click();
  await page.getByRole("button", { name: "Test sound", exact: true }).click();
  await expect.poll(() => count(page)).toBe(13);
  const defaultReplay = await page.evaluate(() => window.soundProbe.starts.at(-1)!);
  expect(JSON.stringify({ duration: defaultReplay.duration, peak: defaultReplay.peak, rms: defaultReplay.rms })).toBe(fingerprints[0]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  await page.screenshot({ path: `test-results/sound-dashboard-${test.info().project.name}.png`, fullPage: true });
  await test.info().attach("twelve-sample-signals.json", { body: JSON.stringify(await page.evaluate(() => ({
    starts: window.soundProbe.starts, outputPeak: window.soundProbe.outputPeak,
  }))), contentType: "application/json" });
});
