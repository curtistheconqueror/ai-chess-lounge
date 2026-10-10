import { useEffect, useState } from "react";
import type { GameSnapshot } from "./types";

export type StockfishChoice = number | "full" | `skill:${number}`;
export function skillValue(value: StockfishChoice): number | null {
  return typeof value === "string" && value.startsWith("skill:") ? Number(value.slice(6)) : null;
}
export function strengthMode(value: StockfishChoice): "rated" | "full" | "skill" {
  return value === "full" ? "full" : typeof value === "string" ? "skill" : "rated";
}
export function strengthSettings(value: StockfishChoice) {
  const skill = skillValue(value);
  return { target_elo: typeof value === "number" ? value : 1600, full_strength: value === "full",
    ...(skill !== null ? { skill_level: skill } : {}) };
}
export function strengthName(value: StockfishChoice): string {
  return value === "full" ? "Stockfish full strength" : skillValue(value) !== null ? `Stockfish skill ${skillValue(value)}` : `Stockfish ${value}`;
}
export const stockfishChoiceKey = "ai-chess-lounge:stockfish-strength";
export interface StockfishCapabilities {
  available: boolean; version: string | null;
  elo_min: number | null; elo_max: number | null; full_strength_available: boolean;
  skill_min?: number | null; skill_max?: number | null;
}
export function readStockfishChoice(): StockfishChoice {
  try {
    const saved = JSON.parse(localStorage.getItem(stockfishChoiceKey) ?? "null");
    if (saved === "full" || (Number.isInteger(saved) && saved >= 800 && saved <= 3200)) return saved;
    if (typeof saved === "string" && /^skill:(?:[0-9]|1[0-9]|20)$/.test(saved)) return saved as StockfishChoice;
  } catch { /* Storage is optional. */ }
  return 1600;
}
export function validStrength(value: StockfishChoice, caps: StockfishCapabilities | null): boolean {
  if (value === "full") return true;
  const skill = skillValue(value);
  if (skill !== null) return Number.isInteger(skill) && skill >= (caps?.skill_min ?? 0) && skill <= (caps?.skill_max ?? 20);
  return typeof value === "number" && Number.isInteger(value) && value >= (caps?.elo_min ?? 800) && value <= (caps?.elo_max ?? 3200);
}
export function useStockfishCapabilities() {
  const [caps, setCaps] = useState<StockfishCapabilities | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    void fetch(`${import.meta.env.VITE_API_BASE ?? ""}/api/engine/strength`, { signal: controller.signal })
      .then(response => { if (!response.ok) throw new Error("Engine unavailable"); return response.json(); })
      .then(setCaps).catch(() => { /* The control explains missing runtime information. */ });
    return () => controller.abort();
  }, []);
  return caps;
}
export function StockfishStrength({ value, onChange, caps, game }: {
  value: StockfishChoice; onChange: (value: StockfishChoice) => void;
  caps: StockfishCapabilities | null; game: GameSnapshot | null;
}) {
  const [sliderStep, setSliderStep] = useState(1);
  const rated = caps?.elo_min != null && caps?.elo_max != null;
  const current = game ? Object.entries({ white: game.white_player, black: game.black_player }).filter(([, player]) => player.adapter_id === "stockfish") : [];
  return <fieldset className="stockfish-strength">
    <legend>Stockfish strength for next match</legend>
    <label>Strength mode<select aria-label="Stockfish strength mode" value={strengthMode(value)}
      onChange={event => onChange(event.target.value === "full" ? "full" : event.target.value === "skill" ? "skill:0" : Math.max(caps?.elo_min ?? 1600, 1600))}>
      <option value="skill">Skill Level — uncalibrated</option>
      <option value="rated">Target Elo</option><option value="full">Full strength · unrestricted</option>
    </select></label>
    {typeof value === "number" && <>
      <label>Target Elo<input type="number" aria-label="Stockfish target Elo" min={caps?.elo_min ?? undefined}
        max={caps?.elo_max ?? undefined} step={1} value={Number.isFinite(value) ? value : ""}
        onChange={event => onChange(event.target.valueAsNumber)} /></label>
      {rated && <details className="stockfish-slider" open>
        <summary>Optional Elo slider</summary>
        <label>Slider increments<select aria-label="Stockfish slider increments" value={sliderStep} onChange={event => setSliderStep(Number(event.target.value))}>
          <option value={1}>1 Elo · exact</option><option value={25}>25 Elo steps</option>
        </select></label>
        <input type="range" aria-label="Stockfish Elo slider" aria-valuetext={`${value} target Elo`}
          min={sliderStep === 1 ? caps!.elo_min! : 0}
          max={sliderStep === 1 ? caps!.elo_max! : Math.ceil((caps!.elo_max! - caps!.elo_min!) / sliderStep)} step={1}
          value={sliderStep === 1 ? (Number.isFinite(value) ? value : caps!.elo_min!) : Math.round(((Number.isFinite(value) ? value : caps!.elo_min!) - caps!.elo_min!) / sliderStep)}
          onChange={event => onChange(sliderStep === 1 ? Number(event.target.value)
            : Math.min(caps!.elo_max!, caps!.elo_min! + Number(event.target.value) * sliderStep))} />
      </details>}
    </>}
    <p>{caps?.available ? `${caps.version ?? "Stockfish"}: ${rated ? `${caps.elo_min}–${caps.elo_max} target Elo, inclusive.` : "No rated range advertised."}`
      : "Stockfish is unavailable or its runtime settings could not be read. A working engine is required to play."}</p>
    {skillValue(value) !== null && <label>Skill Level<input type="number" aria-label="Stockfish Skill Level" min={caps?.skill_min ?? 0} max={caps?.skill_max ?? 20} step={1}
      value={Number.isFinite(skillValue(value)) ? skillValue(value)! : ""} onChange={e => onChange(`skill:${e.target.valueAsNumber}`)} /></label>}
    {skillValue(value) !== null ? <p>Native Skill Level 0–20. Lower levels weaken play; these are not calibrated Elo ratings or a guarantee of beginner difficulty.</p> : value === "full" ? <p>No Elo handicap. Search time and hardware still limit playing strength.</p>
      : <p>Target Elo uses Stockfish's native rating limit; it is not a guaranteed rating. Type any supported integer, or use 25-Elo slider steps.</p>}
    {!validStrength(value, caps) && <p role="alert">{skillValue(value) !== null ? "Enter a whole-number Skill Level from 0 to 20." : "Enter a whole-number Elo within the supported range."}</p>}
    <p>These are next-match settings only. For the game already on the board, use Current match Stockfish strength above and confirm the update.</p>
    <p className="stockfish-current" aria-label="Current match Stockfish strength">Current match: {current.length
      ? current.map(([color, player]) => `${color}: ${player.settings.skill_level != null ? `Skill Level ${player.settings.skill_level} (uncalibrated)` : player.settings.full_strength ? "full strength" : `${player.settings.target_elo ?? 1600} target Elo`}`).join("; ")
      : "no Stockfish seat"}.</p>
  </fieldset>;
}
