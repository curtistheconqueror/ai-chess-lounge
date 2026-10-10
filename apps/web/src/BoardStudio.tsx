import { useState } from "react";
import { ChessBoard } from "./ChessBoard";
import { PieceComparison } from "./PieceComparison";

const looks = [
  { id: "club", number: 1, name: "Current club", description: "The existing ivory and green board, kept as the baseline." },
  { id: "wood", number: 2, name: "Warm wood", description: "Maple and walnut tones with a quiet grain and a solid frame." },
  { id: "glass", number: 3, name: "Frosted glass", description: "Cool, matte glass colors with restrained highlights. Opaque squares keep pieces clear." },
  { id: "metal", number: 4, name: "Brushed metal", description: "Satin silver and slate with a subtle brushed finish, without mirror glare." },
];
const start = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";
const middle = "r1bq1rk1/ppp2ppp/2np1n2/2b1p3/2B1P3/2NP1N2/PPP2PPP/R1BQ1RK1 w - - 4 6";

export function BoardStudio() {
  const [comparePieces, setComparePieces] = useState(() => new URLSearchParams(location.search).has("pieces"));
  const [flipped, setFlipped] = useState(false);
  const [position, setPosition] = useState("middle");
  const [highlights, setHighlights] = useState(true);
  return <main className="board-studio app-shell">
    <header className="sound-lab-heading">
      <div><p className="eyebrow">AI CHESS LOUNGE · BOARD STUDIO</p>
        <h1>Choose the board's feel.</h1>
        <p>Four finishes. The same pieces, position and size in every preview.</p></div>
      <a className="ghost-button" href="/">Back to the board</a>
    </header>
    <nav className="board-studio-controls" aria-label="Comparison category">
      <button className="ghost-button" aria-pressed={!comparePieces} onClick={() => setComparePieces(false)}>Board finishes</button>
      <button className="ghost-button" aria-pressed={comparePieces} onClick={() => setComparePieces(true)}>Previous vs approved pieces</button>
    </nav>
    {comparePieces ? <PieceComparison /> : <>
    <section className="board-studio-controls" aria-label="Visual comparison controls">
      <label>Position <select aria-label="Comparison position" value={position} onChange={event => setPosition(event.target.value)}>
        <option value="middle">Middlegame</option><option value="start">Starting position</option>
      </select></label>
      <button className="ghost-button" aria-pressed={flipped} onClick={() => setFlipped(value => !value)}>Flip all boards</button>
      <label><input type="checkbox" checked={highlights} onChange={event => setHighlights(event.target.checked)} /> Show move highlights</label>
    </section>
    <p className="sound-lab-note">Board finish previews only. The live board keeps its current colors and uses the approved classic pieces. Choose a finish after comparing piece clarity and coordinates.</p>
    <div className="board-comparison-grid">
      {looks.map(look => <section className={`board-look board-look-${look.id}`} key={look.id} aria-label={`Look ${look.number}: ${look.name}`}>
        <div className="sound-card-top"><span className="eyebrow">LOOK {look.number}</span>
          <span className="sound-default">{look.id === "club" ? "CURRENT" : "PREVIEW"}</span></div>
        <h2>{look.name}</h2><p>{look.description}</p>
        <ChessBoard fen={position === "start" ? start : middle} positionKey={position} flipped={flipped}
          legalMoves={highlights ? (position === "start" ? ["g1f3", "g1h3"] : ["c3b5", "c3d5", "c3a4", "c3e2"]) : []}
          selected={highlights ? (position === "start" ? "g1" : "c3") : null}
          lastMove={highlights && position !== "start" ? "f8c5" : null}
          inCheck={false} disabled={true} onSquareClick={() => {}} onMoveDrop={() => {}} />
      </section>)}
    </div>
    </>}
    <p className="sound-lab-note">The selected original wood tap stays the same for every look. These previews do not start games or change your audio device.</p>
    <a className="sound-lab-link" href="/sound-lab">Open sound comparison</a>
  </main>;
}
