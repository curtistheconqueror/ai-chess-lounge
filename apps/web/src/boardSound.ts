import type { GameSnapshot } from "./types";

export type BoardSoundKind = "move" | "capture";
export type AudioStatus = "locked" | "ready" | "unavailable";
export const soundStorageKey = "ai-chess-lounge:board-sound";
export const defaultSoundSettings = { muted: false, volume: 40 };

export const woodSamples = [
  { id: 1, name: "Wood", description: "Current board sound · rounded contact, short wooden body", pitch: 1, decay: 1, noise: 1, cutoff: 1900, attack: 0.0012, duration: 0.16, weight: 1, second: 0 },
  { id: 2, name: "Felted tap", description: "Soft landing · cushioned base, little top-end", pitch: 0.85, decay: 0.65, noise: 0.45, cutoff: 900, attack: 0.0028, duration: 0.14, weight: 1.3, second: 0 },
  { id: 3, name: "Dry hardwood", description: "Compact knock · firm, closely damped contact", pitch: 1.3, decay: 0.55, noise: 1.3, cutoff: 2400, attack: 0.0009, duration: 0.12, weight: 0.8, second: 0 },
  { id: 4, name: "Deep board", description: "Lower body · a little more board resonance", pitch: 0.64, decay: 1.45, noise: 0.7, cutoff: 1400, attack: 0.0018, duration: 0.23, weight: 1.6, second: 0 },
  { id: 5, name: "Light placement", description: "Small piece · light, crisp and restrained", pitch: 1.6, decay: 0.62, noise: 0.9, cutoff: 2800, attack: 0.0012, duration: 0.13, weight: 0.7, second: 0 },
  { id: 6, name: "Weighted capture", description: "Heavier landing · low contact with a tiny settling tap", pitch: 0.78, decay: 1.15, noise: 1.1, cutoff: 1800, attack: 0.0014, duration: 0.21, weight: 1.4, second: 0.3 },
  { id: 7, name: "Soft board", description: "Warm and muted · broad, gentle impact", pitch: 0.92, decay: 1.2, noise: 0.35, cutoff: 1100, attack: 0.0034, duration: 0.2, weight: 1.5, second: 0 },
  { id: 8, name: "Hollow knock", description: "Airier board · upper wooden body, reduced low thud", pitch: 1.08, decay: 1.45, noise: 0.8, cutoff: 2000, attack: 0.0015, duration: 0.24, weight: 0.35, second: 0 },
  { id: 9, name: "Close tap", description: "Very short contact · dry and intimate", pitch: 1.12, decay: 0.4, noise: 1.5, cutoff: 2100, attack: 0.0008, duration: 0.1, weight: 1.1, second: 0 },
  { id: 10, name: "Dense piece", description: "Solid little thock · low, tightly controlled body", pitch: 0.72, decay: 0.75, noise: 0.8, cutoff: 1500, attack: 0.001, duration: 0.15, weight: 1.8, second: 0 },
  { id: 11, name: "Gentle settle", description: "Two close contacts · careful placement on wood", pitch: 1.2, decay: 0.8, noise: 0.6, cutoff: 1700, attack: 0.002, duration: 0.19, weight: 1, second: 0.48 },
  { id: 12, name: "Table resonance", description: "Broad wooden base · a slightly longer natural tail", pitch: 0.82, decay: 1.6, noise: 1, cutoff: 1600, attack: 0.0022, duration: 0.25, weight: 1.2, second: 0.12 },
] as const;

export function readSoundSettings() {
  try {
    const saved = JSON.parse(localStorage.getItem(soundStorageKey) ?? "null");
    return {
      muted: typeof saved?.muted === "boolean" ? saved.muted : false,
      volume: typeof saved?.volume === "number" && Number.isFinite(saved.volume)
        ? Math.max(0, Math.min(100, saved.volume)) : 40,
    };
  } catch {
    return { ...defaultSoundSettings };
  }
}

// Only a newly committed, adjacent ply makes a sound. Loading a board, reset,
// duplicate HTTP/socket updates and catching up a history gap stay quiet.
export function newMoveSound(previous: GameSnapshot | null, next: GameSnapshot): BoardSoundKind | null {
  if (!previous || previous.id !== next.id || previous.generation !== next.generation
    || next.version <= previous.version || next.moves.length !== previous.moves.length + 1) return null;
  return next.moves.at(-1)?.san.includes("x") ? "capture" : "move";
}

