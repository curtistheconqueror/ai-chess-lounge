import { useEffect, useState } from "react";
import type { GameSnapshot } from "./types";

export type StockfishChoice = number | "full";
export const stockfishChoiceKey = "ai-chess-lounge:stockfish-strength";
export interface StockfishCapabilities {
  available: boolean; version: string | null;
  elo_min: number | null; elo_max: number | null; full_strength_available: boolean;
}
export function readStockfishChoice(): StockfishChoice {
  try {
    const saved = JSON.parse(localStorage.getItem(stockfishChoiceKey) ?? "null");
    if (saved === "full" || (Number.isInteger(saved) && saved >= 800 && saved <= 3200)) return saved;
  } catch { /* Storage is optional. */ }
  return 1600;
}
export function validStrength(value: StockfishChoice, caps: StockfishCapabilities | null): boolean {
  if (value === "full") return true;
  return Number.isInteger(value) && value >= (caps?.elo_min ?? 800) && value <= (caps?.elo_max ?? 3200);
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
    <label>Strength mode<select aria-label="Stockfish strength mode" value={value === "full" ? "full" : "rated"}
      onChange={event => onChange(event.target.value === "full" ? "full" : Math.max(caps?.elo_min ?? 1600, 1600))}>
      <option value="rated">Target Elo</option><option value="full">Full strength · unrestricted</option>
    </select></label>
    {value !== "full" && <>
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
    {value === "full" ? <p>No Elo handicap. Search time and hardware still limit playing strength.</p>
      : <p>Target Elo uses Stockfish's native rating limit; it is not a guaranteed rating. Type any supported integer, or use 25-Elo slider steps.</p>}
    {!validStrength(value, caps) && <p role="alert">Enter a whole-number Elo within the supported range.</p>}
    <p>Changes apply when you click New match. To change an existing seat, pause the match, then use Apply White or Apply Black.</p>
    <p className="stockfish-current" aria-label="Current match Stockfish strength">Current match: {current.length
      ? current.map(([color, player]) => `${color}: ${player.settings.full_strength ? "full strength" : `${player.settings.target_elo ?? 1600} target Elo`}`).join("; ")
      : "no Stockfish seat"}.</p>
  </fieldset>;
}
