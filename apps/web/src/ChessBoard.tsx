import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { motionEasingCss, pieceTranslations, remainingFlight } from "./boardMotion";

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
  motionPly?: number;
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
  motionPly,
}: ChessBoardProps) {
  const board = useRef<HTMLDivElement>(null);
  const previous = useRef({ fen, motionContext, flipped, motionPly });
  const animations = useRef<Animation[]>([]);
  const flights = useRef(new Map<Animation, { square: string; x: number; y: number; delay: number; duration: number }>());
  // Unfinished flights from a superseded position, resumed rather than snapped.
  const carried = useRef<{ square: string; x: number; y: number; ms: number }[]>([]);
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
    const resumable = carried.current;
    carried.current = [];
    const dragged = dropped.current;
    dropped.current = null;
    previous.current = { fen, motionContext, flipped, motionPly };
    setMoving(false);
    if (reducedMotion || !transitionMs || prior.motionContext !== motionContext || prior.flipped !== flipped
      || (motionPly !== undefined && motionPly !== (prior.motionPly ?? motionPly) + 1)) return;
    const shifts = pieceTranslations(prior.fen, fen, lastMove);
    // A missed or non-adjacent position snaps; only one consecutive move may resume older flights.
    if (!shifts.length) return;
    const raised: HTMLElement[] = [];
    const fly = (square: string, x: number, y: number, delay: number, duration: number) => {
      const target = board.current?.querySelector<HTMLElement>(`[data-square="${square}"]`);
      const sprite = target?.querySelector<HTMLElement>(".piece-motion");
      if (!target || !sprite) return;
      target.style.zIndex = "5";
      raised.push(target);
      const animation = sprite.animate([
        { transform: `translate(${x}px, ${y}px)` },
        { transform: "translate(0, 0)" },
      ], { duration, delay, easing: motionEasingCss, fill: "both" });
      flights.current.set(animation, { square, x, y, delay, duration });
      animations.current.push(animation);
    };
    for (const shift of shifts) {
      // The pointer already carried this piece to its destination; do not replay it.
      if (dragged?.from === shift.from && dragged.to === shift.to) continue;
      const source = board.current?.querySelector<HTMLElement>(`[data-square="${shift.from}"]`);
      const target = board.current?.querySelector<HTMLElement>(`[data-square="${shift.to}"]`);
      if (!source || !target) continue;
      const a = source.getBoundingClientRect(), b = target.getBoundingClientRect();
      fly(shift.to, a.x - b.x, a.y - b.y, Math.min(600, bufferMs), Math.min(500, transitionMs));
    }
    const before = new Map(parseFen(prior.fen).map(s => [s.name, s.piece]));
    const after = new Map(parseFen(fen).map(s => [s.name, s.piece]));
    const touched = new Set(shifts.flatMap(s => [s.from, s.to]));
    for (const flight of resumable) {
      // Finish the earlier piece's remaining path from where it was drawn, unless this move displaced it.
      const was = before.get(flight.square), now = after.get(flight.square);
      if (touched.has(flight.square) || !was || was.type !== now?.type || was.color !== now.color) continue;
      fly(flight.square, flight.x, flight.y, 0, flight.ms);
    }
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
      if (!finished) {
        carried.current = pending.flatMap(animation => {
          const flight = flights.current.get(animation);
          const elapsed = Number(animation.currentTime ?? 0);
          if (!flight || animation.playState === "finished") return [];
          return [{ square: flight.square, ...remainingFlight(flight, elapsed, flight.delay, flight.duration) }];
        });
      }
      pending.forEach(a => flights.current.delete(a));
      resize.disconnect();
      pending.forEach(a => a.cancel());
      animations.current = [];
      raised.forEach(el => { el.style.zIndex = ""; });
    };
  }, [fen, motionContext, flipped, reducedMotion, transitionMs, bufferMs, lastMove, motionPly]);
  // Input never waits for decoration: touching the board lands every piece immediately.
  // Only live flights: finish() on a cancelled animation would revive it as a lingering frame.
  const settle = () => animations.current.forEach(a => {
    if (a.playState === "running" || a.playState === "paused") a.finish();
  });
  // Drag paints the sprite directly; React's own style (release hold or none) takes over afterwards.
  const clearDrag = (square: HTMLElement) => {
    const sprite = square.querySelector<HTMLElement>(".piece-motion");
    if (sprite) sprite.style.transform = "";
  };
  const pointer = useRef<{ id: number; from: string; key: string; x: number; y: number; moved: boolean } | null>(null);
  const suppressClick = useRef(false);
  const [dragFrom, setDragFrom] = useState<string | null>(null);
  const [dragOffset, setDragOffset] = useState({ x: 0, y: 0 });
  const [released, setReleased] = useState<{ from: string; key: string; x: number; y: number } | null>(null);
  useEffect(() => {
    if (!released) return;
    const timer = window.setTimeout(() => setReleased(null), 500);
    return () => window.clearTimeout(timer);
  }, [released]);
  useEffect(() => { setReleased(null); }, [positionKey, motionContext, flipped]);
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
      <div ref={board} className="board" role="grid" aria-label="Chess board" aria-busy={moving} data-animating={moving}>
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
                settle();
                onSquareClick(square.name);
              }}
              onPointerDown={(event) => {
                suppressClick.current = false;
                if (!event.isPrimary || event.button !== 0) return;
                settle();
                if (disabled || square.piece?.color !== checkedKingColor) return;
                pointer.current = { id: event.pointerId, from: square.name, key: positionKey, x: event.clientX, y: event.clientY, moved: false };
                event.currentTarget.setPointerCapture(event.pointerId);
              }}
              onPointerMove={(event) => {
                const active = pointer.current;
                if (!active || active.id !== event.pointerId) return;
                if (Math.hypot(event.clientX - active.x, event.clientY - active.y) > 6) {
                  active.moved = true;
                  setDragFrom(active.from);
                  const offset = { x: event.clientX - active.x, y: event.clientY - active.y };
                  // Paint now; waiting for React's render left the piece trailing the pointer.
                  const sprite = event.currentTarget.querySelector<HTMLElement>(".piece-motion");
                  if (sprite) sprite.style.transform = `translate(${offset.x}px, ${offset.y}px)`;
                  setDragOffset(offset);
                }
              }}
              onPointerUp={(event) => {
                const active = pointer.current;
                pointer.current = null;
                setDragFrom(null);
                clearDrag(event.currentTarget);
                if (!active || active.id !== event.pointerId || !active.moved) return;
                suppressClick.current = true;
                if (disabled || active.key !== positionKey) return;
                const target = document.elementFromPoint(event.clientX, event.clientY)?.closest<HTMLElement>("[data-square]");
                if (target && event.currentTarget.closest(".board")?.contains(target)) {
                  dropped.current = { from: active.from, to: target.dataset.square! };
                  if (legalMoves.some(move => move.startsWith(active.from + target.dataset.square))) {
                    setReleased({ from: active.from, key: positionKey, x: event.clientX - active.x, y: event.clientY - active.y });
                  }
                  onMoveDrop(active.from, target.dataset.square!);
                }
              }}
              onPointerCancel={(event) => {
                pointer.current = null; setDragFrom(null); clearDrag(event.currentTarget); suppressClick.current = true;
              }}
              onLostPointerCapture={(event) => {
                pointer.current = null; setDragFrom(null); clearDrag(event.currentTarget);
              }}
              style={dragFrom === square.name || (released?.key === positionKey && released.from === square.name) ? { zIndex: 6 } : undefined}
              disabled={disabled}
              aria-label={`${square.name}${square.piece ? ` ${square.piece.color} ${square.piece.type}` : " empty"}`}
            >
              {showRank && <span className="coordinate rank" aria-hidden="true">{square.rank}</span>}
              {showFile && <span className="coordinate file" aria-hidden="true">{square.file}</span>}
              {square.piece && (
                <span className="piece-motion" style={dragFrom === square.name ? { transform: `translate(${dragOffset.x}px, ${dragOffset.y}px)` }
                  : released?.key === positionKey && released.from === square.name ? { transform: `translate(${released.x}px, ${released.y}px)` } : undefined}>
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
        <button type="button" disabled={disabled || !moveFrom || !moveTo} onClick={() => { settle(); onMoveDrop(moveFrom, moveTo); }}>Play move</button>
      </div>
    </details>}
    </div>
  );
}
