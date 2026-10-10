import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { pieceTranslations } from "./boardMotion";

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
  motionContext?: string;
  transitionMs?: number;
  bufferMs?: number;
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
  motionContext = "board",
  transitionMs = 300,
  bufferMs = 0,
}: ChessBoardProps) {
  const board = useRef<HTMLDivElement>(null);
  const previous = useRef({ fen, motionContext, flipped });
  const animations = useRef<Animation[]>([]);
  const interrupted = useRef(false);
  const dropped = useRef<{ from: string; to: string } | null>(null);
  const [moving, setMoving] = useState(false);
  const [reducedMotion, setReducedMotion] = useState(() => window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  useEffect(() => {
    const media = window.matchMedia("(prefers-reduced-motion: reduce)");
    const change = () => setReducedMotion(media.matches);
    media.addEventListener("change", change);
    return () => media.removeEventListener("change", change);
  }, []);
  useLayoutEffect(() => {
    const prior = previous.current;
    const superseded = interrupted.current;
    interrupted.current = false;
    previous.current = { fen, motionContext, flipped };
    setMoving(false);
    if (superseded || reducedMotion || !transitionMs || prior.motionContext !== motionContext || prior.flipped !== flipped) return;
    const shifts = pieceTranslations(prior.fen, fen, lastMove);
    const raised: HTMLElement[] = [];
    for (const shift of shifts) {
      // The pointer already carried this piece to its destination; do not replay it.
      if (dropped.current?.from === shift.from && dropped.current.to === shift.to) continue;
      const source = board.current?.querySelector<HTMLElement>(`[data-square="${shift.from}"]`);
      const target = board.current?.querySelector<HTMLElement>(`[data-square="${shift.to}"]`);
      const sprite = target?.querySelector<HTMLElement>(".piece-motion");
      if (!source || !target || !sprite) continue;
      const a = source.getBoundingClientRect(), b = target.getBoundingClientRect();
      target.style.zIndex = "5";
      raised.push(target);
      animations.current.push(sprite.animate([
        { transform: `translate(${a.x - b.x}px, ${a.y - b.y}px)` },
        { transform: "translate(0, 0)" },
      ], { duration: Math.min(500, transitionMs), delay: Math.min(600, bufferMs), easing: "cubic-bezier(.2,.7,.25,1)", fill: "both" }));
    }
    dropped.current = null;
    let cancelled = false;
    let finished = false;
    const pending = animations.current;
    if (pending.length) {
      setMoving(true);
      void Promise.all(pending.map(a => a.finished)).then(() => {
        finished = true;
        if (!cancelled) {
          pending.forEach(a => a.cancel());
          raised.forEach(el => { el.style.zIndex = ""; });
          setMoving(false);
        }
      }).catch(() => { /* Superseded position, lifecycle or preference. */ });
    }
    const size = board.current?.getBoundingClientRect();
    const resize = new ResizeObserver(() => {
      const current = board.current?.getBoundingClientRect();
      if (size && current && (size.width !== current.width || size.height !== current.height)) {
        finished = true;
        pending.forEach(a => a.cancel());
        raised.forEach(el => { el.style.zIndex = ""; });
        setMoving(false);
      }
    });
    if (board.current) resize.observe(board.current);
    return () => {
      cancelled = true;
      interrupted.current = pending.length > 0 && !finished;
      resize.disconnect();
      pending.forEach(a => a.cancel());
      animations.current = [];
      raised.forEach(el => { el.style.zIndex = ""; });
    };
  }, [fen, motionContext, flipped, reducedMotion, transitionMs, bufferMs, lastMove]);
  const pointer = useRef<{ id: number; from: string; key: string; x: number; y: number; moved: boolean } | null>(null);
  const suppressClick = useRef(false);
  const [dragFrom, setDragFrom] = useState<string | null>(null);
  const [dragOffset, setDragOffset] = useState({ x: 0, y: 0 });
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
      <div ref={board} className="board" role="grid" aria-label="Chess board" data-animating={moving}>
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
                if (!moving) onSquareClick(square.name);
              }}
              onPointerDown={(event) => {
                suppressClick.current = false;
                if (disabled || moving || !event.isPrimary || event.button !== 0 || square.piece?.color !== checkedKingColor) return;
                pointer.current = { id: event.pointerId, from: square.name, key: positionKey, x: event.clientX, y: event.clientY, moved: false };
                event.currentTarget.setPointerCapture(event.pointerId);
              }}
              onPointerMove={(event) => {
                const active = pointer.current;
                if (!active || active.id !== event.pointerId) return;
                if (Math.hypot(event.clientX - active.x, event.clientY - active.y) > 6) {
                  active.moved = true;
                  setDragFrom(active.from);
                  setDragOffset({ x: event.clientX - active.x, y: event.clientY - active.y });
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
                  dropped.current = { from: active.from, to: target.dataset.square! };
                  onMoveDrop(active.from, target.dataset.square!);
                }
              }}
              onPointerCancel={() => {
                pointer.current = null; setDragFrom(null); suppressClick.current = true;
              }}
              onLostPointerCapture={() => {
                pointer.current = null; setDragFrom(null);
              }}
              style={dragFrom === square.name ? { zIndex: 6 } : undefined}
              disabled={disabled || moving}
              aria-label={`${square.name}${square.piece ? ` ${square.piece.color} ${square.piece.type}` : " empty"}`}
            >
              {showRank && <span className="coordinate rank" aria-hidden="true">{square.rank}</span>}
              {showFile && <span className="coordinate file" aria-hidden="true">{square.file}</span>}
              {square.piece && (
                <span className="piece-motion" style={dragFrom === square.name ? { transform: `translate(${dragOffset.x}px, ${dragOffset.y}px)` } : undefined}>
                  <ChessPiece piece={square.piece} design={pieceDesign} />
                </span>
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
        <label>From<select aria-label="Move from square" disabled={disabled || moving} value={moveFrom}
          onChange={event => { setMoveFrom(event.target.value); setMoveTo(""); }}>
          <option value="">Choose</option>
          {[...new Set(legalMoves.map(move => move.slice(0, 2)))].sort().map(from => <option key={from}>{from}</option>)}
        </select></label>
        <label>To<select aria-label="Move to square" disabled={disabled || moving || !moveFrom} value={moveTo}
          onChange={event => setMoveTo(event.target.value)}>
          <option value="">Choose</option>
          {[...new Set(legalMoves.filter(move => move.startsWith(moveFrom)).map(move => move.slice(2, 4)))].sort().map(to => <option key={to}>{to}</option>)}
        </select></label>
        <button type="button" disabled={disabled || moving || !moveFrom || !moveTo} onClick={() => onMoveDrop(moveFrom, moveTo)}>Play move</button>
      </div>
    </details>}
    </div>
  );
}
