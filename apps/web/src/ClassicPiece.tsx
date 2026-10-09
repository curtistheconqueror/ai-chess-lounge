import type { BoardPiece } from "./chess";

// Original paths drawn for the Lounge. No third-party piece assets or tracing.
// Shared 100-unit canvas, outline and stepped pedestal across the whole set.
export function ClassicPiece({ piece }: { piece: BoardPiece }) {
  const small = piece.type === "pawn";
  return <svg className={`piece-svg classic-piece ${piece.color}`} viewBox="0 0 100 100"
    role="img" aria-label={`${piece.color} ${piece.type}`}>
    <g className="classic-shape">
      {piece.type === "king" && <>
        <path d="M46 7h8v10h10v8H54v12h-8V25H36v-8h10z" />
        <path d="M30 39Q50 31 70 39L63 51H37Z" />
        <path d="M38 51h24Q60 68 70 78H30Q40 68 38 51Z" />
        <path className="classic-line" d="M36 56h28" />
      </>}
      {piece.type === "queen" && <>
        <path d="M25 32 36 43 40 24 50 39 60 24 64 43 75 32 67 57H33Z" />
        <circle cx="25" cy="29" r="3.5" /><circle cx="40" cy="21" r="3.5" />
        <circle cx="60" cy="21" r="3.5" /><circle cx="75" cy="29" r="3.5" />
        <path d="M35 57h30Q58 69 70 78H30Q42 69 35 57Z" />
        <path className="classic-line" d="M34 53h32" />
      </>}
      {piece.type === "rook" && <>
        <path d="M25 25h12v11h7V25h12v11h7V25h12v23H25Z" />
        <path d="M33 48h34L64 70 71 78H29L36 70Z" />
        <path className="classic-line" d="M34 54h32M35 70h30" />
      </>}
      {piece.type === "bishop" && <>
        <path d="M50 19C41 28 31 37 33 46Q35 57 50 60Q65 57 67 46C68 40 64 34 60 30L48 43 43 39 55 25Z" />
        <circle cx="50" cy="15" r="4" />
        <path d="M42 59h16L61 68 70 78H30L39 68Z" />
        <path className="classic-line" d="M38 65h24" />
      </>}
      {piece.type === "knight" && <>
        <path d="M29 78C31 63 40 55 52 47Q45 47 39 42L30 48Q24 50 20 44L18 39Q27 29 42 22L47 10 56 19C72 22 82 38 80 57Q80 69 74 78Z" />
        <path className="classic-line classic-mane" d="M59 26Q75 37 72 57Q71 65 67 71" />
        <path className="classic-line" d="m23 40 6 1" />
        <circle className="classic-eye" cx="44" cy="30" r="1.8" />
      </>}
      {small && <>
        <circle cx="50" cy="35" r="11.5" />
        <path d="M40 47h20v7H40Z" />
        <path d="M43 54h14Q56 67 65 78H35Q44 67 43 54Z" />
      </>}
      <path d={small ? "M33 78h34l4 6H29Z" : "M28 78h44l5 6H23Z"} />
      <path d={small ? "M29 84h42v7H29Z" : "M23 84h54v7H23Z"} />
    </g>
  </svg>;
}
