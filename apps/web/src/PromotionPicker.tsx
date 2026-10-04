import { useEffect, useRef } from "react";

import { ChessPiece } from "./ChessPiece";

const promotions = ["queen", "rook", "bishop", "knight"] as const;

export type PromotionPiece = (typeof promotions)[number];

export function PromotionPicker({
  onChoose,
  color,
  onCancel,
}: {
  onChoose: (piece: PromotionPiece) => void;
  color: "white" | "black";
  onCancel: () => void;
}) {
  const firstOption = useRef<HTMLButtonElement>(null);
  const dialog = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const previousFocus = document.activeElement as HTMLElement | null;
    firstOption.current?.focus();
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") onCancel();
      if (event.key === "Tab") {
        const buttons = Array.from(
          dialog.current?.querySelectorAll<HTMLButtonElement>("button") ?? [],
        );
        if (!buttons.length) return;
        const first = buttons[0];
        const last = buttons[buttons.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      previousFocus?.focus();
    };
  }, [onCancel]);

  return (
    <div className="promotion-backdrop" role="presentation" onMouseDown={onCancel}>
      <div
        ref={dialog}
        className="promotion-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="promotion-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <p className="eyebrow">PROMOTION</p>
        <h2 id="promotion-title">Choose your piece</h2>
        <div className="promotion-options">
          {promotions.map((type, index) => (
            <button
              ref={index === 0 ? firstOption : undefined}
              key={type}
              onClick={() => onChoose(type)}
              aria-label={`Promote to ${type}`}
            >
              <ChessPiece piece={{ type, color, symbol: "" }} />
              <span>{type}</span>
            </button>
          ))}
        </div>
        <button className="promotion-cancel" onClick={onCancel}>Cancel</button>
      </div>
    </div>
  );
}
