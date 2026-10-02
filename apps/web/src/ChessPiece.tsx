import type { BoardPiece } from "./chess";

export function ChessPiece({ piece }: { piece: BoardPiece }) {
  return (
    <svg
      className={`piece-svg ${piece.color}`}
      viewBox="0 0 100 100"
      role="img"
      aria-label={`${piece.color} ${piece.type}`}
    >
      <g className="piece-shape">
        {piece.type === "king" && (
          <>
            <path d="M46 9h8v12h11v8H54v11h-8V29H35v-8h11z" />
            <path d="M34 43c6-7 26-7 32 0l-5 13 10 24H29l10-24z" />
            <path d="M25 81h50v9H25z" />
          </>
        )}
        {piece.type === "queen" && (
          <>
            <circle cx="22" cy="28" r="6" />
            <circle cx="50" cy="20" r="6" />
            <circle cx="78" cy="28" r="6" />
            <path d="m22 34 12 25 16-33 16 33 12-25-8 44H30z" />
            <path d="M25 79h50v11H25z" />
          </>
        )}
        {piece.type === "rook" && (
          <>
            <path d="M25 19h12v10h10V19h12v10h10V19h9v25H22V19z" />
            <path d="M30 45h40l-5 34H35z" />
            <path d="M25 79h50v11H25z" />
          </>
        )}
        {piece.type === "bishop" && (
          <>
            <path d="M50 13c12 9 19 19 19 29 0 9-6 16-14 20H45c-8-4-14-11-14-20 0-10 7-20 19-29z" />
            <path className="piece-cut" d="m57 24-17 24" />
            <path d="M36 62h28l7 17H29z" />
            <path d="M25 79h50v11H25z" />
          </>
        )}
        {piece.type === "knight" && (
          <>
            <path d="M29 78c2-19 9-31 22-39l-9-5 9-18c21 8 30 25 24 42-2 7-8 11-17 12l-2 8z" />
            <circle className="piece-eye" cx="57" cy="31" r="3" />
            <path d="M24 79h53v11H24z" />
          </>
        )}
        {piece.type === "pawn" && (
          <>
            <circle cx="50" cy="30" r="15" />
            <path d="M38 44h24l8 35H30z" />
            <path d="M25 79h50v11H25z" />
          </>
        )}
      </g>
    </svg>
  );
}
