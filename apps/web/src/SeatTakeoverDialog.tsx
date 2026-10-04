import { useEffect, useRef } from "react";
import type { PlayerConfiguration } from "./types";

export function SeatTakeoverDialog({ color, current, player, busy, onConfirm, onCancel }: {
  color: "white" | "black"; current: PlayerConfiguration; player: PlayerConfiguration;
  busy: boolean; onConfirm: () => void; onCancel: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const element = dialog.current;
    element?.showModal();
    return () => element?.close();
  }, []);
  return <dialog ref={dialog} className="promotion-dialog human-action-dialog" aria-labelledby="takeover-title"
    onCancel={event => { event.preventDefault(); if (!busy) onCancel(); }}>
    <h2 id="takeover-title">Change {color} player?</h2>
    <p>{current.display_name} → <strong>{player.display_name}</strong></p>
    <p>{player.provider} · {player.model} · {player.effort ?? "Default effort"} · {player.division.replaceAll("_", " ")}</p>
    <p>The match stays paused. Position, remaining time and move history carry over. This switch is recorded in the game history and PGN.</p>
    <div className="secondary-actions">
      <button autoFocus disabled={busy} onClick={onCancel}>Cancel</button>
      <button disabled={busy} onClick={onConfirm}>Confirm seat change</button>
    </div>
  </dialog>;
}
