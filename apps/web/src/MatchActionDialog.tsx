import { useEffect, useRef, useState } from "react";

export type MatchAction = "abort" | "adjudicate" | "reset";
export type AdjudicatedResult = "1-0" | "0-1" | "1/2-1/2";

const copy: Record<MatchAction, { title: string; body: string; confirm: string }> = {
  abort: {
    title: "Abort this match?",
    body: "The match ends with no result (*). Moves and history are kept. This cannot be undone.",
    confirm: "Abort match",
  },
  adjudicate: {
    title: "Adjudicate this match?",
    body: "The match ends now with the result you choose. History records that the operator decided it.",
    confirm: "Record result",
  },
  reset: {
    title: "Reset with paired bots?",
    body: "Each paired bot is authorized for the current game only. After a reset the match pauses straight away until both bots are paired again and put back in their seats. To start over with the same bots, generate new pairings and use New match instead.",
    confirm: "Reset anyway",
  },
};

export function MatchActionDialog({ action, busy, onConfirm, onCancel }: {
  action: MatchAction;
  busy: boolean;
  onConfirm: (result: AdjudicatedResult | null) => void;
  onCancel: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [result, setResult] = useState<AdjudicatedResult>("1/2-1/2");
  useEffect(() => {
    const element = dialog.current;
    element?.showModal();
    return () => element?.close();
  }, []);
  const text = copy[action];
  return <dialog ref={dialog} className="promotion-dialog human-action-dialog" aria-labelledby="match-action-title"
    onCancel={event => { event.preventDefault(); if (!busy) onCancel(); }}>
    <h2 id="match-action-title">{text.title}</h2>
    <p>{text.body}</p>
    {action === "adjudicate" && <label>Result
      <select aria-label="Adjudicated result" value={result} onChange={event => setResult(event.target.value as AdjudicatedResult)}>
        <option value="1-0">1-0 · White wins</option>
        <option value="0-1">0-1 · Black wins</option>
        <option value="1/2-1/2">½-½ · Draw</option>
      </select>
    </label>}
    <div className="secondary-actions">
      <button autoFocus disabled={busy} onClick={onCancel}>Cancel</button>
      <button disabled={busy} onClick={() => onConfirm(action === "adjudicate" ? result : null)}>{text.confirm}</button>
    </div>
  </dialog>;
}
