import { useCallback, useEffect, useRef, useState } from "react";
import { BoardAudio, originalPrototype, readSoundSettings, soundStorageKey, type AudioStatus, type BoardSoundKind } from "./boardSound";

export function useBoardSound(preloadPrototype = true) {
  const [settings, setSettings] = useState(readSoundSettings);
  const [status, setStatus] = useState<AudioStatus>("locked");
  const [testResult, setTestResult] = useState("");
  const audio = useRef<BoardAudio | null>(null);
  const testRequest = useRef(0);
  const currentSettings = useRef(settings);
  currentSettings.current = settings;

  useEffect(() => {
    const engine = new BoardAudio(setStatus);
    audio.current = engine;
    engine.settings(currentSettings.current.muted, currentSettings.current.volume);
    if (preloadPrototype) void engine.preloadPrototype().catch(() => { /* Explicit replay can retry. */ });
    const gesture = (event: Event) => {
      if (event.isTrusted) void engine.unlock().then(ready => {
        if (ready && preloadPrototype) void engine.prepareSample(originalPrototype.id);
      });
    };
    window.addEventListener("pointerdown", gesture, true);
    window.addEventListener("pointerup", gesture, true);
    window.addEventListener("touchend", gesture, { capture: true, passive: true });
    window.addEventListener("keydown", gesture, true);
    return () => {
      window.removeEventListener("pointerdown", gesture, true);
      window.removeEventListener("pointerup", gesture, true);
      window.removeEventListener("touchend", gesture, true);
      window.removeEventListener("keydown", gesture, true);
      engine.dispose();
      audio.current = null;
    };
  }, [preloadPrototype]);

  useEffect(() => {
    audio.current?.settings(settings.muted, settings.volume);
    setTestResult("");
    try { localStorage.setItem(soundStorageKey, JSON.stringify(settings)); } catch { /* Storage is optional. */ }
  }, [settings]);

  const playMove = useCallback((kind: BoardSoundKind) => { audio.current?.play(kind); }, []);

  async function testSound(sampleId: number = originalPrototype.id) {
    const engine = audio.current;
    if (!engine) return;
    const request = ++testRequest.current;
    const ready = await engine.unlock();
    const prepared = ready && await engine.prepareSample(sampleId);
    // A slow fetch/decode must not replay an old selection over a newer click.
    if (request !== testRequest.current || audio.current !== engine) return;
    const played = prepared && engine.play("move", sampleId, true);
    setTestResult(played ? "Test sound sent. If silent, check your tab and device volume."
      : ready ? "This sample could not play. Check the connection and try again."
        : "Audio is blocked. Check this browser's sound permission and try again.");
  }

  return { settings, setSettings, status, testResult, testSound, playMove };
}

export function BoardSoundControls({ sound }: { sound: ReturnType<typeof useBoardSound> }) {
  const { settings, setSettings, status, testResult } = sound;
  return <section className="board-sound" aria-label="Board sound">
    <div className="board-sound-controls">
      <span className="board-sound-title">ORIGINAL WOOD · SELECTED</span>
      <button className="ghost-button" aria-label={`${settings.muted ? "Sound off" : "Sound on"}: Mute board sounds`} aria-pressed={settings.muted}
        onClick={() => setSettings(value => ({ ...value, muted: !value.muted }))}>
        {settings.muted ? "Sound off" : "Sound on"}
      </button>
      <label className="board-volume">Volume
        <input type="range" min="0" max="100" step="5" value={settings.volume}
          aria-label="Board sound volume" aria-valuetext={`${settings.volume}%`}
          onChange={event => setSettings(value => ({ ...value, volume: Number(event.target.value) }))} />
        <output>{settings.volume}%</output>
      </label>
      <button className="ghost-button" disabled={settings.muted || settings.volume === 0}
        onClick={() => void sound.testSound()}>Test sound</button>
    </div>
    <p role="status">{settings.muted ? "Board sounds are muted." : settings.volume === 0 ? "Volume is zero."
      : testResult || (status === "ready" ? "Sound enabled for live moves and captures."
        : status === "unavailable" ? "Audio unavailable. Check browser sound permission, then try Test sound."
          : "Click Test sound or interact with the board to enable audio.")}</p>
    <a className="sound-lab-link" href="/sound-lab">Compare 19 wood sounds</a>
  </section>;
}
