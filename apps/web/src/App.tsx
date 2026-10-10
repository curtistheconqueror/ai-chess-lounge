import { StockfishStrength, readStockfishChoice, stockfishChoiceKey, useStockfishCapabilities, validStrength, type StockfishChoice } from "./StockfishStrength";
import { Leaderboards } from "./Leaderboards";
import { IdentityEditor } from "./IdentityEditor";
import type { IdentityDeclaration } from "./types";
import { ModelLab } from "./ModelLab";
import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from "react";

import {
  ApiRequestError,
  abortGame,
  adjudicateGame,
  claimDraw,
  changeSeat,
  controlMatch,
  createGame,
  createRunnerPairing,
  fetchAnalysis,
  fetchGame,
  fetchGameEvents,
  fetchLiveMatch,
  fetchPlayerAdapters,
  fetchRunnerSessions,
  revokeRunnerSession,
  resignGame,
  resetGame,
  retryAgentTurn,
  submitMove,
  suggestToAgent,
  websocketUrl,
} from "./api";
import { pairMoves, parseFen } from "./chess";
import { ConsultationPanel } from "./ConsultationPanel";
import { SeatTakeoverDialog } from "./SeatTakeoverDialog";
import { HumanActionDialog } from "./HumanActionDialog";
import { MatchActionDialog, type AdjudicatedResult, type MatchAction } from "./MatchActionDialog";
import { GameUsage } from "./GameUsage";
import { ChessBoard } from "./ChessBoard";
import { BoardSoundControls, useBoardSound } from "./BoardSoundControls";
import { newMoveSound } from "./boardSound";
import { EvaluationChart } from "./EvaluationChart";
import { PromotionPicker, type PromotionPiece } from "./PromotionPicker";
import type {
  AnalysisPoint,
  AdapterModelCapabilities,
  EffortLevel,
  GameAnalysis,
  GameSnapshot,
  MatchEvent,
  PlayerAdapterCatalog,
  PlayerConfiguration,
  RunnerPairingResponse,
  RunnerSessionStatus,
} from "./types";

type PanelTab = "moves" | "analysis" | "pgn" | "fen";
type TimeControlKey = "1+0" | "3+2" | "5+2" | "10+5";
type AgentProviderChoice =
  | "openai"
  | "anthropic"
  | "google"
  | "openrouter"
  | "ollama"
  | "vllm";
type SeatChoice = "human" | "stockfish" | "scripted" | "remote_runner" | AgentProviderChoice;
type RunnerConnectionMode = "remote_runner" | "subscription_bridge";
const wrappedCodeStyle: CSSProperties = {
  maxWidth: "100%",
  overflow: "visible",
  overflowWrap: "anywhere",
  textOverflow: "clip",
  whiteSpace: "normal",
};
type ClockSync = { gameId: string; generation: number; revision: number; receivedAt: number };
type PromotionRequest = { from: string; to: string; candidates: string[]; gameId: string; version: number; color: "white" | "black" };
type Color = "white" | "black";
interface PlayerCardProps {
  side: "white" | "black";
  title: string;
  provider: string;
  configuration: string;
  division: string;
  cost: string;
  latency: string;
  badge: string;
  active: boolean;
  clock: string;
  urgent: boolean;
}

const timeControls: Record<
  TimeControlKey,
  { label: string; initialTimeMs: number; incrementMs: number }
> = {
  "1+0": { label: "1 + 0 · Bullet", initialTimeMs: 60_000, incrementMs: 0 },
  "3+2": { label: "3 + 2 · Blitz", initialTimeMs: 180_000, incrementMs: 2_000 },
  "5+2": { label: "5 + 2 · Rapid", initialTimeMs: 300_000, incrementMs: 2_000 },
  "10+5": { label: "10 + 5 · Classical", initialTimeMs: 600_000, incrementMs: 5_000 },
};

const promotionCodes: Record<PromotionPiece, string> = {
  queen: "q",
  rook: "r",
  bishop: "b",
  knight: "n",
};

const loungeEffortLevels: EffortLevel[] = ["fast", "balanced", "deep", "maximum"];
const providerPublicSettings = {
  move_timeout_ms: 20_000,
  spectator_delay_ms: 180,
} as const;
const providerDetails: Record<AgentProviderChoice, { label: string; provider: string }> = {
  openai: { label: "OpenAI", provider: "OpenAI" },
  anthropic: { label: "Claude", provider: "Anthropic" },
  google: { label: "Gemini", provider: "Google" },
  openrouter: { label: "OpenRouter", provider: "OpenRouter" },
  ollama: { label: "Ollama", provider: "Ollama" },
  vllm: { label: "vLLM", provider: "vLLM" },
};