// Original synthesized contact sound: a rounded noise transient excites several
// short, inharmonic wooden resonances. No sample downloads or musical oscillator.
export function woodenSamples(sampleRate: number, kind: BoardSoundKind, sampleId = 1): Float32Array {
  const profile = woodSamples.find(sample => sample.id === sampleId) ?? woodSamples[0];
  const capture = kind === "capture";
  const duration = profile.duration + (capture ? 0.03 : 0);
  const samples = new Float32Array(Math.ceil(sampleRate * duration));
  let seed = capture ? 781 : 431;
  let lowNoise = 0;
  for (let i = 0; i < samples.length; i++) {
    const t = i / sampleRate;
    seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0;
    const noise = seed / 2147483648 - 1;
    lowNoise += (1 - Math.exp(-2 * Math.PI * profile.cutoff / sampleRate)) * (noise - lowNoise);
    const attack = 1 - Math.exp(-t / profile.attack);
    const pitch = (capture ? 0.9 : 1) * profile.pitch;
    const body = 0.47 * profile.weight * Math.sin(2 * Math.PI * 310 * pitch * t) * Math.exp(-t / (0.026 * profile.decay))
      + 0.24 * Math.sin(2 * Math.PI * 727 * pitch * t + 0.3) * Math.exp(-t / (0.014 * profile.decay))
      + 0.13 * Math.sin(2 * Math.PI * 1231 * pitch * t + 0.8) * Math.exp(-t / (0.009 * profile.decay));
    const contact = 0.36 * profile.noise * lowNoise * Math.exp(-t / 0.006);
    const settleTime = t - 0.018;
    const settle = settleTime > 0 ? profile.second * Math.sin(2 * Math.PI * 490 * pitch * settleTime)
      * (1 - Math.exp(-settleTime / 0.001)) * Math.exp(-settleTime / 0.01) : 0;
    const tail = Math.min(1, (duration - t) / 0.012);
    samples[i] = (body + contact + settle) * attack * tail * (capture ? 0.76 : 0.68);
  }
  // Keep Sound 1 unchanged; match alternatives by impact energy with peak headroom.
  if (profile.id !== 1) {
    let energy = 0, peak = 0;
    for (const value of samples) { energy += value * value; peak = Math.max(peak, Math.abs(value)); }
    const scale = Math.min(Math.sqrt(0.00065 * sampleRate / energy), 0.72 / peak);
    for (let i = 0; i < samples.length; i++) samples[i] *= scale;
  }
  return samples;
}

export class BoardAudio {
  private context: AudioContext | null = null;
  private gain: GainNode | null = null;
  private buffers = new Map<string, AudioBuffer>();
  private sources = new Set<AudioBufferSourceNode>();
  private muted = false;
  private volume = 40;
  private disposed = false;

  constructor(private onStatus: (status: AudioStatus) => void) {}

  settings(muted: boolean, volume: number) {
    this.muted = muted;
    this.volume = volume;
    if (this.gain && this.context) {
      this.gain.gain.cancelScheduledValues(this.context.currentTime);
      this.gain.gain.setTargetAtTime(muted ? 0 : volume / 100, this.context.currentTime, 0.005);
    }
  }

  async unlock(): Promise<boolean> {
    if (this.disposed) return false;
    try {
      if (!this.context) {
        this.context = new AudioContext();
        this.gain = this.context.createGain();
        this.gain.gain.value = this.muted ? 0 : this.volume / 100;
        this.gain.connect(this.context.destination);
        this.context.onstatechange = () => {
          if (!this.disposed) this.onStatus(this.context?.state === "running" ? "ready" : "locked");
        };
      }
      if (this.context.state !== "running") await this.context.resume();
      if (this.disposed) return false;
      const ready = this.context.state === "running";
      this.onStatus(ready ? "ready" : "locked");
      return ready;
    } catch {
      if (!this.disposed) this.onStatus("unavailable");
      return false;
    }
  }

  play(kind: BoardSoundKind, sampleId = 1, exclusive = false): boolean {
    const context = this.context;
    if (this.disposed || !context || context.state !== "running" || !this.gain
      || this.muted || this.volume === 0) return false;
    try {
      const key = `${sampleId}:${kind}`;
      let buffer = this.buffers.get(key);
      if (!buffer) {
        const samples = woodenSamples(context.sampleRate, kind, sampleId);
        buffer = context.createBuffer(1, samples.length, context.sampleRate);
        buffer.getChannelData(0).set(samples);
        this.buffers.set(key, buffer);
      }
      if (exclusive) {
        for (const playing of this.sources) { playing.stop(); playing.disconnect(); }
        this.sources.clear();
      }
      // Bound rapid test clicks/live bursts; never build an audio backlog.
      if (this.sources.size >= 4) {
        const oldest = this.sources.values().next().value!;
        oldest.stop();
        oldest.disconnect();
        this.sources.delete(oldest);
      }
      const source = context.createBufferSource();
      source.buffer = buffer;
      source.connect(this.gain);
      source.onended = () => { source.disconnect(); this.sources.delete(source); };
      this.sources.add(source);
      source.start();
      return true;
    } catch {
      this.onStatus("unavailable");
      return false;
    }
  }

  dispose() {
    this.disposed = true;
    for (const source of this.sources) { source.stop(); source.disconnect(); }
    this.sources.clear();
    if (this.context) {
      this.context.onstatechange = null;
      void this.context.close().catch(() => {});
    }
  }
}
