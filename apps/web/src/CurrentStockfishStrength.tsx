import { useEffect, useRef, useState } from "react";
import { skillValue, strengthMode, strengthSettings, strengthName, validStrength, type StockfishCapabilities, type StockfishChoice } from "./StockfishStrength";
import type { GameSnapshot, PlayerConfiguration } from "./types";

type Color = "white" | "black";
export function playerStrength(player: PlayerConfiguration): StockfishChoice {
  return player.settings.skill_level != null ? `skill:${Number(player.settings.skill_level)}` : player.settings.full_strength ? "full" : Number(player.settings.target_elo ?? 1600);
}
export function strengthLabel(value: StockfishChoice): string {
  return skillValue(value) !== null ? `Skill Level ${skillValue(value)} (uncalibrated)` : value === "full" ? "Full strength" : `${value} target Elo`;
}
export function withStrength(player: PlayerConfiguration, value: StockfishChoice): PlayerConfiguration {
  const settings = { ...player.settings };
  delete settings.skill_level;
  return { ...player, display_name: strengthName(value), settings: { ...settings, ...strengthSettings(value) } };
}

export function CurrentStockfishStrength({ game, caps, disabled, onApply }: {
  game: GameSnapshot; caps: StockfishCapabilities | null; disabled: boolean;
  onApply: (color: Color, value: StockfishChoice, revision: number) => Promise<void>;
}) {
  return <section className="current-stockfish-panel" aria-label="Current match engine strength">
    <h3>Current match Stockfish strength</h3>
    {(["white", "black"] as const).filter(color => game[`${color}_player`].adapter_id === "stockfish").map(color =>
      <CurrentSeat key={`${game.id}:${color}`} game={game} color={color} caps={caps} disabled={disabled} onApply={onApply} />)}
  </section>;
}
function CurrentSeat({ game, color, caps, disabled, onApply }: {
  game: GameSnapshot; color: Color; caps: StockfishCapabilities | null; disabled: boolean;
  onApply: (color: Color, value: StockfishChoice, revision: number) => Promise<void>;
}) {
  const current = playerStrength(game[`${color}_player`]);
  const [proposed, setProposed] = useState(current);
  const [confirmation, setConfirmation] = useState<{ value: StockfishChoice; revision: number } | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { setProposed(current); }, [current]);
  useEffect(() => {
    if (!busy && confirmation && (confirmation.revision !== game.revision || disabled)) setConfirmation(null);
  }, [game.revision, disabled, busy, confirmation]);
  const valid = validStrength(proposed, caps);
  return <fieldset className="stockfish-strength" aria-label={`Current ${color} Stockfish`}>
    <legend>{color === "white" ? "White" : "Black"} Stockfish — current match</legend>
    <p aria-label={`Current ${color} strength`}>Current: <strong>{strengthLabel(current)}</strong></p>
    <label>Proposed strength mode<select aria-label={`Current ${color} strength mode`} value={strengthMode(proposed)}
      onChange={e => setProposed(e.target.value === "full" ? "full" : e.target.value === "skill" ? "skill:0" : Math.max(caps?.elo_min ?? 1600, 1600))}>
      <option value="skill">Skill Level — uncalibrated</option>
      <option value="rated">Target Elo</option><option value="full">Full strength</option>
    </select></label>
    {typeof proposed === "number" && <label>Proposed Elo<input type="number" aria-label={`Current ${color} proposed Elo`} value={Number.isFinite(proposed) ? proposed : ""}
      min={caps?.elo_min ?? undefined} max={caps?.elo_max ?? undefined} step={1} onChange={e => setProposed(e.target.valueAsNumber)} /></label>}
    <p>Proposed: {strengthLabel(proposed)}. Nothing changes until you confirm.</p>
    {skillValue(proposed) !== null && <label>Proposed Skill Level<input type="number" aria-label={`Current ${color} proposed Skill Level`} min={caps?.skill_min ?? 0} max={caps?.skill_max ?? 20} step={1}
      value={Number.isFinite(skillValue(proposed)) ? skillValue(proposed)! : ""} onChange={e => setProposed(`skill:${e.target.valueAsNumber}`)} /></label>}
    <button disabled={disabled || busy || !valid || proposed === current} onClick={() => setConfirmation({ value: proposed, revision: game.revision })}>
      Update current {color} Stockfish
    </button>
    {confirmation && <StrengthConfirmation color={color} current={current} proposed={confirmation.value} busy={busy}
      onCancel={() => setConfirmation(null)} onConfirm={async () => {
        setBusy(true);
        try { await onApply(color, confirmation.value, confirmation.revision); }
        finally { setBusy(false); setConfirmation(null); }
      }} />}
  </fieldset>;
}
function StrengthConfirmation({ color, current, proposed, busy, onCancel, onConfirm }: {
  color: Color; current: StockfishChoice; proposed: StockfishChoice; busy: boolean;
  onCancel: () => void; onConfirm: () => Promise<void>;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => { const element = dialog.current; element?.showModal(); return () => element?.close(); }, []);
  return <dialog ref={dialog} className="promotion-dialog human-action-dialog" aria-labelledby="strength-confirm-title"
    onCancel={e => { e.preventDefault(); if (!busy) onCancel(); }}>
    <h2 id="strength-confirm-title">{skillValue(proposed) !== null ? `Update the current Stockfish Skill Level to ${skillValue(proposed)}?` : proposed === "full" ? "Update the current Stockfish to full strength?" : `Update the current Stockfish Elo rating to ${proposed}?`}</h2>
    <p>{color === "white" ? "White" : "Black"} seat: {strengthLabel(current)} → <strong>{strengthLabel(proposed)}</strong></p>
    <p>Play will pause before applying this change. The position and move history stay intact. The match stays paused; choose Resume play when ready. All connected viewers will see the confirmed setting.</p>
    <div className="secondary-actions"><button autoFocus disabled={busy} onClick={onCancel}>Cancel</button>
      <button disabled={busy} onClick={() => void onConfirm()}>Confirm strength update</button></div>
  </dialog>;
}
