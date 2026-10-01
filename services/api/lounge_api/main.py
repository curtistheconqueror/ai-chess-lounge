from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .domain import MoveRejected, StalePosition
from .manager import GameManager, GameNotFound
from .models import CreateGameRequest, GameSnapshot, HealthResponse, MoveRequest


manager = GameManager()


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    await manager.close()


app = FastAPI(
    title="AI Chess Lounge API",
    version=__version__,
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(version=__version__, stockfish_available=manager.engine.available)


@app.post("/api/games", response_model=GameSnapshot, status_code=201)
async def create_game(request: CreateGameRequest) -> GameSnapshot:
    try:
        game = await manager.create(request)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return game.snapshot()


@app.get("/api/games/{game_id}", response_model=GameSnapshot)
async def get_game(game_id: str) -> GameSnapshot:
    try:
        return manager.get(game_id).snapshot()
    except GameNotFound as exc:
        raise HTTPException(status_code=404, detail="Game not found.") from exc


@app.post("/api/games/{game_id}/moves", response_model=GameSnapshot)
async def make_move(game_id: str, request: MoveRequest) -> GameSnapshot:
    try:
        return await manager.make_human_move(game_id, request.move, request.position_version)
    except GameNotFound as exc:
        raise HTTPException(status_code=404, detail="Game not found.") from exc
    except StalePosition as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except MoveRejected as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/api/games/{game_id}/reset", response_model=GameSnapshot)
async def reset_game(game_id: str) -> GameSnapshot:
    try:
        return await manager.reset(game_id)
    except GameNotFound as exc:
        raise HTTPException(status_code=404, detail="Game not found.") from exc


@app.post("/api/games/{game_id}/resign", response_model=GameSnapshot)
async def resign_game(game_id: str) -> GameSnapshot:
    try:
        return await manager.resign(game_id)
    except GameNotFound as exc:
        raise HTTPException(status_code=404, detail="Game not found.") from exc
    except MoveRejected as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.websocket("/ws/games/{game_id}")
async def game_socket(websocket: WebSocket, game_id: str) -> None:
    try:
        await manager.subscribe(game_id, websocket)
    except GameNotFound:
        await websocket.close(code=4404, reason="Game not found")
        return
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.unsubscribe(game_id, websocket)


web_dist = Path(__file__).resolve().parents[3] / "apps" / "web" / "dist"
if web_dist.is_dir():
    assets = web_dist / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str) -> FileResponse:
        candidate = web_dist / path
        if path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(web_dist / "index.html")
