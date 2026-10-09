import { useState } from "react";
import { ChessBoard } from "./ChessBoard";
import { ChessPiece } from "./ChessPiece";
import type { BoardPiece } from "./chess";

const types: BoardPiece["type"][] = ["king", "queen", "rook", "bishop", "knight", "pawn"];
const colors: BoardPiece["color"][] = ["white", "black"];
const starting = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";

export function PieceComparison() {
  const [finish, setFinish] = useState("club");
  const [silhouette, setSilhouette] = useState(false);
  return <section className={`piece-comparison ${silhouette ? "silhouette-review" : ""}`} aria-label="Piece design comparison">
    <h2>A clearer classic set.</h2>
    <p className="sound-lab-note">Original vector artwork for review. A horse-profile knight, distinct crowns and a readable bishop slit. The live game still uses the current set.</p>
    <div className="board-studio-controls">
      <label>Board finish <select aria-label="Piece comparison finish" value={finish} onChange={e => setFinish(e.target.value)}>
        <option value="club">Current club</option><option value="wood">Warm wood</option>
        <option value="glass">Frosted glass</option><option value="metal">Brushed metal</option>
      </select></label>
      <label><input type="checkbox" checked={silhouette} onChange={e => setSilhouette(e.target.checked)} /> Silhouette check</label>
    </div>
    <div className="board-comparison-grid piece-boards">
      {(["current", "classic"] as const).map(design => <section className={`board-look board-look-${finish}`} key={design}
        aria-label={design === "current" ? "Current pieces" : "Proposed pieces"}>
        <p className="eyebrow">{design === "current" ? "CURRENT" : "PROPOSED · ORIGINAL SVG"}</p>
        <h3>{design === "current" ? "Existing pieces" : "Classic profile"}</h3>
        <ChessBoard fen={starting} positionKey="piece-review" flipped={false} legalMoves={[]} selected={null}
          lastMove={null} inCheck={false} disabled onSquareClick={() => {}} onMoveDrop={() => {}} pieceDesign={design} />
      </section>)}
    </div>
    <h3>Small-size clarity</h3>
    <p className="sound-lab-note">All twelve proposed pieces on light and dark squares, at 32, 40 and 64 pixels. Silhouette check hides the eye and internal lines.</p>
    <div className="piece-specimens">
      {([32, 40, 64] as const).map(size => <section className={`specimen-size board-look-${finish}`} key={size} aria-label={`${size} pixel pieces`}>
        <h4>{size} px</h4>
        {colors.map(color => <div className="specimen-row" key={color}>
          {types.map(type => <div className="specimen-pair" key={type}>
            <div className="specimen-squares">{(["light", "dark"] as const).map(square => <div className={`specimen-square ${square}`} key={square}>
              <span style={{ width: size, height: size }}><ChessPiece piece={{ color, type, symbol: "" }} design="classic" /></span>
            </div>)}</div><small>{color} {type}</small>
          </div>)}
        </div>)}
      </section>)}
    </div>
  </section>;
}
