export interface BoardPiece {
  color: "white" | "black";
  type: "king" | "queen" | "rook" | "bishop" | "knight" | "pawn";
  symbol: string;
}

const pieceMap: Record<string, BoardPiece> = {
  K: { color: "white", type: "king", symbol: "♔" },
  Q: { color: "white", type: "queen", symbol: "♕" },
  R: { color: "white", type: "rook", symbol: "♖" },
  B: { color: "white", type: "bishop", symbol: "♗" },
  N: { color: "white", type: "knight", symbol: "♘" },
  P: { color: "white", type: "pawn", symbol: "♙" },
  k: { color: "black", type: "king", symbol: "♚" },
  q: { color: "black", type: "queen", symbol: "♛" },
  r: { color: "black", type: "rook", symbol: "♜" },
  b: { color: "black", type: "bishop", symbol: "♝" },
  n: { color: "black", type: "knight", symbol: "♞" },
  p: { color: "black", type: "pawn", symbol: "♟" },
};

export interface BoardSquare {
  name: string;
  file: string;
  rank: string;
  piece: BoardPiece | null;
  dark: boolean;
}

export function parseFen(fen: string): BoardSquare[] {
  const placement = fen.split(" ")[0];
  const rows = placement.split("/");
  const squares: BoardSquare[] = [];

  rows.forEach((row, rowIndex) => {
    let fileIndex = 0;
    for (const token of row) {
      if (/\d/.test(token)) {
        const emptySquares = Number(token);
        for (let offset = 0; offset < emptySquares; offset += 1) {
          const file = String.fromCharCode(97 + fileIndex);
          const rank = String(8 - rowIndex);
          squares.push({
            name: `${file}${rank}`,
            file,
            rank,
            piece: null,
            dark: (fileIndex + rowIndex) % 2 === 1,
          });
          fileIndex += 1;
        }
        continue;
      }
      const file = String.fromCharCode(97 + fileIndex);
      const rank = String(8 - rowIndex);
      squares.push({
        name: `${file}${rank}`,
        file,
        rank,
        piece: pieceMap[token] ?? null,
        dark: (fileIndex + rowIndex) % 2 === 1,
      });
      fileIndex += 1;
    }
    while (fileIndex < 8) {
      const file = String.fromCharCode(97 + fileIndex);
      const rank = String(8 - rowIndex);
      squares.push({
        name: `${file}${rank}`,
        file,
        rank,
        piece: null,
        dark: (fileIndex + rowIndex) % 2 === 1,
      });
      fileIndex += 1;
    }
  });
  return squares;
}

export function boardForOrientation(squares: BoardSquare[], flipped: boolean): BoardSquare[] {
  return flipped ? [...squares].reverse() : squares;
}

export function pairMoves(moves: { ply: number; san: string }[]): Array<{
  number: number;
  white?: string;
  black?: string;
}> {
  const rows: Array<{ number: number; white?: string; black?: string }> = [];
  for (const move of moves) {
    const number = Math.ceil(move.ply / 2);
    let row = rows.find((candidate) => candidate.number === number);
    if (!row) {
      row = { number };
      rows.push(row);
    }
    if (move.ply % 2 === 1) row.white = move.san;
    else row.black = move.san;
  }
  return rows;
}
