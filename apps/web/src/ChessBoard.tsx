import { useMemo } from "react";

import { boardForOrientation, parseFen } from "./chess";
import { ChessPiece } from "./ChessPiece";

interface ChessBoardProps {
  fen: string;
  positionKey: string;
  flipped: boolean;
  legalMoves: string[];
  selected: string | null;
  lastMove: string | null;
  inCheck: boolean;
  disabled: boolean;
  onSquareClick: (square: string) => void;
  onMoveDrop: (from: string, to: string) => void;
  pieceDesign?: "current" | "classic";
}

export function ChessBoard({
  fen,
  positionKey,
  flipped,
  legalMoves,
  selected,
  lastMove,
  inCheck,
  disabled,
  onSquareClick,
  onMoveDrop,
  pieceDesign = "classic",
}: ChessBoardProps) {
  const squares = useMemo(
    () => boardForOrientation(parseFen(fen), flipped),
    [fen, flipped],
  );
  const legalTargets = selected
    ? new Set(legalMoves.filter((move) => move.startsWith(selected)).map((move) => move.slice(2, 4)))
    : new Set<string>();
  const lastSquares = lastMove ? new Set([lastMove.slice(0, 2), lastMove.slice(2, 4)]) : new Set<string>();
  const checkedKingColor = fen.split(" ")[1] === "b" ? "black" : "white";

  return (
    <div className="board-frame">
      <div className="board" role="grid" aria-label="Chess board">
        {squares.map((square, displayIndex) => {
          const showFile = displayIndex >= 56;
          const showRank = displayIndex % 8 === 0;
          const isSelected = selected === square.name;
          const isTarget = legalTargets.has(square.name);
          const isLast = lastSquares.has(square.name);
          const isCheckedKing =
            inCheck &&
            square.piece?.type === "king" &&
            square.piece.color === checkedKingColor;
          return (
            <button
              type="button"
              role="gridcell"
              className={`square ${square.dark ? "dark" : "light"} ${
                isSelected ? "selected" : ""
              } ${isTarget ? "legal-target" : ""} ${isLast ? "last-move" : ""} ${
                isCheckedKing ? "in-check" : ""
              }`}
              key={square.name}
              onClick={() => onSquareClick(square.name)}
              draggable={!disabled && square.piece?.color === checkedKingColor}
              onDragStart={(event) => {
                event.dataTransfer.setData("application/x-chess-move", JSON.stringify({ from: square.name, positionKey }));
                event.dataTransfer.effectAllowed = "move";
              }}
              onDragOver={(event) => {
                if (!disabled && event.dataTransfer.types.includes("application/x-chess-move")) event.preventDefault();
              }}
              onDrop={(event) => {
                event.preventDefault();
                if (disabled) return;
                try {
                  const source = JSON.parse(event.dataTransfer.getData("application/x-chess-move"));
                  if (source.positionKey === positionKey && typeof source.from === "string") onMoveDrop(source.from, square.name);
                } catch { /* Ignore unrelated or stale drag payloads. */ }
              }}
              disabled={disabled}
              aria-label={`${square.name}${square.piece ? ` ${square.piece.color} ${square.piece.type}` : " empty"}`}
            >
              {showRank && <span className="coordinate rank">{square.rank}</span>}
              {showFile && <span className="coordinate file">{square.file}</span>}
              {square.piece && (
                <ChessPiece piece={square.piece} design={pieceDesign} />
              )}
              {isTarget && !square.piece && <span className="target-dot" aria-hidden="true" />}
            </button>
          );
        })}
      </div>
    </div>
  );
}