function App() {
  const boardSound = useBoardSound();
  const playMoveSound = boardSound.playMove;
  const [showLab, setShowLab] = useState(false);
  const [showLeaderboards, setShowLeaderboards] = useState(false);
  const [whiteIdentity, setWhiteIdentity] = useState<IdentityDeclaration>({});
  const [blackIdentity, setBlackIdentity] = useState<IdentityDeclaration>({});
  const [runnerIdentity, setRunnerIdentity] = useState<IdentityDeclaration>({});
  const [game, setGame] = useState<GameSnapshot | null>(null);
  const [analysis, setAnalysis] = useState<GameAnalysis | null>(null);
  const [analysisLoading, setAnalysisLoading] = useState(false);
  const [analysisError, setAnalysisError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [flipped, setFlipped] = useState(false);
  const [stockfishElo, setStockfishElo] = useState<StockfishChoice>(readStockfishChoice);
  const stockfishCaps = useStockfishCapabilities();
  useEffect(() => {
    if (validStrength(stockfishElo, stockfishCaps)) {
      try { localStorage.setItem(stockfishChoiceKey, JSON.stringify(stockfishElo)); } catch { /* Optional storage. */ }
    }
  }, [stockfishElo, stockfishCaps]);
  const [whiteSeat, setWhiteSeat] = useState<SeatChoice>("human");
  const [blackSeat, setBlackSeat] = useState<SeatChoice>("stockfish");
  const [playerAdapters, setPlayerAdapters] = useState<PlayerAdapterCatalog | null>(null);
  const [whiteProviderModel, setWhiteProviderModel] = useState("");
  const [blackProviderModel, setBlackProviderModel] = useState("");
  const [whiteEffort, setWhiteEffort] = useState<EffortLevel>("balanced");
  const [blackEffort, setBlackEffort] = useState<EffortLevel>("balanced");
  const [runnerSessions, setRunnerSessions] = useState<RunnerSessionStatus[]>([]);
  const [runnerAccessDenied, setRunnerAccessDenied] = useState(false);
  const [whiteRunnerId, setWhiteRunnerId] = useState("");
  const [blackRunnerId, setBlackRunnerId] = useState("");
  const [runnerMaxTurns, setRunnerMaxTurns] = useState(500);
  const [runnerMatchMinutes, setRunnerMatchMinutes] = useState(240);
  const [runnerName, setRunnerName] = useState("Remote Agent");
  const [runnerProvider, setRunnerProvider] = useState("Independent Runner");
  const [runnerModel, setRunnerModel] = useState("external-model");
  const [runnerConnectionMode, setRunnerConnectionMode] = useState<RunnerConnectionMode>("remote_runner");
  const [subscriptionModel, setSubscriptionModel] = useState("");
  const [runnerPairing, setRunnerPairing] = useState<RunnerPairingResponse | null>(null);
  const [timeControl, setTimeControl] = useState<TimeControlKey>("5+2");
  const [panelTab, setPanelTab] = useState<PanelTab>("moves");
  const [replayPly, setReplayPly] = useState<number | null>(null);
  const replayPlyRef = useRef(replayPly);
  replayPlyRef.current = replayPly;
  const [replayRunning, setReplayRunning] = useState(false);
  const [takeover, setTakeover] = useState<{ gameId: string; revision: number; color: Color; player: PlayerConfiguration } | null>(null);
  const [matchControlBusy, setMatchControlBusy] = useState(false);
  const [humanAction, setHumanAction] = useState<"white" | "black" | "draw" | null>(null);
  const [matchAction, setMatchAction] = useState<MatchAction | null>(null);
  const matchActionTarget = useRef<{ id: string; generation: number; label: string } | null>(null);
  const [pauseReason, setPauseReason] = useState<string | null>(null);
  const [promotion, setPromotion] = useState<PromotionRequest | null>(null);
  const [adviceMode, setAdviceMode] = useState(false);
  const [startPaused, setStartPaused] = useState(false);
  const cancelPromotion = useCallback(() => setPromotion(null), []);
  const [connection, setConnection] = useState<"connecting" | "live" | "offline">("connecting");
  const [busy, setBusy] = useState(true);
  const [notice, setNotice] = useState<string | null>(null);
  const boardControlsRef = useRef<HTMLElement | null>(null);
  const [clockTick, setClockTick] = useState(Date.now());
  const socketRef = useRef<WebSocket | null>(null);
  const gameRef = useRef<GameSnapshot | null>(null);
  const clockSyncRef = useRef<ClockSync | null>(null);

  const whiteProviderModels = useMemo(
    () => isAgentProvider(whiteSeat)
      ? selectableProviderModels(whiteSeat, playerAdapters)
      : [],
    [playerAdapters, whiteSeat],
  );
  const blackProviderModels = useMemo(
    () => isAgentProvider(blackSeat)
      ? selectableProviderModels(blackSeat, playerAdapters)
      : [],
    [blackSeat, playerAdapters],
  );
  const activeRunnerSessions = useMemo(
    () => runnerSessions.filter((session) => !session.expired && !session.revoked && !session.match_grant),
    [runnerSessions],
  );

  useEffect(() => {
    let cancelled = false;
    void fetchPlayerAdapters()
      .then((catalog) => {
        if (!cancelled) setPlayerAdapters(catalog);
      })
      .catch(() => {
        if (!cancelled) setPlayerAdapters(null);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const refreshRunnerSessions = useCallback(async () => {
    try {
      setRunnerSessions(await fetchRunnerSessions());
    } catch (error) {
      setRunnerSessions([]);
      if (error instanceof ApiRequestError && error.status === 403) setRunnerAccessDenied(true);
    }
  }, []);

  useEffect(() => {
    if (runnerAccessDenied) return;
    void refreshRunnerSessions();
    const timer = window.setInterval(() => void refreshRunnerSessions(), 3_000);
    return () => window.clearInterval(timer);
  }, [refreshRunnerSessions, runnerAccessDenied]);

  useEffect(() => {
    if (activeRunnerSessions.length) {
      if (!activeRunnerSessions.some((session) => session.player_id === whiteRunnerId)) {
        setWhiteRunnerId(activeRunnerSessions[0].player_id);
      }
      if (!activeRunnerSessions.some((session) => session.player_id === blackRunnerId)) {
        setBlackRunnerId(activeRunnerSessions[0].player_id);
      }
    }
  }, [activeRunnerSessions, blackRunnerId, whiteRunnerId]);

  useEffect(() => {
    if (whiteProviderModels.length) {
      const resolvedWhiteModel = selectedProviderModel(whiteProviderModel, whiteProviderModels);
      if (whiteProviderModel !== resolvedWhiteModel) setWhiteProviderModel(resolvedWhiteModel);
      if (!loungeEffortsForModel(whiteSeat, resolvedWhiteModel, playerAdapters).includes(whiteEffort)) {
        setWhiteEffort(defaultProviderEffort(whiteSeat, resolvedWhiteModel, playerAdapters));
      }
    }
    if (blackProviderModels.length) {
      const resolvedBlackModel = selectedProviderModel(blackProviderModel, blackProviderModels);
      if (blackProviderModel !== resolvedBlackModel) setBlackProviderModel(resolvedBlackModel);
      if (!loungeEffortsForModel(blackSeat, resolvedBlackModel, playerAdapters).includes(blackEffort)) {
        setBlackEffort(defaultProviderEffort(blackSeat, resolvedBlackModel, playerAdapters));
      }
    }
  }, [
    blackEffort,
    blackProviderModel,
    blackProviderModels,
    blackSeat,
    playerAdapters,
    whiteEffort,
    whiteProviderModel,
    whiteProviderModels,
    whiteSeat,
  ]);

  const acceptSnapshot = useCallback((snapshot: GameSnapshot, announceMove = true, selectMatch = false) => {
    const current = gameRef.current;
    // Only explicit match creation may switch away from the selected match.
    // Old HTTP/socket callbacks can finish before React cleans up their effects.
    if (current && current.id !== snapshot.id && !selectMatch) return;
    const currentServerTime = current ? Date.parse(current.clock.server_time) : Number.NaN;
    const incomingServerTime = Date.parse(snapshot.clock.server_time);
    if (
      current?.id === snapshot.id &&
      (snapshot.generation < current.generation ||
        (snapshot.generation === current.generation &&
          (snapshot.revision < current.revision ||
            (snapshot.revision === current.revision &&
              Number.isFinite(currentServerTime) &&
              Number.isFinite(incomingServerTime) &&
              incomingServerTime <= currentServerTime))))
    ) {
      return;
    }
    if (current?.id !== snapshot.id || current.revision !== snapshot.revision) setTakeover(null);
    const sound = newMoveSound(current, snapshot);
    if (announceMove && sound && replayPlyRef.current === null) playMoveSound(sound);
    const receivedAt = Date.now();
    if (current?.id !== snapshot.id) setConnection("connecting");
    gameRef.current = snapshot;
    clockSyncRef.current = {
      gameId: snapshot.id,
      generation: snapshot.generation,
      revision: snapshot.revision,
      receivedAt,
    };
    setGame(snapshot);
    setClockTick(receivedAt);
    if (
      !current ||
      current.id !== snapshot.id ||
      current.generation !== snapshot.generation ||
      current.version !== snapshot.version ||
      current.can_move !== snapshot.can_move
    ) {
      setSelected(null);
      setPromotion(null);
      setHumanAction(null);
    }
    setReplayPly((currentPly) =>
      currentPly === null ? null : Math.min(currentPly, snapshot.moves.length),
    );
    const path = `/games/${snapshot.id}`;
    if (window.location.pathname !== path) window.history.replaceState(null, "", path);
  }, [playMoveSound]);

  const startNewGame = useCallback(async () => {
    setBusy(true);
    setNotice(null);
    setAnalysis(null);
    setReplayRunning(false);
    try {
      const control = timeControls[timeControl];
      acceptSnapshot(
        await createGame({
          startPaused,
          singleGame: true,
          stockfishElo,
          initialTimeMs: control.initialTimeMs,
          incrementMs: control.incrementMs,
          whitePlayer: createSelectedPlayerConfiguration(
            whiteSeat,
            "white",
            stockfishElo,
            whiteProviderModel,
            whiteEffort,
            playerAdapters,
            whiteRunnerId,
            activeRunnerSessions,
            whiteIdentity,
          ),
          blackPlayer: createSelectedPlayerConfiguration(
            blackSeat,
            "black",
            stockfishElo,
            blackProviderModel,
            blackEffort,
            playerAdapters,
            blackRunnerId,
            activeRunnerSessions,
            blackIdentity,
          ),
        }),
        false,
        true,
      );
      setReplayPly(null);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Unable to create game.");
      if (error instanceof ApiRequestError && error.status === 409) {
        try {
          const live = await fetchLiveMatch();
          if (live) {
            acceptSnapshot(live, false, true);
            setReplayPly(null);
            setNotice(`A match is already on the table: ${live.id.slice(0, 8).toUpperCase()} (${live.lifecycle}). It is shown here. Resume it, or use End and start new to finish this specific match first.`);
          }
        } catch { /* Preserve the creation error and the selected game. */ }
      }
    } finally {
      setBusy(false);
      boardControlsRef.current?.scrollIntoView({ block: "start" });
    }
  }, [
    startPaused,
    acceptSnapshot,
    whiteIdentity,
    blackIdentity,
    blackEffort,
    blackProviderModel,
    blackRunnerId,
    blackSeat,
    activeRunnerSessions,
    playerAdapters,
    stockfishElo,
    timeControl,
    whiteEffort,
    whiteProviderModel,
    whiteRunnerId,
    whiteSeat,
  ]);

  useEffect(() => {
    let cancelled = false;
    async function restore() {
      const routeGame = window.location.pathname.match(/^\/games\/([A-Za-z0-9-]+)\/?$/)?.[1];
      // The start URL always discovers the server's current table. Only an
      // intentional deep link restores a particular (possibly finished) game.
      if (routeGame) {
        setBusy(true);
        try {
          const snapshot = await fetchGame(routeGame);
          if (!cancelled) acceptSnapshot(snapshot);
          return;
        } catch {
          if (!cancelled) setNotice("That shared match is unavailable or no longer exists. Open the current table or start a new match below.");
          return;
        } finally {
          if (!cancelled) setBusy(false);
        }
      }
      if (!cancelled) {
        setBusy(true);
        try {
          const live = await fetchLiveMatch();
          // A match started while this request was in flight takes priority.
          if (cancelled || gameRef.current) return;
          if (live) acceptSnapshot(live);
          else setNotice("No match is live. Choose the White and Black seats, then press New match.");
        } catch (error) {
          if (!cancelled) setNotice(error instanceof Error ? error.message : "Unable to load the live match.");
        } finally {
          if (!cancelled) setBusy(false);
        }
      }
    }
    const timer = window.setTimeout(() => void restore(), 0);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [acceptSnapshot]);

  const pausedGameId = game?.lifecycle === "paused" ? game.id : null;
  const pausedRevision = game?.revision;
  useEffect(() => {
    if (!pausedGameId) {
      setPauseReason(null);
      return;
    }
    let cancelled = false;
    void fetchGameEvents(pausedGameId).then((events) => {
      const current = gameRef.current;
      if (!cancelled && current?.id === pausedGameId) setPauseReason(describePause(events, current));
    }).catch(() => { if (!cancelled) setPauseReason(null); });
    return () => { cancelled = true; };
  }, [pausedGameId, pausedRevision]);

  useEffect(() => {
    if (!game?.id) return;
    const gameId = game.id;
    socketRef.current?.close();
    let stopped = false;
    let retryTimer: number | undefined;
    let retryCount = 0;

    function connect() {
      if (stopped || document.visibilityState === "hidden") return;
      setConnection("connecting");
      const socket = new WebSocket(websocketUrl(gameId));
      let receivedSnapshot = false;
      socketRef.current = socket;
      const isCurrentSocket = () => !stopped && socketRef.current === socket && gameRef.current?.id === gameId;
      socket.addEventListener("open", () => {
        if (!isCurrentSocket()) return;
        retryCount = 0;
        // Enable input only after the reconnect delivers an authoritative snapshot.
      });
      socket.addEventListener("close", () => {
        if (!isCurrentSocket()) return;
        setConnection("offline");
        const delay = Math.min(10_000, 500 * 2 ** retryCount);
        retryCount += 1;
        retryTimer = window.setTimeout(connect, delay);
      });
      socket.addEventListener("error", () => {
        if (isCurrentSocket()) setConnection("offline");
      });
      socket.addEventListener("message", (event) => {
        if (!isCurrentSocket()) return;
        try {
          const message = JSON.parse(event.data) as { type: string; payload: GameSnapshot };
          if (message.type === "snapshot" && message.payload.id === gameId) {
            acceptSnapshot(message.payload, receivedSnapshot);
            receivedSnapshot = true;
            setConnection("live");
          }
        } catch {
          setNotice("A live update could not be read.");
        }
      });
    }

    connect();
    function visibilityChanged() {
      if (retryTimer !== undefined) window.clearTimeout(retryTimer);
      // Invalidate the old socket before closing it so queued events cannot
      // re-enable input. Foreground always gets a fresh authoritative baseline.
      const previous = socketRef.current;
      socketRef.current = null;
      previous?.close();
      setConnection("connecting");
      setSelected(null);
      setPromotion(null);
      if (document.visibilityState === "visible") connect();
    }
    document.addEventListener("visibilitychange", visibilityChanged);
    return () => {
      stopped = true;
      document.removeEventListener("visibilitychange", visibilityChanged);
      if (retryTimer !== undefined) window.clearTimeout(retryTimer);
      socketRef.current?.close();
    };
  }, [game?.id, acceptSnapshot]);

  useEffect(() => {
    if (!game?.id) return;
    let cancelled = false;
    setAnalysis((current) =>
      current?.game_id === game.id &&
      current.generation === game.generation &&
      current.position_version === game.version
        ? current
        : null,
    );
    setAnalysisLoading(true);
    setAnalysisError(null);
    const timer = window.setTimeout(() => {
      void fetchAnalysis(game.id)
        .then((result) => {
          if (
            !cancelled &&
            result.game_id === game.id &&
            result.generation === game.generation &&
            result.position_version === game.version
          ) {
            setAnalysis(result);
          }
        })
        .catch((error) => {
          if (!cancelled) {
            setAnalysisError(error instanceof Error ? error.message : "Analysis unavailable.");
          }
        })
        .finally(() => {
          if (!cancelled) setAnalysisLoading(false);
        });
    }, 350);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [game?.id, game?.generation, game?.version]);

  useEffect(() => {
    if (game?.lifecycle !== "running" || game.status !== "active") return;
    setClockTick(Date.now());
    const timer = window.setInterval(() => setClockTick(Date.now()), 100);
    return () => window.clearInterval(timer);
  }, [game?.id, game?.lifecycle, game?.status, game?.turn, game?.clock.server_time]);

  useEffect(() => {
    if (!game) return;
    document.title = `${game.status === "active" ? "Live" : game.result} · AI Chess Lounge`;
    const description = document.querySelector('meta[name="description"]');
    description?.setAttribute(
      "content",
      `Watch ${game.white_player.display_name} vs ${game.black_player.display_name} in the AI Chess Lounge.`,
    );
  }, [game]);

  useEffect(() => {
    if (!replayRunning || !game) return;
    const timer = window.setTimeout(() => {
      const current = replayPly ?? 0;
      const next = Math.min(game.moves.length, current + 1);
      setReplayPly(next);
      if (next >= game.moves.length) setReplayRunning(false);
    }, 700);
    return () => window.clearTimeout(timer);
  }, [game, replayPly, replayRunning]);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (!game || event.altKey || event.ctrlKey || event.metaKey) return;
      const target = event.target as HTMLElement | null;
      if (target?.matches("input, select, textarea, button")) return;
      const current = replayPly ?? game.moves.length;
      if (event.key === "ArrowLeft") {
        event.preventDefault();
        setReplayRunning(false);
        setReplayPly(Math.max(0, current - 1));
      }
      if (event.key === "ArrowRight") {
        event.preventDefault();
        setReplayRunning(false);
        setReplayPly(Math.min(game.moves.length, current + 1));
      }
      if (event.key === "Home") {
        event.preventDefault();
        setReplayRunning(false);
        setReplayPly(0);
      }
      if (event.key === "End") {
        event.preventDefault();
        setReplayRunning(false);
        setReplayPly(null);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [game, replayPly]);

  const displayPly = replayPly ?? game?.moves.length ?? 0;
  const followingLive = replayPly === null;
  const displayFen = useMemo(() => {
    if (!game || displayPly === game.moves.length) return game?.fen ?? "";
    if (displayPly === 0) return game.initial_fen;
    return game.moves[displayPly - 1]?.fen ?? game.fen;
  }, [displayPly, game]);
  const displayLastMove = useMemo(() => {
    if (!game || displayPly === 0) return null;
    return game.moves[displayPly - 1]?.uci ?? null;
  }, [displayPly, game]);
  const moveRows = useMemo(() => pairMoves(game?.moves ?? []), [game?.moves]);
  const clocks = useMemo(
    () => projectClocks(game, clockTick, clockSyncRef.current),
    [game, clockTick],
  );
  const playerCanMove = Boolean(game?.can_move && followingLive && !busy && connection === "live");
  const activeSeat = game?.[game.turn === "white" ? "white_player" : "black_player"];
  const adviceSupported = !!activeSeat && ["scripted", "openai", "anthropic", "google", "openrouter", "ollama", "vllm"].includes(activeSeat.adapter_id);
  const canSuggest = Boolean(adviceMode && adviceSupported && game?.lifecycle === "paused" && followingLive && !busy && connection === "live");
  const boardCanInteract = playerCanMove || canSuggest;
  const humanSuggestions = game?.consultations?.filter(c => c.direction === "human_to_ai") ?? [];
  const latestHumanSuggestion = humanSuggestions.at(-1);
  useEffect(() => { setAdviceMode(false); setSelected(null); setPromotion(null); }, [game?.id, game?.revision]);

  async function saveHumanSuggestion(move: string | null) {
    if (!game || !canSuggest) return;
    setBusy(true);
    try {
      acceptSnapshot(await suggestToAgent(game, move));
      setNotice(move ? "Suggestion saved. Resume when ready; the AI chooses its own move." : "Suggestion cleared.");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Suggestion failed.");
      try { acceptSnapshot(await fetchGame(game.id)); } catch { /* Keep original error. */ }
    } finally { setBusy(false); setSelected(null); setPromotion(null); }
  }
  const currentAnalysis =
    analysis &&
    game &&
    analysis.game_id === game.id &&
    analysis.generation === game.generation &&
    analysis.position_version === game.version
      ? analysis
      : null;
  const selectedPoint = currentAnalysis?.points.find((point) => point.ply === displayPly) ?? null;
  const latestAgentMove = game?.moves.filter((move) => move.player_metadata !== null).at(-1);
  const matchupLabel = game
    ? `${game.white_player.display_name} vs ${game.black_player.display_name}`
    : "Human vs Stockfish";
  const evalShare = evaluationShare(selectedPoint);

  async function commitMove(move: string) {
    if (canSuggest) { await saveHumanSuggestion(move); return; }
    if (!game || !playerCanMove) return;
    setSelected(null);
    setPromotion(null);
    setBusy(true);
    setNotice(null);
    try {
      acceptSnapshot(await submitMove(game.id, move, game.version));
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Move failed.");
      try {
        acceptSnapshot(await fetchGame(game.id));
      } catch {
        // Preserve the original move error when refresh also fails.
      }
    } finally {
      setBusy(false);
    }
  }

  async function onSquareClick(square: string) {
    if (!game || !boardCanInteract) return;
    const boardSquare = parseFen(game.fen).find((candidate) => candidate.name === square);
    if (!selected) {
      if (boardSquare?.piece?.color === game.turn) setSelected(square);
      return;
    }
    if (boardSquare?.piece?.color === game.turn) {
      setSelected(square);
      return;
    }
    await onMoveDrop(selected, square);
  }

  async function onMoveDrop(from: string, to: string) {
    if (!game || !boardCanInteract) return;
    const candidates = game.legal_moves.filter(
      (move) => move.startsWith(from) && move.slice(2, 4) === to,
    );
    if (!candidates.length) {
      setSelected(null);
      return;
    }
    if (candidates.some((candidate) => candidate.length === 5)) {
      setPromotion({ from, to, candidates, gameId: game.id, version: game.version, color: game.turn });
      return;
    }
    await commitMove(candidates[0]);
  }

  function choosePromotion(piece: PromotionPiece) {
    if (!promotion || !game || promotion.gameId !== game.id || promotion.version !== game.version || !boardCanInteract) {
      setPromotion(null);
      return;
    }
    const move = `${promotion.from}${promotion.to}${promotionCodes[piece]}`;
    if (promotion.candidates.includes(move)) void commitMove(move);
  }

  async function copyText(value: string, label: string) {
    try {
      await navigator.clipboard.writeText(value);
      setNotice(`${label} copied.`);
    } catch {
      setNotice(`${label} could not be copied. Select it manually and try again.`);
    }
    window.setTimeout(() => setNotice(null), 1800);
  }

  async function revokeRunner(sessionId: string) {
    setBusy(true);
    try {
      await revokeRunnerSession(sessionId);
      await refreshRunnerSessions();
      setNotice("Runner access revoked. Pending moves cannot be committed.");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Unable to revoke runner.");
    } finally {
      setBusy(false);
    }
  }

  async function generateRunnerPairing() {
    setBusy(true);
    setNotice(null);
    try {
      const pairing = await createRunnerPairing({
        comparison: Object.keys(runnerIdentity).length ? runnerIdentity : undefined,
        maxTurns: runnerMaxTurns,
        matchTtlMs: runnerMatchMinutes * 60_000,
        displayName: runnerName.trim(),
        provider: runnerConnectionMode === "subscription_bridge" ? "OpenAI" : runnerProvider.trim(),
        model: (runnerConnectionMode === "subscription_bridge" ? subscriptionModel : runnerModel).trim(),
        connectionMode: runnerConnectionMode,
        division: runnerConnectionMode === "subscription_bridge" ? "open_agentic" : "legal_assist",
        effort: null,
        moveTimeoutMs: runnerConnectionMode === "subscription_bridge" ? 120_000 : 30_000,
      });
      setRunnerPairing(pairing);
      setNotice("One-time runner pairing created. Share only with the agent you intend to seat.");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Unable to create runner pairing.");
    } finally {
      setBusy(false);
    }
  }

  function openMatchAction(action: MatchAction) {
    if (!game) return;
    matchActionTarget.current = {
      id: game.id, generation: game.generation,
      label: `Match ${game.id.slice(0, 8).toUpperCase()} · ${game.white_player.display_name} vs ${game.black_player.display_name}`,
    };
    setMatchAction(action);
  }

  function onReset() {
    if (!game) return;
    const remoteSeat = [game.white_player, game.black_player].some((player) =>
      player.connection_mode === "remote_runner" || player.connection_mode === "subscription_bridge");
    if (remoteSeat) openMatchAction("reset");
    else void resetMatch();
  }

  async function resetMatch() {
    if (!game) return;
    setBusy(true);
    setReplayRunning(false);
    try {
      acceptSnapshot(await resetGame(game.id));
      setReplayPly(null);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Reset failed.");
    } finally {
      setBusy(false);
    }
  }

  async function onMatchAction(result: AdjudicatedResult | null) {
    if (!game || !matchAction) return;
    const target = matchActionTarget.current;
    if (!target || target.id !== gameRef.current?.id) {
      setMatchAction(null);
      setNotice("The selected match changed. Review it before continuing.");
      return;
    }
    const action = matchAction;
    if (action === "reset") {
      setMatchAction(null);
      await resetMatch();
      return;
    }
    setMatchControlBusy(true);
    setNotice(null);
    try {
      acceptSnapshot(action === "abort" || action === "restart"
        ? await abortGame(target.id, target.generation)
        : await adjudicateGame(target.id, result ?? "1/2-1/2"));
      setMatchAction(null);
      if (action === "restart" && gameRef.current?.id === target.id) await startNewGame();
    } catch (error) {
      setMatchAction(null);
      setNotice(error instanceof Error ? error.message : "Match action failed.");
      try { acceptSnapshot(await fetchGame(game.id)); } catch { /* Preserve action error. */ }
    } finally {
      setMatchControlBusy(false);
      boardControlsRef.current?.scrollIntoView({ block: "start" });
    }
  }

  async function onHumanAction(intendedMove: string | null) {
    if (!game || !humanAction || game.status !== "active" || !followingLive || connection !== "live") return;
    setBusy(true);
    try {
      acceptSnapshot(humanAction === "draw"
        ? await claimDraw(game.id, game.version, intendedMove)
        : await resignGame(game.id, humanAction, game.version));
      setHumanAction(null);
    } catch (error) {
      setHumanAction(null);
      setNotice(error instanceof Error ? error.message : "Action failed.");
      try { acceptSnapshot(await fetchGame(game.id)); } catch { /* Keep the action error. */ }
    } finally {
      setBusy(false);
    }
  }

  async function onMatchControl(action: "pause" | "resume") {
    if (!game || !followingLive || connection !== "live" || matchControlBusy) return;
    setMatchControlBusy(true);
    setNotice(null);
    try {
      acceptSnapshot(await controlMatch(game.id, action, game.revision));
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Match control failed.");
      try { acceptSnapshot(await fetchGame(game.id)); } catch { /* Preserve action error. */ }
    } finally {
      setMatchControlBusy(false);
      boardControlsRef.current?.scrollIntoView({ block: "start" });
    }
  }

  function prepareTakeover(color: Color, restore = false) {
    if (!game || game.lifecycle !== "paused" || !followingLive || connection !== "live") return;
    const previous = (game.seat_history ?? []).filter((change) => change.color === color).at(-1)?.previous_player;
    const white = color === "white";
    const player = restore && previous ? previous : createSelectedPlayerConfiguration(
      white ? whiteSeat : blackSeat, color, stockfishElo,
      white ? whiteProviderModel : blackProviderModel, white ? whiteEffort : blackEffort,
      playerAdapters, white ? whiteRunnerId : blackRunnerId, activeRunnerSessions,
    );
    setTakeover({ gameId: game.id, revision: game.revision, color, player });
  }

  async function confirmTakeover() {
    if (!game || !takeover || takeover.gameId !== game.id || takeover.revision !== game.revision
      || game.lifecycle !== "paused" || connection !== "live" || !followingLive) return;
    setMatchControlBusy(true);
    setNotice(null);
    try {
      acceptSnapshot(await changeSeat(game.id, takeover.color, takeover.player, takeover.revision));
      setTakeover(null);
      setNotice("Seat changed. The match stays paused until you resume.");
      void refreshRunnerSessions();
    } catch (error) {
      setTakeover(null);
      setNotice(error instanceof Error ? error.message : "Seat change failed.");
      try { acceptSnapshot(await fetchGame(game.id)); } catch { /* Preserve action error. */ }
    } finally { setMatchControlBusy(false); }
  }

  async function onRetryAgentTurn() {
    if (!game || game.lifecycle !== "paused") return;
    setBusy(true);
    try {
      acceptSnapshot(await retryAgentTurn(game.id));
      setNotice("Agent retry requested from the preserved position.");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Agent retry failed.");
    } finally {
      setBusy(false);
    }
  }

  function selectPly(ply: number) {
    setTakeover(null);
    setPromotion(null);
    setHumanAction(null);
    setSelected(null);
    setReplayRunning(false);
    setReplayPly(Math.max(0, Math.min(game?.moves.length ?? 0, ply)));
  }

  function toggleReplay() {
    if (!game?.moves.length) return;
    if (replayRunning) {
      setReplayRunning(false);
      return;
    }
    if (replayPly === null || replayPly >= game.moves.length) setReplayPly(0);
    setReplayRunning(true);
  }

  function downloadGame(format: "pgn" | "json") {
    if (!game) return;
    const content = format === "pgn"
      ? game.pgn
      : JSON.stringify(
          {
            schema: "ai-chess-lounge.match-export.v1",
            exported_at: new Date().toISOString(),
            match: game,
              analysis: currentAnalysis,
          },
          null,
          2,
        );
    downloadText(content, `ai-chess-lounge-${game.id}.${format}`, format);
  }

  async function shareMatch() {
    if (!game) return;
    const url = permalink(game.id);
    if (navigator.share) {
      try {
        await navigator.share({
          title: "AI Chess Lounge match",
          text: `${matchupLabel} · ${game.result === "*" ? "live" : game.result}`,
          url,
        });
        return;
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") return;
      }
    }
    await copyText(url, "Match link");
  }

  const whiteConfiguration = game?.white_player
    ?? createSelectedPlayerConfiguration(
      whiteSeat,
      "white",
      stockfishElo,
      whiteProviderModel,
      whiteEffort,
      playerAdapters,
      whiteRunnerId,
      activeRunnerSessions,
    );
  const blackConfiguration = game?.black_player
    ?? createSelectedPlayerConfiguration(
      blackSeat,
      "black",
      stockfishElo,
      blackProviderModel,
      blackEffort,
      playerAdapters,
      blackRunnerId,
      activeRunnerSessions,
    );
  const whiteStrategy = strategyForSeat(game, "white", whiteConfiguration);
  const blackStrategy = strategyForSeat(game, "black", blackConfiguration);
  const whitePlayer = playerCardForSeat(
    game,
    "white",
    whiteConfiguration,
    clocks.white,
  );
  const blackPlayer = playerCardForSeat(
    game,
    "black",
    blackConfiguration,
    clocks.black,
  );
  const activePlayer = game?.turn === "black" ? game.black_player : game?.white_player;
  const canRetryAgent = Boolean(
    game?.lifecycle === "paused" && activePlayer && activePlayer.adapter_id !== "human",
  );
  const newMatchDisabled = busy || matchControlBusy
    || ((whiteSeat === "stockfish" || blackSeat === "stockfish") && !validStrength(stockfishElo, stockfishCaps))
    || (whiteSeat === "remote_runner" && !whiteRunnerId)
    || (blackSeat === "remote_runner" && !blackRunnerId);
  const matchEnded = Boolean(game && ["completed", "aborted", "adjudicated"].includes(game.lifecycle));
  const broadcastLabel = !game ? (busy ? "CHECKING TABLE" : "READY TO START") : game.status === "active"
    ? "LIVE EXHIBITION"
    : game?.lifecycle === "paused"
      ? "RECOVERY PAUSED"
      : "MATCH COMPLETE";

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
          <details className="lounge-tools">
          <summary>Lounge tools</summary>
          <div>
          <a className="ghost-button" href="/board-studio">Compare board looks</a>
          <button className="ghost-button" aria-expanded={showLeaderboards} onClick={() => setShowLeaderboards(v => !v)}>{showLeaderboards ? "Close AI leaderboards" : "AI leaderboards"}</button>
          <button className="ghost-button" aria-expanded={showLab} onClick={() => setShowLab(v => !v)}>{showLab ? "Close Model Lab" : "Model Lab"}</button>
          </div>
          </details>
          <span className={`connection ${connection}`} aria-label={`Connection ${game ? connection : busy ? "checking" : "ready"}`}>
            <span className="connection-dot" /> {game ? connection : busy ? "checking" : "ready"}
          </span>
          <button className="ghost-button" onClick={() => setFlipped((value) => !value)}>Flip board</button>
          <button className="gold-ghost-button" onClick={() => void shareMatch()} disabled={!game}>Share match</button>
        </div>
      </header>

      <section className="broadcast-ribbon" aria-label="Match broadcast status">
        <span className={game?.status === "active" ? "live-pulse" : "result-pulse"} />
        <strong>{broadcastLabel}</strong>
        <span>Table 01</span>
        <span>{game ? `${Math.round(game.clock.initial_time_ms / 60_000)}+${game.clock.increment_ms / 1_000}` : "—"}</span>
        <span>Server authoritative</span>
        {!followingLive && <b>LOCAL REPLAY · LIVE FEED CONTINUES</b>}
      </section>

      <section className="arena-layout">
        <div className="match-stage">
          <section ref={boardControlsRef} className="board-play-controls" aria-label="Board play controls">
            {game && <small>Viewing match {game.id.slice(0, 8).toUpperCase()} · {game.white_player.display_name} vs {game.black_player.display_name}</small>}
            {!game ? <>
                <strong>{busy ? "Checking the table" : "Ready to start"}</strong>
                <p>Choose Seats & game setup, then start a match. Nothing starts until you choose to play.</p>
                <button className="primary-button" disabled={newMatchDisabled} onClick={() => void startNewGame()}>Play a new match</button>
                <small>Next match: {seatChoiceLabel(whiteSeat)} vs {seatChoiceLabel(blackSeat)}. Change players in Seats & game setup.</small>
                <a href="/">Open current table</a>
              </>
              : connection !== "live" ? <><strong>Reconnecting to the board</strong><p>Moves are disabled until the current position arrives.</p></>
              : matchEnded ? <>
                <strong>{game.status === "aborted" ? "Match aborted" : "Match finished"}</strong>
                <p>This match has ended. Its final position and history are saved. Start a new match to play.</p>
                <button className="primary-button" disabled={newMatchDisabled} onClick={() => void startNewGame()}>Play a new match</button>
                <small>Next match: {seatChoiceLabel(whiteSeat)} vs {seatChoiceLabel(blackSeat)}. Change players in Seats & game setup.</small>
                <a href="/">Open current table</a>
              </> : !followingLive ? <>
                <strong>Viewing replay</strong><p>Return to the current position before playing.</p>
                <button onClick={() => { setReplayRunning(false); setReplayPly(null); }}>Return to live board</button>
              </> : game.lifecycle === "paused" ? <>
                <strong>Match paused</strong><p>{pauseReason ?? "The clocks and moves are paused."} Resume to continue from this position.</p>
                <button className="primary-button" disabled={matchControlBusy || busy} onClick={() => void onMatchControl("resume")}>Resume play</button>
              </> : game.lifecycle === "created" || game.lifecycle === "waiting" ? <>
                <strong>Waiting for players</strong><p>This match is not running yet.</p>
              </> : <>
                <strong>{capitalize(game.turn)} to move</strong>
                <p>{activePlayer?.adapter_id === "human" ? `Move a ${game.turn} piece: tap its square and destination, or drag it.` : `Waiting for ${activePlayer?.display_name ?? "the player"} to move.`}</p>
              </>}
            {game && !matchEnded && <div className="secondary-actions">
              <button disabled={busy || matchControlBusy || !followingLive || connection !== "live"} onClick={() => openMatchAction("abort")}>End match…</button>
              <button disabled={newMatchDisabled || !followingLive || connection !== "live"} onClick={() => openMatchAction("restart")}>End and start new…</button>
            </div>}
            <button className="setup-shortcut" onClick={() => {
              const section = document.getElementById("seats-setup") as HTMLDetailsElement;
              section.open = true; section.querySelector("summary")?.focus(); section.scrollIntoView({ block: "nearest" });
            }}>Seats &amp; game setup</button>
            {game?.lifecycle === "running" && <button disabled={matchControlBusy || !followingLive || connection !== "live"} onClick={() => void onMatchControl("pause")}>Pause play</button>}
            {notice && <p className="board-notice" role="alert">{notice}</p>}
          </section>
          <PlayerCard {...(flipped ? whitePlayer : blackPlayer)} />

          <div className="board-broadcast-frame">
            <div className={`evaluation-bar ${flipped ? "flipped" : ""}`} aria-label={`White evaluation share ${Math.round(evalShare)} percent`}>
              <div className="evaluation-white" style={{ height: `${evalShare}%` }} />
              <span>{formatEvaluation(selectedPoint)}</span>
            </div>
            <ChessBoard
              showSquareEntry
              fen={displayFen || "8/8/8/8/8/8/8/8 w - - 0 1"}
              positionKey={`${game?.id}:${game?.version}:${game?.revision}`}
              flipped={flipped}
              legalMoves={followingLive ? game?.legal_moves ?? [] : []}
              selected={selected}
              lastMove={displayLastMove}
              inCheck={Boolean(followingLive && game?.in_check)}
              disabled={!boardCanInteract}
              onSquareClick={(square) => void onSquareClick(square)}
              onMoveDrop={(from, to) => void onMoveDrop(from, to)}
            />
          </div>

          {game && adviceSupported && <section className="consultation-panel" aria-label="Suggest a move to your AI">
            <h3>Suggest a move to your AI</h3>
            <p>Pause on the AI turn, enable suggestion mode, then drag a piece or select two squares. The board stays unchanged. Resume to let the AI decide.</p>
            <label><input type="checkbox" checked={adviceMode} disabled={game.lifecycle !== "paused" || !followingLive || connection !== "live" || busy} onChange={e => setAdviceMode(e.target.checked)} /> Suggestion mode</label>
            {canSuggest && <p role="status">Board input saves a suggestion for {activeSeat?.display_name}; it does not play a move.</p>}
            {latestHumanSuggestion && <p>Human suggested {latestHumanSuggestion.san} to {latestHumanSuggestion.advisor.display_name}: {latestHumanSuggestion.status === "played" ? "AI turn completed (may choose differently)" : latestHumanSuggestion.status}.</p>}
            {latestHumanSuggestion?.status === "ready" && <button disabled={!canSuggest} onClick={() => void saveHumanSuggestion(null)}>Clear human suggestion</button>}
            <small>Human-AI Team exhibition. Advice is recorded in history and PGN.</small>
          </section>}

          <PlayerCard {...(flipped ? blackPlayer : whitePlayer)} />

          <div className="playback-bar">
            <button aria-label="First position" onClick={() => selectPly(0)} disabled={!game?.moves.length}>|◀</button>
            <button aria-label="Previous move" onClick={() => selectPly(displayPly - 1)} disabled={!game?.moves.length || displayPly === 0}>◀</button>
            <button className="replay-toggle" onClick={toggleReplay} disabled={!game?.moves.length}>{replayRunning ? "PAUSE" : "REPLAY"}</button>
            <input type="range" min="0" max={game?.moves.length ?? 0} value={displayPly} onChange={(event) => selectPly(Number(event.target.value))} aria-label="Replay position" />
            <span><strong>{displayPly}</strong> / {game?.moves.length ?? 0}</span>
            <button aria-label="Next move" onClick={() => selectPly(displayPly + 1)} disabled={!game || displayPly >= game.moves.length}>▶</button>
            <button className={followingLive ? "live active" : "live"} onClick={() => { setReplayRunning(false); setReplayPly(null); }} disabled={followingLive}>LIVE</button>
          </div>
        </div>

        <aside className="control-deck">
          <div className="match-header">
            <div>
              <p className="eyebrow">EXHIBITION TABLE 01</p>
              <h2>{game?.white_player.display_name ?? seatChoiceLabel(whiteSeat)} <span>vs</span> {game?.black_player.display_name ?? seatChoiceLabel(blackSeat)}</h2>
              <small>{game?.id ? `Match ${game.id.slice(0, 8).toUpperCase()}${game.termination_reason ? ` · ${terminationLabel(game.termination_reason)}` : ""}` : "No match loaded"}</small>
            </div>
            <span className={`result-badge ${game?.status ?? "loading"}`}>{game?.status === "active" ? "LIVE" : game?.status === "paused" ? "PAUSED" : game?.status === "aborted" ? "ABORTED" : game?.result ?? (busy ? "CHECKING" : "READY")}</span>
          </div>

          <div className="telemetry-grid">
            <Metric label="Position" value={`${displayPly} / ${game?.moves.length ?? 0}`} />
            <Metric label="Evaluation" value={formatEvaluation(selectedPoint)} accent />
            <Metric label="Move latency" value={latestAgentMove?.player_metadata ? `${latestAgentMove.player_metadata.latency_ms} ms` : "—"} />
            <Metric label="Analysis depth" value={selectedPoint?.depth ? `Depth ${selectedPoint.depth}` : analysisLoading ? "CALCULATING" : "—"} />
            <Metric label="Event sequence" value={String(game?.event_sequence ?? 0)} />
            <Metric label="Lifecycle" value={(game?.lifecycle ?? "loading").toUpperCase()} accent />
          </div>

          <div className="panel-tabs" role="tablist" aria-label="Match details">
            {(["moves", "analysis", "pgn", "fen"] as const).map((tab) => (
              <button key={tab} id={`detail-tab-${tab}`} role="tab" aria-controls="match-detail-panel" tabIndex={panelTab === tab ? 0 : -1} aria-selected={panelTab === tab} className={panelTab === tab ? "active" : ""} onClick={() => setPanelTab(tab)} onKeyDown={event => {
                const tabs: PanelTab[] = ["moves", "analysis", "pgn", "fen"];
                const index = tabs.indexOf(tab);
                const next = event.key === "ArrowRight" ? (index + 1) % 4 : event.key === "ArrowLeft" ? (index + 3) % 4 : event.key === "Home" ? 0 : event.key === "End" ? 3 : -1;
                if (next < 0) return;
                event.preventDefault(); setPanelTab(tabs[next]); document.getElementById(`detail-tab-${tabs[next]}`)?.focus();
              }}>
                {tab.toUpperCase()}
              </button>
            ))}
          </div>

          <div className="panel-content" id="match-detail-panel" role="tabpanel" aria-labelledby={`detail-tab-${panelTab}`} tabIndex={0}>
            {panelTab === "moves" && (
              <div className="move-list">
                {!moveRows.length && <div className="empty-state">The opening position is ready.</div>}
                {moveRows.map((row) => (
                  <div className="move-row" key={row.number}>
                    <span>{row.number}.</span>
                    <MoveButton san={row.white} ply={row.number * 2 - 1} selected={displayPly === row.number * 2 - 1} classification={currentAnalysis?.points[row.number * 2 - 1]?.classification ?? null} onSelect={selectPly} />
                    <MoveButton san={row.black} ply={row.number * 2} selected={Boolean(row.black && displayPly === row.number * 2)} classification={currentAnalysis?.points[row.number * 2]?.classification ?? null} onSelect={selectPly} />
                  </div>
                ))}
              </div>
            )}
            {panelTab === "analysis" && <AnalysisPanel analysis={currentAnalysis} loading={analysisLoading} error={analysisError} selectedPly={displayPly} selectedPoint={selectedPoint} onSelect={selectPly} />}
            {panelTab === "pgn" && (
              <div className="notation-panel">
                <pre>{game?.pgn ?? "No game loaded."}</pre>
                <div><button onClick={() => void copyText(game?.pgn ?? "", "PGN")}>Copy PGN</button><button onClick={() => downloadGame("pgn")}>Download .pgn</button></div>
              </div>
            )}
            {panelTab === "fen" && (
              <div className="notation-panel">
                <pre>{displayFen}</pre>
                <div><button onClick={() => void copyText(displayFen, "FEN")}>Copy FEN</button><button onClick={() => downloadGame("json")}>Download match JSON</button></div>
              </div>
            )}
          </div>

          <details className="workspace-section">
            <summary>Strategy &amp; live telemetry <span>Plans, usage, consultation</span></summary>
          <StrategyChannel
            white={whiteStrategy}
            black={blackStrategy}
            activeSide={game?.turn ?? "white"}
            pv={selectedPoint?.pv_san ?? []}
            depth={selectedPoint?.depth ?? null}
          />

          {game && <GameUsage game={game} />}
          {game && <ConsultationPanel key={game.id} game={game} catalog={playerAdapters}
            enabled={followingLive && connection === "live" && !busy}
            onSnapshot={snapshot => { if (gameRef.current?.id === snapshot.id) acceptSnapshot(snapshot); }} />}
          </details>
          <details className="workspace-section" id="seats-setup">
            <summary>Seats &amp; game setup <span>Players, models, strength, clock</span></summary>
          <p>One game at a time. Select each seat independently: Human to play, or two agents to watch. Effort choices come from each model's supported capabilities. API access is separate from ordinary consumer subscriptions.</p>
          <div className="match-controls">
            <label>
              White seat
              <select
                aria-label="White seat"
                value={whiteSeat}
                onChange={(event) => setWhiteSeat(event.target.value as SeatChoice)}
              >
                <SeatOptions
                  catalog={playerAdapters}
                  runners={activeRunnerSessions}
                />
              </select>
            </label>
            <label>
              Black seat
              <select
                aria-label="Black seat"
                value={blackSeat}
                onChange={(event) => setBlackSeat(event.target.value as SeatChoice)}
              >
                <SeatOptions
                  catalog={playerAdapters}
                  runners={activeRunnerSessions}
                />
              </select>
            </label>
            {isAgentProvider(whiteSeat) && (
              <ProviderSeatControls
                providerChoice={whiteSeat}
                color="white"
                models={whiteProviderModels}
                catalog={playerAdapters}
                selectedModel={selectedProviderModel(whiteProviderModel, whiteProviderModels)}
                selectedEffort={whiteEffort}
                onModelChange={(model) => {
                  setWhiteProviderModel(model);
                  setWhiteEffort(defaultProviderEffort(whiteSeat, model, playerAdapters));
                }}
                onEffortChange={setWhiteEffort}
              />
            )}
            {isAgentProvider(blackSeat) && (
              <ProviderSeatControls
                providerChoice={blackSeat}
                color="black"
                models={blackProviderModels}
                catalog={playerAdapters}
                selectedModel={selectedProviderModel(blackProviderModel, blackProviderModels)}
                selectedEffort={blackEffort}
                onModelChange={(model) => {
                  setBlackProviderModel(model);
                  setBlackEffort(defaultProviderEffort(blackSeat, model, playerAdapters));
                }}
                onEffortChange={setBlackEffort}
              />
            )}
            {whiteSeat === "remote_runner" && (
              <RunnerSeatControls
                color="white"
                runners={activeRunnerSessions}
                selectedRunnerId={whiteRunnerId}
                onRunnerChange={setWhiteRunnerId}
              />
            )}
            {blackSeat === "remote_runner" && (
              <RunnerSeatControls
                color="black"
                runners={activeRunnerSessions}
                selectedRunnerId={blackRunnerId}
                onRunnerChange={setBlackRunnerId}
              />
            )}
            <StockfishStrength value={stockfishElo} onChange={setStockfishElo} caps={stockfishCaps} game={game} />
            <label>
              Time control
              <select value={timeControl} onChange={(event) => setTimeControl(event.target.value as TimeControlKey)}>
                {(Object.entries(timeControls) as [TimeControlKey, (typeof timeControls)[TimeControlKey]][]).map(([key, control]) => (
                  <option key={key} value={key}>{control.label}</option>
                ))}
              </select>
            </label>
            <label><input type="checkbox" checked={startPaused} onChange={e => setStartPaused(e.target.checked)} /> Start paused to review or advise before any agent call</label>
            {(game?.lifecycle === "running" || game?.lifecycle === "paused") && <p>Finish or explicitly abort the current match before creating another.</p>}
            <button
              className="primary-button"
              onClick={() => void startNewGame()}
              disabled={newMatchDisabled}
            >
              New match
            </button>
          </div>

          <section className="takeover-panel" aria-label="Match control">
            <h3>Match control</h3>
            {game?.lifecycle === "running" && <button disabled={matchControlBusy || !followingLive || connection !== "live"} onClick={() => void onMatchControl("pause")}>Pause match</button>}
            {game?.lifecycle === "paused" && <>
              {pauseReason && <p className="pause-reason" role="status">{pauseReason}</p>}
              <p>Match paused. Choose players in the seat selectors above, apply a change, then resume. Position and remaining time carry over.</p>
              <div className="secondary-actions">
                {(["white", "black"] as const).map((color) => <button key={color} disabled={matchControlBusy || !followingLive || connection !== "live"} onClick={() => prepareTakeover(color)}>Apply {capitalize(color)} seat</button>)}
                <button disabled={matchControlBusy || !followingLive || connection !== "live"} onClick={() => void onMatchControl("resume")}>Resume match</button>
              </div>
              <div className="secondary-actions">
                {(["white", "black"] as const).filter(color => (game.seat_history ?? []).some(change => change.color === color)).map(color => <button key={color} disabled={matchControlBusy || !followingLive || connection !== "live"} onClick={() => prepareTakeover(color, true)}>Restore previous {color} player</button>)}
              </div>
            </>}
            {(game?.lifecycle === "running" || game?.lifecycle === "paused") && <div className="secondary-actions">
              <button disabled={busy || matchControlBusy || !followingLive || connection !== "live"} onClick={() => openMatchAction("abort")}>Abort match</button>
              <button disabled={busy || matchControlBusy || !followingLive || connection !== "live"} onClick={() => openMatchAction("adjudicate")}>Adjudicate…</button>
            </div>}
            {!!game?.seat_history?.length && <details className="seat-history">
              <summary>Seat history · {game.seat_history.length} changes · exhibition</summary>
              <ol>{game.seat_history.map((change) => <li key={change.position_version}>
                <strong>{capitalize(change.color)}</strong>: {change.previous_player.display_name} → {change.player.display_name}
                <small>After move {Math.ceil(change.after_ply / 2)} · {change.player.provider} · {change.player.division.replaceAll("_", " ")}</small>
              </li>)}</ol>
            </details>}
          </section>

          </details>

          <details className="workspace-section">
            <summary>Connections &amp; API access <span>Remote runners, provider setup</span></summary>
            <p>Direct-provider API keys are configured on the server. This browser never collects keys. Choose configured providers, including OpenRouter, in Seats &amp; game setup.</p>
            {runnerAccessDenied && <p>Runner pairing is unavailable on this private connection. Existing player access is unchanged.</p>}
          {!runnerAccessDenied && <div className="runner-pairing-panel" aria-label="Remote runner pairing">
            <div className="runner-pairing-heading">
              <div>
                <span>{runnerConnectionMode === "subscription_bridge" ? "SUBSCRIPTION BRIDGE · EXPERIMENTAL" : "REMOTE RUNNER"}</span>
                <strong>Pair once. Play unattended.</strong>
              </div>
              <button onClick={() => void refreshRunnerSessions()} disabled={busy}>Refresh</button>
            </div>
            <label>
              Connection type
              <select
                aria-label="Runner connection type"
                value={runnerConnectionMode}
                onChange={(event) => setRunnerConnectionMode(event.target.value as RunnerConnectionMode)}
              >
                <option value="remote_runner">External agent</option>
                <option value="subscription_bridge">Subscription bridge (Codex CLI)</option>
              </select>
            </label>
            <div className="runner-pairing-fields">
              <label>Agent name<input aria-label="Remote agent name" value={runnerName} onChange={(event) => setRunnerName(event.target.value)} /></label>
              {runnerConnectionMode === "subscription_bridge" ? (
                <label>Provider<span>OpenAI · local Codex CLI</span></label>
              ) : (
                <label>Provider<input aria-label="Remote agent provider" value={runnerProvider} onChange={(event) => setRunnerProvider(event.target.value)} /></label>
              )}
              {runnerConnectionMode === "subscription_bridge" ? (
                <label>Codex CLI model<input aria-label="Codex CLI model" value={subscriptionModel} onChange={(event) => setSubscriptionModel(event.target.value)} placeholder="Enter the exact CLI model name" /></label>
              ) : (
                <label>Model<input aria-label="Remote agent model" value={runnerModel} onChange={(event) => setRunnerModel(event.target.value)} /></label>
              )}
            </div>
            {runnerConnectionMode === "subscription_bridge" && (
              <p className="runner-subscription-disclosure">
                Uses the official OpenAI Codex CLI authorization on the bridge machine. Subscription credentials stay local and are not uploaded to the Lounge. This runner is limited to the open_agentic division, uses provider-default effort, and requires a one-match authorization each time.
              </p>
            )}
            <p>Authorizes the next match only. Reconnects keep the original clock and limits. Pair again for another game.</p>
            <div className="runner-pairing-fields">
              <label>Maximum turn requests<input aria-label="Runner turn limit" type="number" min={1} max={2000} value={runnerMaxTurns} onChange={(event) => setRunnerMaxTurns(Number(event.target.value))} /></label>
              <label>Authorization minutes<input aria-label="Runner authorization minutes" type="number" min={1} max={1440} value={runnerMatchMinutes} onChange={(event) => setRunnerMatchMinutes(Number(event.target.value))} /></label>
            </div>
            <IdentityEditor label="Runner pairing" value={runnerIdentity} onChange={setRunnerIdentity} />
            <button className="runner-pairing-create" onClick={() => void generateRunnerPairing()} disabled={busy || !Number.isInteger(runnerMaxTurns) || runnerMaxTurns < 1 || runnerMaxTurns > 2000 || !Number.isInteger(runnerMatchMinutes) || runnerMatchMinutes < 1 || runnerMatchMinutes > 1440 || !runnerName.trim() || (runnerConnectionMode === "subscription_bridge" ? !subscriptionModel.trim() : !runnerProvider.trim() || !runnerModel.trim())}>
              Generate one-time pairing
            </button>
            {runnerPairing && (
              <div
                className="runner-pairing-code"
                style={runnerPairing.player.connection_mode === "subscription_bridge"
                  ? { alignItems: "stretch", paddingRight: 10 }
                  : undefined}
              >
                <span>PAIRING CODE · EXPIRES {new Date(runnerPairing.expires_at).toLocaleTimeString()}</span>
                <code style={runnerPairing.player.connection_mode === "subscription_bridge" ? wrappedCodeStyle : undefined}>
                  {runnerPairing.pairing_code}
                </code>
                <button
                  style={runnerPairing.player.connection_mode === "subscription_bridge"
                    ? { position: "static", transform: "none", alignSelf: "flex-start" }
                    : undefined}
                  onClick={() => void copyText(runnerPairing.pairing_code, "Pairing code")}
                >Copy code</button>
                {runnerPairing.player.connection_mode === "subscription_bridge" && (
                  <div
                    className="runner-subscription-instructions"
                    aria-label="Codex CLI subscription bridge instructions"
                    style={{ display: "grid", gap: 7, minWidth: 0, width: "100%" }}
                  >
                    <span>PAIRING ID</span>
                    <code style={wrappedCodeStyle}>{runnerPairing.pairing_id}</code>
                    <p>On the machine running the bridge, first check setup, then start it. The pairing code is prompted locally.</p>
                    <code style={wrappedCodeStyle}>lounge-subscription-bridge doctor --model MODEL</code>
                    <code style={wrappedCodeStyle}>lounge-subscription-bridge run --pairing-id {runnerPairing.pairing_id} --model MODEL --authorize-next-match</code>
                    <small>Pairing model: <strong>{runnerPairing.player.model}</strong>. Use that exact model as MODEL. The next-match grant is required for each match.</small>
                  </div>
                )}
                {runnerPairing.player.connection_mode !== "subscription_bridge" && (
                  <div
                    className="runner-sdk-instructions"
                    aria-label="Remote runner SDK instructions"
                    style={{ display: "grid", gap: 7, minWidth: 0, width: "100%" }}
                  >
                    <span>PAIRING ID</span>
                    <code style={wrappedCodeStyle}>{runnerPairing.pairing_id}</code>
                    <button
                      style={{ position: "static", transform: "none", justifySelf: "start" }}
                      onClick={() => void copyText(runnerPairing.pairing_id, "Pairing ID")}
                    >Copy pairing ID</button>
                    <p>Send the pairing ID and code to the runner over a trusted channel. The runner prompts for the code locally.</p>
                    <code style={wrappedCodeStyle}>lounge-sample-bot --base-url {window.location.origin} --pairing-id {runnerPairing.pairing_id}</code>
                  </div>
                )}
              </div>
            )}
            <div className="runner-presence">
              <span>{activeRunnerSessions.length} ready for a new match</span>
              {runnerSessions.filter((session) => !session.expired && !session.revoked).map((session) => (
                <small key={session.session_id} className={session.connected ? "connected" : "standby"}>
                  {session.display_name} · {session.connected ? "live" : "standby"}
                  {session.match_grant && <span> · Bound to {session.match_grant.color} · {session.match_grant.turns_dispatched}/{session.match_grant.max_turns} turn requests</span>}
                  <button disabled={busy} aria-label={`Revoke ${session.display_name}`} onClick={() => void revokeRunner(session.session_id)}>Revoke access</button>
                </small>
              ))}
            </div>
          </div>}
          </details>
          <details className="workspace-section">
            <summary>Board preferences <span>Motion, spectator pacing, sound</span></summary>
            <BoardSoundControls sound={boardSound} />
          </details>
          <details className="workspace-section">
            <summary>Match actions &amp; export <span>Resign, draw, reset, download</span></summary>
          <div className="secondary-actions">
            {canRetryAgent && (
              <button onClick={() => void onRetryAgentTurn()} disabled={busy}>
                Retry agent turn
              </button>
            )}
            <button onClick={onReset} disabled={!game || matchEnded || busy || matchControlBusy || connection !== "live"}>Reset</button>
            {(["white", "black"] as const).filter((color) => game?.[`${color}_player`].connection_mode === "human").map((color) => (
              <button key={color} onClick={() => setHumanAction(color)} disabled={!game || busy || game.status !== "active" || !followingLive || connection !== "live"}>
                Resign {color === "white" ? "White" : "Black"}
              </button>
            ))}
            <button onClick={() => setHumanAction("draw")} disabled={!playerCanMove || (!game?.can_claim_draw && !game?.draw_claim_moves?.length)} title="Available for threefold repetition or the fifty-move rule">
              Claim draw
            </button>
            <button onClick={() => game && void copyText(permalink(game.id), "Match link")}>Copy link</button>
            <button onClick={() => downloadGame("pgn")} disabled={!game}>Export PGN</button>
          </div>

          </details>

          <div className="integrity-note">
            <span>BROADCAST INTEGRITY</span>
            Evaluation runs in a separate spectator engine and never chooses the competitor’s move. Public strategy cards contain declared or position-derived summaries—not hidden model reasoning.
          </div>
        </aside>
      </section>

      {showLab && <ModelLab catalog={playerAdapters} />}
      {showLeaderboards && <><section className="model-lab" aria-label="Next match identity"><h2>Next match identity</h2><p>Optional declarations are saved when a new match starts. Existing game identities remain unchanged. Remote seats use the declarations saved during pairing.</p>{whiteSeat !== "remote_runner" && <IdentityEditor label="White next match" value={whiteIdentity} onChange={setWhiteIdentity} />}{blackSeat !== "remote_runner" && <IdentityEditor label="Black next match" value={blackIdentity} onChange={setBlackIdentity} />}</section><Leaderboards /></>}

      <footer className="lounge-footer"><span>AI Chess Lounge</span><span>Provider-neutral broadcast shell</span><span>PGN · FEN · JSON · Replay</span></footer>
      {promotion && <PromotionPicker color={promotion.color} onChoose={choosePromotion} onCancel={cancelPromotion} />}
      {takeover && game && <SeatTakeoverDialog color={takeover.color} current={game[`${takeover.color}_player`]} player={takeover.player} busy={matchControlBusy} onConfirm={() => void confirmTakeover()} onCancel={() => setTakeover(null)} />}
      {matchAction && game && <MatchActionDialog action={matchAction} targetLabel={matchActionTarget.current?.label} nextMatchLabel={`${seatChoiceLabel(whiteSeat)} vs ${seatChoiceLabel(blackSeat)}`} busy={busy || matchControlBusy} onCancel={() => setMatchAction(null)} onConfirm={(result) => void onMatchAction(result)} />}
      {humanAction && game && <HumanActionDialog action={humanAction} claimMoves={game.draw_claim_moves ?? []} busy={busy} onCancel={() => setHumanAction(null)} onConfirm={(move) => void onHumanAction(move)} />}
      <div className="sr-only" aria-live="polite">Position {displayPly}. {selectedPoint ? formatEvaluation(selectedPoint) : "Evaluation pending"}.</div>
    </main>
  );
}

function PlayerCard({ side, title, provider, configuration, division, cost, latency, badge, active, clock, urgent }: PlayerCardProps) {
  return (
    <div className={`player-card ${side} ${active ? "active" : ""}`}>
      <div className={`player-avatar ${side}`}>{side === "white" ? "♔" : "♚"}</div>
      <div className="player-copy">
        <div className="player-name-line"><strong>{title}</strong><span className="player-badge">{badge}</span></div>
        <span>{provider} · {configuration}</span>
        <div className="player-chips"><small>{division}</small><small>{latency}</small><small>{cost}</small></div>
      </div>
      <strong className={`player-clock ${urgent ? "urgent" : ""}`}>{clock}</strong>
    </div>
  );
}

function StrategyChannel({ white, black, activeSide, pv, depth }: {
  white: string;
  black: string;
  activeSide: "white" | "black";
  pv: string[];
  depth: number | null;
}) {
  return (
    <div className="strategy-channel" aria-label="Public strategy channel">
      <div className={activeSide === "black" ? "strategy-card active" : "strategy-card"}><span><b>BLACK</b> PUBLIC PLAN</span><strong>{black}</strong></div>
      <div className="strategy-center" aria-label="Spectator principal variation"><span>◇</span><small>{pv.length ? `Spectator PV · ${pv.slice(0, 4).join(" ")}` : "Public summaries only"}</small>{depth && <em>D{depth}</em>}</div>
      <div className={activeSide === "white" ? "strategy-card active" : "strategy-card"}><span><b>WHITE</b> PUBLIC PLAN</span><strong>{white}</strong></div>
    </div>
  );
}

function MoveButton({ san, ply, selected, classification, onSelect }: {
  san?: string;
  ply: number;
  selected: boolean;
  classification: AnalysisPoint["classification"];
  onSelect: (ply: number) => void;
}) {
  return <button className={selected ? "selected" : ""} onClick={() => onSelect(ply)} disabled={!san}><span>{san ?? "…"}</span>{classification && <i className={`classification ${classification}`}>{classification}</i>}</button>;
}

function AnalysisPanel({ analysis, loading, error, selectedPly, selectedPoint, onSelect }: {
  analysis: GameAnalysis | null;
  loading: boolean;
  error: string | null;
  selectedPly: number;
  selectedPoint: AnalysisPoint | null;
  onSelect: (ply: number) => void;
}) {
  if (!analysis && loading) return <div className="analysis-state"><span className="analysis-spinner" />Running spectator Stockfish…</div>;
  if (!analysis && error) return <div className="analysis-state error">Analysis unavailable: {error}</div>;
  if (!analysis) return <div className="analysis-state">Analysis will appear after the match loads.</div>;
  return (
    <div className="analysis-panel">
      <div className="analysis-headline"><div><span>SPECTATOR ENGINE</span><strong>{analysis.engine_version ?? analysis.engine_name}</strong></div><b>{formatEvaluation(selectedPoint)}</b></div>
      <EvaluationChart points={analysis.points} selectedPly={selectedPly} onSelect={onSelect} />
      <div className="principal-variation"><span>Principal variation</span><strong>{selectedPoint?.pv_san.length ? selectedPoint.pv_san.join(" ") : "No forced line available"}</strong></div>
      <div className="analysis-footnote">White perspective · {selectedPoint?.depth ? `depth ${selectedPoint.depth}` : "depth pending"} · isolated from move selection</div>
    </div>
  );
}

function Metric({ label, value, accent = false }: { label: string; value: string; accent?: boolean }) {
  return <div className="metric"><span>{label}</span><strong className={accent ? "accent" : ""}>{value}</strong></div>;
}

function SeatOptions({ catalog, runners }: {
  catalog: PlayerAdapterCatalog | null;
  runners: RunnerSessionStatus[];
}) {
  return (
    <>
      <option value="human">Human player</option>
      <option value="stockfish">Stockfish</option>
      <option value="scripted">Deterministic agent</option>
      <option value="remote_runner" disabled={!runners.length}>
        Paired remote agent{runners.length ? "" : " · pair below"}
      </option>
      {(Object.keys(providerDetails) as AgentProviderChoice[]).map((choice) => {
        const selectable = selectableProviderModels(choice, catalog).length > 0;
        const label = providerDetails[choice].label;
        return (
          <option key={choice} value={choice} disabled={!selectable}>
            {label} model{selectable ? "" : " · not configured"}
          </option>
        );
      })}
    </>
  );
}

function seatChoiceLabel(choice: SeatChoice): string {
  if (choice === "stockfish") return "Stockfish";
  if (choice === "scripted") return "Deterministic Agent";
  if (choice === "openai") return "OpenAI";
  if (choice === "anthropic") return "Claude";
  if (choice === "google") return "Gemini";
  if (choice === "openrouter") return "OpenRouter";
  if (choice === "ollama") return "Ollama";
  if (choice === "vllm") return "vLLM";
  if (choice === "remote_runner") return "Remote Agent";
  return "Human";
}

function RunnerSeatControls({
  color,
  runners,
  selectedRunnerId,
  onRunnerChange,
}: {
  color: Color;
  runners: RunnerSessionStatus[];
  selectedRunnerId: string;
  onRunnerChange: (runnerId: string) => void;
}) {
  return (
    <div className="provider-seat-controls" role="group" aria-label={`${capitalize(color)} remote runner settings`}>
      <label>
        {capitalize(color)} paired agent
        <select
          aria-label={`${capitalize(color)} paired agent`}
          value={selectedRunnerId}
          onChange={(event) => onRunnerChange(event.target.value)}
          disabled={!runners.length}
        >
          {!runners.length && <option value="">No paired runner</option>}
          {runners.map((session) => (
            <option key={session.session_id} value={session.player_id}>
              {session.display_name} · {session.model} · {session.connected ? "live" : "standby"}
            </option>
          ))}
        </select>
      </label>
    </div>
  );
}

function ProviderSeatControls({
  providerChoice,
  color,
  models,
  catalog,
  selectedModel,
  selectedEffort,
  onModelChange,
  onEffortChange,
}: {
  providerChoice: AgentProviderChoice;
  color: Color;
  models: string[];
  catalog: PlayerAdapterCatalog | null;
  selectedModel: string;
  selectedEffort: EffortLevel;
  onModelChange: (model: string) => void;
  onEffortChange: (effort: EffortLevel) => void;
}) {
  const providerLabel = providerDetails[providerChoice].label;
  const effortOptions = models.length
    ? loungeEffortsForModel(providerChoice, selectedModel, catalog)
    : [];
  return (
    <div className="provider-seat-controls" role="group" aria-label={`${capitalize(color)} ${providerLabel} settings`}>
      <label>
        {capitalize(color)} {providerLabel} model
        <select aria-label={`${capitalize(color)} ${providerLabel} model`} value={selectedModel} onChange={(event) => onModelChange(event.target.value)} disabled={!models.length}>
          {models.map((model) => <option key={model} value={model}>{model}</option>)}
        </select>
      </label>
      <label>
        {capitalize(color)} effort
        <select aria-label={`${capitalize(color)} effort`} value={effortOptions.length ? selectedEffort : ""} onChange={(event) => onEffortChange(event.target.value as EffortLevel)} disabled={!effortOptions.length}>
          {!effortOptions.length && <option value="">Provider default</option>}
          {effortOptions.map((effort) => <option key={effort} value={effort}>{capitalize(effort)}</option>)}
        </select>
      </label>
    </div>
  );
}

function createPlayerConfiguration(
  choice: Exclude<SeatChoice, AgentProviderChoice | "remote_runner">,
  color: "white" | "black",
  stockfishElo: StockfishChoice,
): PlayerConfiguration {
  if (choice === "stockfish") {
    return {
      protocol_version: "1.0",
      player_id: `local-stockfish-${color}`,
      adapter_id: "stockfish",
      display_name: stockfishElo === "full" ? "Stockfish full strength" : `Stockfish ${stockfishElo}`,
      provider: "Local UCI",
      model: "Stockfish",
      connection_mode: "local",
      effort: "balanced",
      division: "engine_assisted",
      settings: {
        color,
        target_elo: stockfishElo === "full" ? 1600 : stockfishElo,
        full_strength: stockfishElo === "full",
        move_time_ms: (stockfishElo === "full" || stockfishElo >= 2500) ? 700 : 400,
        spectator_delay_ms: 80,
      },
    };
  }
  if (choice === "scripted") {
    return {
      protocol_version: "1.0",
      player_id: `local-scripted-${color}`,
      adapter_id: "scripted",
      display_name: `Deterministic ${color === "white" ? "White" : "Black"}`,
      provider: "Lounge Protocol",
      model: "deterministic-v1",
      connection_mode: "local",
      effort: null,
      division: "legal_assist",
      settings: { moves: [], spectator_delay_ms: 180 },
    };
  }
  return {
    protocol_version: "1.0",
    player_id: `local-human-${color}`,
    adapter_id: "human",
    display_name: `Human ${color === "white" ? "White" : "Black"}`,
    provider: "Human seat",
    model: "Manual input",
    connection_mode: "human",
    effort: null,
    division: "legal_assist",
    settings: { color },
  };
}

function createSelectedPlayerConfiguration(
  choice: SeatChoice,
  color: Color,
  stockfishElo: StockfishChoice,
  requestedModel: string,
  requestedEffort: EffortLevel,
  catalog: PlayerAdapterCatalog | null,
  requestedRunnerId: string,
  runners: RunnerSessionStatus[],
  comparison?: IdentityDeclaration,
): PlayerConfiguration {
  if (choice === "remote_runner") {
    const runner = runners.find((candidate) => candidate.player_id === requestedRunnerId)
      ?? runners[0];
    if (runner) return runner.player;
    const playerId = "remote-runner-unpaired";
    return {
      protocol_version: "1.0",
      player_id: playerId,
      adapter_id: "remote_runner",
      display_name: "Unpaired Remote Agent",
      provider: "Remote runner",
      model: "unpaired",
      connection_mode: "remote_runner",
      effort: null,
      division: "legal_assist",
      settings: { runner_id: playerId, move_timeout_ms: 30_000 },
    };
  }
  if (!isAgentProvider(choice)) {
    return { ...createPlayerConfiguration(choice, color, stockfishElo), ...(comparison && Object.keys(comparison).length ? { comparison } : {}) };
  }

  const provider = providerDetails[choice];
  const model = selectedProviderModel(
    requestedModel,
    selectableProviderModels(choice, catalog),
  );
  const effortOptions = loungeEffortsForModel(choice, model, catalog);
  const effort = effortOptions.includes(requestedEffort)
    ? requestedEffort
    : effortOptions.length
      ? defaultProviderEffort(choice, model, catalog)
      : null;
  const capabilities = providerCapabilities(choice, model, catalog);
  return {
    protocol_version: catalog?.protocol_version ?? "1.0",
    player_id: `local-${choice}-${color}`,
    adapter_id: choice,
    display_name: `${model} · ${effort ? capitalize(effort) : "Provider default"}`,
    provider: provider.provider,
    model,
    connection_mode: capabilities?.connection_mode ?? "direct_api",
    effort,
    division: "legal_assist",
    settings: { ...providerPublicSettings },
    ...(comparison && Object.keys(comparison).length ? { comparison } : {}),
  };
}

function isAgentProvider(choice: SeatChoice): choice is AgentProviderChoice {
  return choice in providerDetails;
}

function selectableProviderModels(
  providerChoice: AgentProviderChoice,
  catalog: PlayerAdapterCatalog | null,
): string[] {
  const adapter = catalog?.adapters.find(
    (candidate) => candidate.adapter_id === providerChoice,
  );
  if (!adapter) return [];
  return adapter.models.filter((model) => adapter.capabilities[model]?.selectable === true);
}

function providerCapabilities(
  providerChoice: SeatChoice,
  model: string,
  catalog: PlayerAdapterCatalog | null,
): AdapterModelCapabilities | undefined {
  if (!isAgentProvider(providerChoice)) return undefined;
  return catalog?.adapters.find((candidate) => candidate.adapter_id === providerChoice)
    ?.capabilities[model];
}

function loungeEffortsForModel(
  providerChoice: SeatChoice,
  model: string,
  catalog: PlayerAdapterCatalog | null,
): EffortLevel[] {
  const advertised = providerCapabilities(providerChoice, model, catalog)?.effort_levels ?? [];
  return loungeEffortLevels.filter((effort) => advertised.includes(effort));
}

function selectedProviderModel(requested: string, available: string[]): string {
  return available.includes(requested) ? requested : available[0] ?? "";
}

function defaultProviderEffort(
  providerChoice: SeatChoice,
  model: string,
  catalog: PlayerAdapterCatalog | null,
): EffortLevel {
  const available = loungeEffortsForModel(providerChoice, model, catalog);
  return available.includes("balanced") ? "balanced" : available[0] ?? "balanced";
}

function capitalize(value: string): string {
  return value.charAt(0).toUpperCase() + value.slice(1);
}

function strategyForSeat(
  game: GameSnapshot | null,
  color: "white" | "black",
  player: PlayerConfiguration,
): string {
  const afterPly = (game?.seat_history ?? []).filter(change => change.color === color).at(-1)?.after_ply ?? 0;
  const move = game?.moves.filter(candidate => candidate.ply > afterPly &&
    (color === "white" ? candidate.ply % 2 === 1 : candidate.ply % 2 === 0)).at(-1);
  if (game?.status === "active" && game.turn === color) {
    return player.adapter_id === "human"
      ? "Human-controlled decision. No private reasoning is captured."
      : `${player.display_name} is selecting a move through the ${player.adapter_id} adapter.`;
  }
  if (move?.player_metadata?.plan) return move.player_metadata.plan;
  if (move) return `Committed ${move.san}; awaiting the next turn.`;
  return `${player.display_name} is waiting for the opening position.`;
}

function playerCardForSeat(
  game: GameSnapshot | null,
  side: "white" | "black",
  player: PlayerConfiguration,
  clockMs: number,
): PlayerCardProps {
  const active = game?.status === "active" && game.turn === side;
  const afterPly = (game?.seat_history ?? []).filter(change => change.color === side).at(-1)?.after_ply ?? 0;
  const move = game?.moves.filter(candidate => candidate.ply > afterPly &&
    (side === "white" ? candidate.ply % 2 === 1 : candidate.ply % 2 === 0)).at(-1);
  const metadata = move?.player_metadata;
  const targetElo = player.settings.target_elo;
  const moveTime = player.settings.move_time_ms;
  const configuration = player.adapter_id === "stockfish"
    ? `${player.settings.full_strength ? "Full strength" : `${typeof targetElo === "number" ? targetElo : "—"} target Elo`} · ${typeof moveTime === "number" ? moveTime : "—"} ms budget`
    : player.adapter_id === "human"
      ? "Manual input · server validated"
      : `${player.model} · protocol v1.0`;
  const knownCost = metadata?.usage.estimated_cost_usd;
  const consulted = player.adapter_id === "human" && (game?.consultations ?? []).some(c => c.color === side);
  return {
    side,
    title: player.display_name,
    provider: player.provider,
    configuration,
    division: consulted ? "Human + AI Team" : player.division.replaceAll("_", " "),
    cost: consulted ? "Advice tracked below" : knownCost !== null && knownCost !== undefined
      ? `$${knownCost.toFixed(4)}`
      : player.connection_mode === "local" || player.connection_mode === "human"
        ? "Local · $0"
        : "Cost pending",
    latency: metadata ? `${metadata.latency_ms} ms` : player.adapter_id === "human" ? "Human controlled" : "Awaiting move",
    badge: active ? (player.adapter_id === "human" ? "YOUR MOVE" : "THINKING") : side.toUpperCase(),
    active: Boolean(active),
    clock: formatClock(clockMs),
    urgent: Boolean(active && clockMs <= 10_000),
  };
}

function projectClocks(game: GameSnapshot | null, nowMs: number, sync: ClockSync | null): { white: number; black: number } {
  if (!game) return { white: 0, black: 0 };
  let white = game.clock.white_remaining_ms;
  let black = game.clock.black_remaining_ms;
  if (game.lifecycle === "running" && game.status === "active") {
    const synchronized = sync?.gameId === game.id && sync.generation === game.generation && sync.revision === game.revision;
    const elapsed = synchronized ? Math.max(0, nowMs - sync.receivedAt) : 0;
    if (game.turn === "white") white = Math.max(0, white - elapsed);
    else black = Math.max(0, black - elapsed);
  }
  return { white, black };
}

function formatClock(milliseconds: number): string {
  const safe = Math.max(0, milliseconds);
  const minutes = Math.floor(safe / 60_000);
  const seconds = Math.floor((safe % 60_000) / 1_000);
  if (safe < 10_000) return `${minutes}:${String(seconds).padStart(2, "0")}.${Math.floor((safe % 1_000) / 100)}`;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

function formatEvaluation(point: AnalysisPoint | null): string {
  if (!point) return "—";
  if (point.mate === 0) return "Mate";
  if (point.mate !== null) return point.mate > 0 ? `M${point.mate}` : `−M${Math.abs(point.mate)}`;
  const pawns = point.score_cp / 100;
  return `${pawns >= 0 ? "+" : ""}${pawns.toFixed(2)}`;
}

function evaluationShare(point: AnalysisPoint | null): number {
  if (!point) return 50;
  // Mate 0 means the side to move is checkmated; fill the bar for the winner.
  if (point.mate === 0) return point.fen.split(" ")[1] === "w" ? 5 : 95;
  const score = point.mate !== null ? Math.sign(point.mate) * 100_000 : point.score_cp;
  return Math.max(5, Math.min(95, 50 + Math.tanh(score / 420) * 45));
}

function permalink(gameId: string): string {
  return `${window.location.origin}/games/${gameId}`;
}

function downloadText(content: string, filename: string, format: "pgn" | "json") {
  const blob = new Blob([content], { type: format === "pgn" ? "application/x-chess-pgn;charset=utf-8" : "application/json;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

export default App;

const pauseReasons: Record<string, string> = {
  illegal_move: "proposed an illegal move",
  move_deadline_exceeded: "did not answer before its move deadline",
  adapter_error: "could not produce a move",
  stale_or_mismatched_response: "answered for an earlier position",
  runner_authorization_unavailable: "is no longer authorized; pair it again or change the seat",
  provider_turn_interrupted: "was interrupted during its request",
};

/** Explain the latest pause from the ordered event log. */
function describePause(events: MatchEvent[], game: GameSnapshot): string {
  let pausedIndex = -1;
  for (let index = events.length - 1; index >= 0; index -= 1) {
    if (events[index].type === "match.paused") { pausedIndex = index; break; }
  }
  const failure = pausedIndex > 0 ? events[pausedIndex - 1] : undefined;
  if (failure?.type !== "agent.failed") return "Paused by an operator.";
  const playerId = failure.payload.player_id;
  const color = game.white_player.player_id === playerId ? "white" : game.black_player.player_id === playerId ? "black" : null;
  const who = color ? `${capitalize(color)} (${game[`${color}_player`].display_name})` : "An automated player";
  const reason = String(failure.payload.reason ?? "");
  const what = pauseReasons[reason] ?? `failed: ${reason.replaceAll("_", " ") || "unknown error"}`;
  return `Paused because ${who} ${what}. Retry the agent turn, change the seat, or abort.`;
}

const terminationLabels: Record<string, string> = {
  checkmate: "Checkmate",
  stalemate: "Stalemate",
  insufficient_material: "Draw · insufficient material",
  fivefold_repetition: "Draw · fivefold repetition",
  seventyfive_moves: "Draw · 75-move rule",
  threefold_repetition: "Draw claimed · threefold repetition",
  fifty_move_rule: "Draw claimed · fifty-move rule",
  timeout: "Lost on time",
  resignation: "Resignation",
  adjudicated: "Adjudicated",
  aborted: "Aborted",
};

function terminationLabel(reason: string): string {
  return terminationLabels[reason] ?? reason.replaceAll("_", " ");
}
