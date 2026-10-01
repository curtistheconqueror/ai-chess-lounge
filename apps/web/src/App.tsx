import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { createGame, fetchGame, resignGame, resetGame, submitMove, websocketUrl } from "./api";
import { pairMoves, parseFen } from "./chess";
import { ChessBoard } from "./ChessBoard";
import type { GameSnapshot } from "./types";

type PanelTab = "moves" | "pgn" | "fen";

const savedGameKey = "ai-chess-lounge:active-game";

function App() {
  const [game, setGame] = useState<GameSnapshot | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [flipped, setFlipped] = useState(false);
  const [stockfishElo, setStockfishElo] = useState(1600);
  const [panelTab, setPanelTab] = useState<PanelTab>("moves");
  const [replayPly, setReplayPly] = useState<number | null>(null);
  const [connection, setConnection] = useState<"connecting" | "live" | "offline">("connecting");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const socketRef = useRef<WebSocket | null>(null);
  const initialEloRef = useRef(stockfishElo);

  const acceptSnapshot = useCallback((snapshot: GameSnapshot) => {
    setGame(snapshot);
    setSelected(null);
    setReplayPly((current) => (current === null ? null : Math.min(current, snapshot.moves.length)));
    localStorage.setItem(savedGameKey, snapshot.id);
  }, []);

  const startNewGame = useCallback(async () => {
    setBusy(true);
    setNotice(null);
    try {
      acceptSnapshot(await createGame(stockfishElo));
      setReplayPly(null);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Unable to create game.");
    } finally {
      setBusy(false);
    }
  }, [acceptSnapshot, stockfishElo]);

  useEffect(() => {
    let cancelled = false;
    async function restore() {
      const stored = localStorage.getItem(savedGameKey);
      if (stored) {
        try {
          const snapshot = await fetchGame(stored);
          if (!cancelled) acceptSnapshot(snapshot);
          return;
        } catch {
          localStorage.removeItem(savedGameKey);
        }
      }
      if (!cancelled) {
        setBusy(true);
        try {
          acceptSnapshot(await createGame(initialEloRef.current));
        } catch (error) {
          setNotice(error instanceof Error ? error.message : "Unable to create game.");
        } finally {
          setBusy(false);
        }
      }
    }
    const timer = window.setTimeout(() => void restore(), 0);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [acceptSnapshot]);

  useEffect(() => {
    if (!game?.id) return;
    socketRef.current?.close();
    setConnection("connecting");
    const socket = new WebSocket(websocketUrl(game.id));
    socketRef.current = socket;
    socket.addEventListener("open", () => setConnection("live"));
    socket.addEventListener("close", () => setConnection("offline"));
    socket.addEventListener("error", () => setConnection("offline"));
    socket.addEventListener("message", (event) => {
      try {
        const message = JSON.parse(event.data) as { type: string; payload: GameSnapshot };
        if (message.type === "snapshot") acceptSnapshot(message.payload);
      } catch {
        setNotice("A live update could not be read.");
      }
    });
    return () => socket.close();
  }, [game?.id, acceptSnapshot]);

  const displayFen = useMemo(() => {
    if (!game || replayPly === null || replayPly === game.moves.length) return game?.fen ?? "";
    if (replayPly === 0) return game.initial_fen;
    return game.moves[replayPly - 1]?.fen ?? game.fen;
  }, [game, replayPly]);

  const displayLastMove = useMemo(() => {
    if (!game) return null;
    if (replayPly === null) return game.last_move;
    return replayPly > 0 ? game.moves[replayPly - 1]?.uci ?? null : null;
  }, [game, replayPly]);

  const moveRows = useMemo(() => pairMoves(game?.moves ?? []), [game?.moves]);
  const atLive = replayPly === null || replayPly === game?.moves.length;
  const playerCanMove = Boolean(game?.can_move && atLive && !busy);

  async function onSquareClick(square: string) {
    if (!game || !playerCanMove) return;
    const boardSquare = parseFen(game.fen).find((candidate) => candidate.name === square);
    if (!selected) {
      if (boardSquare?.piece?.color === "white") setSelected(square);
      return;
    }
    if (boardSquare?.piece?.color === "white") {
      setSelected(square);
      return;
    }
    const candidates = game.legal_moves.filter(
      (move) => move.startsWith(selected) && move.slice(2, 4) === square,
    );
    if (!candidates.length) {
      setSelected(null);
      return;
    }
    let move = candidates[0];
    if (candidates.some((candidate) => candidate.length === 5)) {
      const promotion = window.prompt("Promote to queen, rook, bishop, or knight?", "queen") ?? "queen";
      const piece = { queen: "q", rook: "r", bishop: "b", knight: "n" }[
        promotion.toLowerCase() as "queen" | "rook" | "bishop" | "knight"
      ] ?? "q";
      move = `${selected}${square}${piece}`;
    }
    setSelected(null);
    setBusy(true);
    setNotice(null);
    try {
      acceptSnapshot(await submitMove(game.id, move, game.version));
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Move failed.");
      try {
        acceptSnapshot(await fetchGame(game.id));
      } catch {
        // Preserve the original error if refresh also fails.
      }
    } finally {
      setBusy(false);
    }
  }

  async function copyText(value: string, label: string) {
    await navigator.clipboard.writeText(value);
    setNotice(`${label} copied.`);
    window.setTimeout(() => setNotice(null), 1600);
  }

  async function onReset() {
    if (!game) return;
    setBusy(true);
    try {
      acceptSnapshot(await resetGame(game.id));
      setReplayPly(null);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Reset failed.");
    } finally {
      setBusy(false);
    }
  }

  async function onResign() {
    if (!game || game.status !== "active") return;
    setBusy(true);
    try {
      acceptSnapshot(await resignGame(game.id));
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Resign failed.");
    } finally {
      setBusy(false);
    }
  }

  const engineLabel = game?.engine?.version ?? game?.engine?.name ?? "Stockfish";
  const replayLabel = replayPly === null ? game?.moves.length ?? 0 : replayPly;

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand-lockup">
          <div className="brand-mark" aria-hidden="true">♞</div>
          <div>
            <p className="eyebrow">LIVE INTELLIGENCE ARENA</p>
            <h1>AI Chess Lounge</h1>
          </div>
        </div>
        <div className="topbar-actions">
          <span className={`connection ${connection}`}>
            <span className="connection-dot" /> {connection}
          </span>
          <button className="ghost-button" onClick={() => setFlipped((value) => !value)}>
            Flip board
          </button>
        </div>
      </header>

      <section className="arena-layout">
        <div className="match-stage">
          <PlayerCard
            side="black"
            title={engineLabel}
            subtitle={`Engine · target ${game?.engine?.target_elo ?? stockfishElo} Elo`}
            badge={game?.turn === "black" && game?.status === "active" ? "THINKING" : "BLACK"}
            active={game?.turn === "black" && game?.status === "active"}
          />

          <div className="strategy-banner" role="status">
            <div className="strategy-icon">◇</div>
            <div>
              <span>Strategy channel</span>
              <strong>{game?.strategy_banner ?? "Preparing the board…"}</strong>
            </div>
          </div>

          <ChessBoard
            fen={displayFen || "8/8/8/8/8/8/8/8 w - - 0 1"}
            flipped={flipped}
            legalMoves={atLive ? game?.legal_moves ?? [] : []}
            selected={selected}
            lastMove={displayLastMove}
            disabled={!playerCanMove}
            onSquareClick={(square) => void onSquareClick(square)}
          />

          <PlayerCard
            side="white"
            title="CurtisTheConqueror"
            subtitle="Human seat · White"
            badge={game?.turn === "white" && game?.status === "active" ? "YOUR MOVE" : "WHITE"}
            active={game?.turn === "white" && game?.status === "active"}
          />

          <div className="playback-bar">
            <button
              aria-label="First position"
              onClick={() => setReplayPly(0)}
              disabled={!game?.moves.length}
            >
              |◀
            </button>
            <button
              aria-label="Previous move"
              onClick={() => setReplayPly(Math.max(0, (replayPly ?? game?.moves.length ?? 0) - 1))}
              disabled={!game?.moves.length}
            >
              ◀
            </button>
            <span>
              Position <strong>{replayLabel}</strong> / {game?.moves.length ?? 0}
            </span>
            <button
              aria-label="Next move"
              onClick={() => {
                if (!game) return;
                const next = Math.min(game.moves.length, (replayPly ?? game.moves.length) + 1);
                setReplayPly(next === game.moves.length ? null : next);
              }}
              disabled={atLive}
            >
              ▶
            </button>
            <button aria-label="Jump to live" onClick={() => setReplayPly(null)} disabled={atLive}>
              LIVE
            </button>
          </div>
        </div>

        <aside className="control-deck">
          <div className="match-header">
            <div>
              <p className="eyebrow">EXHIBITION TABLE 01</p>
              <h2>Human vs Stockfish</h2>
            </div>
            <span className={`result-badge ${game?.status ?? "loading"}`}>
              {game?.status === "active" ? "LIVE" : game?.result ?? "LOADING"}
            </span>
          </div>

          <div className="match-controls">
            <label>
              Engine strength
              <select value={stockfishElo} onChange={(event) => setStockfishElo(Number(event.target.value))}>
                <option value={1320}>1320 · Club entry</option>
                <option value={1600}>1600 · Strong club</option>
                <option value={2000}>2000 · Expert</option>
                <option value={2500}>2500 · Grandmaster+</option>
                <option value={3190}>Maximum · Brutal</option>
              </select>
            </label>
            <button className="primary-button" onClick={() => void startNewGame()} disabled={busy}>
              New match
            </button>
          </div>

          <div className="panel-tabs" role="tablist">
            {(["moves", "pgn", "fen"] as const).map((tab) => (
              <button
                key={tab}
                role="tab"
                aria-selected={panelTab === tab}
                className={panelTab === tab ? "active" : ""}
                onClick={() => setPanelTab(tab)}
              >
                {tab.toUpperCase()}
              </button>
            ))}
          </div>

          <div className="panel-content">
            {panelTab === "moves" && (
              <div className="move-list">
                {!moveRows.length && <div className="empty-state">The opening move is yours.</div>}
                {moveRows.map((row) => (
                  <div className="move-row" key={row.number}>
                    <span>{row.number}.</span>
                    <button onClick={() => setReplayPly(row.number * 2 - 1)}>{row.white ?? "—"}</button>
                    <button
                      onClick={() => setReplayPly(row.black ? row.number * 2 : row.number * 2 - 1)}
                    >
                      {row.black ?? "…"}
                    </button>
                  </div>
                ))}
              </div>
            )}
            {panelTab === "pgn" && (
              <div className="notation-panel">
                <pre>{game?.pgn ?? "No game loaded."}</pre>
                <button onClick={() => void copyText(game?.pgn ?? "", "PGN")}>Copy PGN</button>
              </div>
            )}
            {panelTab === "fen" && (
              <div className="notation-panel">
                <pre>{displayFen}</pre>
                <button onClick={() => void copyText(displayFen, "FEN")}>Copy FEN</button>
              </div>
            )}
          </div>

          <div className="telemetry-grid">
            <Metric label="Ply" value={String(game?.moves.length ?? 0)} />
            <Metric
              label="Engine latency"
              value={
                game?.moves.filter((move) => move.actor.startsWith("stockfish")).at(-1)?.elapsed_ms
                  ? `${game.moves.filter((move) => move.actor.startsWith("stockfish")).at(-1)?.elapsed_ms} ms`
                  : "—"
              }
            />
            <Metric label="Position version" value={String(game?.version ?? 0)} />
            <Metric label="Event sequence" value={String(game?.event_sequence ?? 0)} />
            <Metric label="Lifecycle" value={(game?.lifecycle ?? "loading").toUpperCase()} accent />
            <Metric label="Storage" value="DURABLE" accent />
          </div>

          <div className="secondary-actions">
            <button onClick={() => void onReset()} disabled={!game || busy}>Reset board</button>
            <button onClick={() => void onResign()} disabled={!game || busy || game.status !== "active"}>
              Resign
            </button>
            <button onClick={() => game && void copyText(window.location.href, "Lounge link")}>Copy link</button>
          </div>

          <div className="integrity-note">
            <span>SERVER AUTHORITY</span>
            Every move is validated before it reaches the board. FEN, PGN, result, and replay all derive from the same position history.
          </div>
        </aside>
      </section>

      {notice && <div className="toast" role="alert">{notice}</div>}
    </main>
  );
}

function PlayerCard({
  side,
  title,
  subtitle,
  badge,
  active,
}: {
  side: "white" | "black";
  title: string;
  subtitle: string;
  badge: string;
  active: boolean;
}) {
  return (
    <div className={`player-card ${active ? "active" : ""}`}>
      <div className={`player-avatar ${side}`}>{side === "white" ? "♔" : "♚"}</div>
      <div className="player-copy">
        <strong>{title}</strong>
        <span>{subtitle}</span>
      </div>
      <span className="player-badge">{badge}</span>
    </div>
  );
}

function Metric({ label, value, accent = false }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong className={accent ? "accent" : ""}>{value}</strong>
    </div>
  );
}

export default App;
