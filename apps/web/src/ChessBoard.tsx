import { useEffect, useMemo, useRef, useState } from "react";

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
  showSquareEntry?: boolean;
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
  showSquareEntry = false,
}: ChessBoardProps) {
  const pointer = useRef<{ id: number; from: string; key: string; x: number; y: number; moved: boolean } | null>(null);
  const suppressClick = useRef(false);
  const [dragFrom, setDragFrom] = useState<string | null>(null);
  const [moveFrom, setMoveFrom] = useState("");
  const [moveTo, setMoveTo] = useState("");
  useEffect(() => {
    pointer.current = null;
    setDragFrom(null);
    setMoveFrom("");
    setMoveTo("");
  }, [positionKey, disabled, flipped]);
  const squares = useMemo(
    () => boardForOrientation(parseFen(fen), flipped),
    [fen, flipped],
  );
  const activeSquare = dragFrom ?? selected;
  const legalTargets = activeSquare
    ? new Set(legalMoves.filter((move) => move.startsWith(activeSquare)).map((move) => move.slice(2, 4)))
    : new Set<string>();
  const lastSquares = lastMove ? new Set([lastMove.slice(0, 2), lastMove.slice(2, 4)]) : new Set<string>();
  const checkedKingColor = fen.split(" ")[1] === "b" ? "black" : "white";

  return (
    <div className="board-input">
    <div className="board-frame">
      <div className="board" role="grid" aria-label="Chess board">
        {Array.from({ length: 8 }, (_, row) => <div role="row" className="board-row" key={row}>
        {squares.slice(row * 8, row * 8 + 8).map((square, column) => {
          const displayIndex = row * 8 + column;
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
              data-square={square.name}
              onClick={() => {
                if (suppressClick.current) { suppressClick.current = false; return; }
                onSquareClick(square.name);
              }}
              onPointerDown={(event) => {
                suppressClick.current = false;
                if (disabled || !event.isPrimary || event.button !== 0 || square.piece?.color !== checkedKingColor) return;
                pointer.current = { id: event.pointerId, from: square.name, key: positionKey, x: event.clientX, y: event.clientY, moved: false };
                event.currentTarget.setPointerCapture(event.pointerId);
              }}
              onPointerMove={(event) => {
                const active = pointer.current;
                if (!active || active.id !== event.pointerId) return;
                if (Math.hypot(event.clientX - active.x, event.clientY - active.y) > 6) {
                  active.moved = true;
                  setDragFrom(active.from);
                }
              }}
              onPointerUp={(event) => {
                const active = pointer.current;
                pointer.current = null;
                setDragFrom(null);
                if (!active || active.id !== event.pointerId || !active.moved) return;
                suppressClick.current = true;
                if (disabled || active.key !== positionKey) return;
                const target = document.elementFromPoint(event.clientX, event.clientY)?.closest<HTMLElement>("[data-square]");
                if (target && event.currentTarget.closest(".board")?.contains(target)) {
                  onMoveDrop(active.from, target.dataset.square!);
                }
              }}
              onPointerCancel={() => {
                pointer.current = null; setDragFrom(null); suppressClick.current = true;
              }}
              onLostPointerCapture={() => {
                pointer.current = null; setDragFrom(null);
              }}
              disabled={disabled}
              aria-label={`${square.name}${square.piece ? ` ${square.piece.color} ${square.piece.type}` : " empty"}`}
            >
              {showRank && <span className="coordinate rank" aria-hidden="true">{square.rank}</span>}
              {showFile && <span className="coordinate file" aria-hidden="true">{square.file}</span>}
              {square.piece && (
                <ChessPiece piece={square.piece} design={pieceDesign} />
              )}
              {isTarget && !square.piece && <span className="target-dot" aria-hidden="true" />}
            </button>
          );
        })}</div>)}
      </div>
    </div>
    {showSquareEntry && <details className="square-entry">
      <summary>Move by square</summary>
      <p>Tap two squares, drag a piece, or use these larger controls.</p>
      <div>
        <label>From<select aria-label="Move from square" disabled={disabled} value={moveFrom}
          onChange={event => { setMoveFrom(event.target.value); setMoveTo(""); }}>
          <option value="">Choose</option>
          {[...new Set(legalMoves.map(move => move.slice(0, 2)))].sort().map(from => <option key={from}>{from}</option>)}
        </select></label>
        <label>To<select aria-label="Move to square" disabled={disabled || !moveFrom} value={moveTo}
          onChange={event => setMoveTo(event.target.value)}>
          <option value="">Choose</option>
          {[...new Set(legalMoves.filter(move => move.startsWith(moveFrom)).map(move => move.slice(2, 4)))].sort().map(to => <option key={to}>{to}</option>)}
        </select></label>
        <button type="button" disabled={disabled || !moveFrom || !moveTo} onClick={() => onMoveDrop(moveFrom, moveTo)}>Play move</button>
      </div>
    </details>}
    </div>
  );
}
