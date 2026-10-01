import { useMemo } from "react";

import { boardForOrientation, parseFen } from "./chess";

interface ChessBoardProps {
  fen: string;
  flipped: boolean;
  legalMoves: string[];
  selected: string | null;
  lastMove: string | null;
  disabled: boolean;
  onSquareClick: (square: string) => void;
}

export function ChessBoard({
  fen,
  flipped,
  legalMoves,
  selected,
  lastMove,
  disabled,
  onSquareClick,
}: ChessBoardProps) {
  const squares = useMemo(
    () => boardForOrientation(parseFen(fen), flipped),
    [fen, flipped],
  );
  const legalTargets = selected
    ? new Set(legalMoves.filter((move) => move.startsWith(selected)).map((move) => move.slice(2, 4)))
    : new Set<string>();
  const lastSquares = lastMove ? new Set([lastMove.slice(0, 2), lastMove.slice(2, 4)]) : new Set<string>();

  return (
    <div className="board-frame">
      <div className="board" role="grid" aria-label="Chess board">
        {squares.map((square, displayIndex) => {
          const showFile = displayIndex >= 56;
          const showRank = displayIndex % 8 === 0;
          const isSelected = selected === square.name;
          const isTarget = legalTargets.has(square.name);
          const isLast = lastSquares.has(square.name);
          return (
            <button
              type="button"
              role="gridcell"
              className={`square ${square.dark ? "dark" : "light"} ${
                isSelected ? "selected" : ""
              } ${isTarget ? "legal-target" : ""} ${isLast ? "last-move" : ""}`}
              key={square.name}
              onClick={() => onSquareClick(square.name)}
              disabled={disabled}
              aria-label={`${square.name}${square.piece ? ` ${square.piece.color} ${square.piece.type}` : " empty"}`}
            >
              {showRank && <span className="coordinate rank">{square.rank}</span>}
              {showFile && <span className="coordinate file">{square.file}</span>}
              {square.piece && (
                <span className={`piece ${square.piece.color}`} aria-hidden="true">
                  {square.piece.symbol}
                </span>
              )}
              {isTarget && !square.piece && <span className="target-dot" aria-hidden="true" />}
            </button>
          );
        })}
      </div>
    </div>
  );
}
