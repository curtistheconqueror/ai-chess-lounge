import { useEffect, useRef, useState } from "react";

export function HumanActionDialog({ action, claimMoves, busy, onConfirm, onCancel }: {
  action: "white" | "black" | "draw";
  claimMoves: string[];
  busy: boolean;
  onConfirm: (move: string | null) => void;
  onCancel: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [move, setMove] = useState(claimMoves[0] ?? "");
  useEffect(() => {
    const element = dialog.current;
    element?.showModal();
    return () => element?.close();
  }, []);
  const isDraw = action === "draw";
  return <dialog ref={dialog} className="promotion-dialog human-action-dialog" onCancel={(event) => { event.preventDefault(); if (!busy) onCancel(); }} aria-labelledby="human-action-title">
    <h2 id="human-action-title">{isDraw ? "Claim a draw?" : `Resign ${action === "white" ? "White" : "Black"}?`}</h2>
    <p>{isDraw ? "The arbiter will validate your claim. The clock continues until it is accepted." : "This ends the match and awards the win to your opponent. The clock continues until confirmed."}</p>
    {isDraw && claimMoves.length > 0 && <label>Intended move
      <select aria-label="Intended draw-claim move" value={move} onChange={(event) => setMove(event.target.value)}>
        {claimMoves.map((candidate) => <option key={candidate} value={candidate}>{candidate}</option>)}
      </select>
      <small>The move is announced for the claim; it is not played on the board.</small>
    </label>}
    <div className="secondary-actions">
      <button autoFocus disabled={busy} onClick={onCancel}>Cancel</button>
      <button disabled={busy} onClick={() => onConfirm(isDraw && claimMoves.length ? move : null)}>{isDraw ? "Confirm draw claim" : "Confirm resignation"}</button>
    </div>
  </dialog>;
}
