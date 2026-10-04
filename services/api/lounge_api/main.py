from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Query, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__
from .adapters import AdapterConfigurationError
from .domain import ClockExpired, MatchTransitionRejected, MoveRejected, StalePosition
from .engine import EngineFailure
from .experiment_metrics import ExperimentMetrics
from .experiment_queue import QueueConflict
from .experiment_reports import ExperimentReports, ReportConflict, ReportTooLarge
from .experiment_worker import ExperimentWorker
from .experiments import ExperimentService, PlanConfiguration, SaveExperiment
from .manager import AnalysisSuperseded, GameManager, GameNotFound
from .models import (
    AdjudicateRequest,
    ConsultationRequest,
    CreateGameRequest,
    DrawClaimRequest,
    GameAnalysis,
    GameSnapshot,
    HealthResponse,
    LifecycleRequest,
    MatchEvent,
    MoveRequest,
    ResignRequest,
    RunnerPairingClaim,
    RunnerPairingCreate,
    RunnerPairingResponse,
    RunnerProposalReceipt,
    RunnerProposalSubmission,
    RunnerSessionCredentials,
    RunnerSessionStatus,
    RunnerTurnDelivery,
    SeatTakeoverRequest,
)
from .operations import LocalOperations, OperationsMiddleware, Readiness
from .persistence import ConcurrentGameUpdate, IdempotencyConflict
from .player_protocol import PROTOCOL_VERSION
from .remote_runner import (
    RunnerAuthenticationError,
    RunnerPairingError,
    RunnerSubmissionError,
    bearer_token,
)

web_dist = Path(__file__).resolve().parents[3] / "apps" / "web" / "dist"
repository_root = Path(__file__).resolve().parents[3]
load_dotenv(repository_root / ".env.local", override=False)
load_dotenv(repository_root / ".env", override=False)


class CreateExperimentRun(BaseModel):
    id: UUID
    concurrency: int = Field(default=1, ge=1, le=4)


class ControlExperimentRun(BaseModel):
    target: Literal["running", "paused", "cancelled"]
    expected_revision: int = Field(ge=0)
    allow_provider_calls: bool = False


def create_app(game_manager: GameManager | None = None) -> FastAPI:
    active_manager = game_manager or GameManager()

    batch_worker = ExperimentWorker(active_manager)
    export_slots = asyncio.Semaphore(2)
    operations = LocalOperations()
    readiness = Readiness(active_manager, batch_worker)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        await active_manager.start()
        batch_worker.start()
        readiness.started = True
        try:
            yield
        finally:
            await readiness.close()
            await batch_worker.close()
            await active_manager.close()

    application = FastAPI(
        title="AI Chess Lounge API",
        version=__version__,
        lifespan=lifespan,
    )
    application.state.game_manager = active_manager
    application.state.operations = operations
    application.state.readiness = readiness
    application.add_middleware(OperationsMiddleware, operations=operations)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    experiments = ExperimentService(active_manager.store, active_manager.adapters)

    @application.post("/api/experiments/preview")
    async def preview_experiment(request: PlanConfiguration):
        try:
            return experiments.preview(request)
        except (ValueError, AdapterConfigurationError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @application.post("/api/experiments", status_code=201)
    async def save_experiment(request: SaveExperiment):
        try:
            return await experiments.save(request)
        except FileExistsError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except (ValueError, AdapterConfigurationError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @application.get("/api/experiments")
    async def list_experiments(offset: Annotated[int, Query(ge=0)] = 0):
        return await experiments.list(offset)

    @application.get("/api/experiments/{experiment_id}")
    async def get_experiment(experiment_id: str):
        result = await experiments.get(experiment_id)
        if result is None:
            raise HTTPException(status_code=404, detail="Experiment not found.")
        return result["document"]

    @application.post("/api/experiments/{experiment_id}/runs", status_code=201)
    async def create_experiment_run(experiment_id: str, request: CreateExperimentRun):
        try:
            return await batch_worker.queue.create(
                experiment_id, str(request.id), request.concurrency
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Experiment not found.") from exc
        except QueueConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @application.get("/api/experiments/{experiment_id}/runs")
    async def list_experiment_runs(experiment_id: str):
        return await batch_worker.queue.list_runs(experiment_id)

    @application.get("/api/experiment-runs/{run_id}")
    async def get_experiment_run(run_id: str):
        try:
            return await batch_worker.queue.snapshot(run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Run not found.") from exc

    @application.get("/api/experiment-runs/{run_id}/metrics")
    async def experiment_metrics(run_id: str):
        try:
            return await ExperimentMetrics(active_manager.store).get(run_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="Run not found.") from None

    @application.get("/api/experiment-runs/{run_id}/bundle")
    async def experiment_bundle(run_id: UUID):
        try:
            async with export_slots:
                content = await ExperimentReports(active_manager.store).bundle(str(run_id))
            return Response(
                content,
                media_type="application/zip",
                headers={
                    "Content-Disposition": f'attachment; filename="experiment-{run_id}.zip"',
                    "Cache-Control": "no-store",
                },
            )
        except KeyError:
            raise HTTPException(status_code=404, detail="Run not found.") from None
        except ReportConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ReportTooLarge as exc:
            raise HTTPException(status_code=413, detail=str(exc)) from exc

    @application.post("/api/experiment-runs/{run_id}/control")
    async def control_experiment_run(run_id: str, request: ControlExperimentRun):
        try:
            return await batch_worker.control(
                run_id, request.target, request.expected_revision, request.allow_provider_calls
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Run not found.") from exc
        except QueueConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except (ValueError, AdapterConfigurationError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @application.get("/api/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse(
            version=__version__, stockfish_available=active_manager.engine.available
        )

    @application.get("/api/ready")
    async def ready(require_engine: bool = False):
        result = await readiness.check(require_engine=require_engine)
        return JSONResponse(
            content={"version": __version__, **result},
            status_code=200 if result["ok"] else 503,
            headers={"Cache-Control": "no-store"},
        )

    @application.get("/api/player-adapters")
    async def player_adapters() -> dict[str, object]:
        return {
            "protocol_version": PROTOCOL_VERSION,
            "adapters": active_manager.adapters.catalog(),
        }

    @application.get("/api/player-adapters/reliability")
    async def player_adapter_reliability() -> dict[str, object]:
        return active_manager.provider_reliability_status()

    @application.post(
        "/api/runner-pairings",
        response_model=RunnerPairingResponse,
        status_code=201,
    )
    async def create_runner_pairing(request: RunnerPairingCreate) -> RunnerPairingResponse:
        try:
            return await active_manager.remote_runners.create_pairing(request)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @application.post(
        "/api/runner-pairings/{pairing_id}/claim",
        response_model=RunnerSessionCredentials,
    )
    async def claim_runner_pairing(
        pairing_id: str,
        request: RunnerPairingClaim,
    ) -> RunnerSessionCredentials:
        try:
            return await active_manager.remote_runners.claim_pairing(
                pairing_id,
                request.pairing_code,
            )
        except RunnerPairingError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @application.get(
        "/api/runner-sessions",
        response_model=list[RunnerSessionStatus],
    )
    async def runner_sessions() -> list[RunnerSessionStatus]:
        return await active_manager.remote_runners.statuses()

    @application.post("/api/runner-sessions/{session_id}/revoke", status_code=204)
    async def revoke_runner(session_id: str) -> Response:
        # Operator-only in the loopback deployment, like pairing and match controls.
        try:
            await active_manager.remote_runners.revoke(session_id)
        except RunnerPairingError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return Response(status_code=204)

    @application.get("/api/runner-sessions/{session_id}/audit")
    async def runner_audit(session_id: str) -> list[dict[str, object]]:
        return await active_manager.store.runner_audit(session_id)

    def runner_token(authorization: str | None) -> str:
        try:
            return bearer_token(authorization)
        except RunnerAuthenticationError as exc:
            raise HTTPException(
                status_code=401,
                detail=str(exc),
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc

    @application.post(
        "/api/runner-sessions/heartbeat",
        response_model=RunnerSessionStatus,
    )
    async def runner_heartbeat(
        authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    ) -> RunnerSessionStatus:
        try:
            return await active_manager.remote_runners.heartbeat(runner_token(authorization))
        except RunnerAuthenticationError as exc:
            raise HTTPException(
                status_code=401,
                detail=str(exc),
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc

    @application.get(
        "/api/runner-sessions/turns/next",
        response_model=RunnerTurnDelivery,
        responses={204: {"description": "No turn is currently pending."}},
    )
    async def next_runner_turn(
        wait_ms: Annotated[int, Query(ge=0, le=25_000)] = 0,
        authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    ) -> RunnerTurnDelivery | Response:
        try:
            delivery = await active_manager.remote_runners.next_turn(
                runner_token(authorization),
                wait_ms=wait_ms,
            )
        except RunnerAuthenticationError as exc:
            raise HTTPException(
                status_code=401,
                detail=str(exc),
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc
        return delivery if delivery is not None else Response(status_code=204)

    @application.post(
        "/api/runner-sessions/turns/{delivery_id}/proposal",
        response_model=RunnerProposalReceipt,
    )
    async def submit_runner_proposal(
        delivery_id: str,
        request: RunnerProposalSubmission,
        authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    ) -> RunnerProposalReceipt:
        try:
            return await active_manager.remote_runners.submit_proposal(
                runner_token(authorization),
                delivery_id,
                request,
            )
        except RunnerAuthenticationError as exc:
            raise HTTPException(
                status_code=401,
                detail=str(exc),
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc
        except RunnerSubmissionError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @application.post("/api/games", response_model=GameSnapshot, status_code=201)
    async def create_game(request: CreateGameRequest) -> GameSnapshot:
        try:
            game = await active_manager.create(request)
        except AdapterConfigurationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return await active_manager.snapshot(game.id)

    @application.get("/api/games/{game_id}", response_model=GameSnapshot)
    async def get_game(game_id: str) -> GameSnapshot:
        try:
            return await active_manager.snapshot(game_id)
        except GameNotFound as exc:
            raise HTTPException(status_code=404, detail="Game not found.") from exc

    @application.get("/api/games/{game_id}/events", response_model=list[MatchEvent])
    async def get_events(game_id: str) -> list[MatchEvent]:
        try:
            return await active_manager.events(game_id)
        except GameNotFound as exc:
            raise HTTPException(status_code=404, detail="Game not found.") from exc

    @application.get("/api/games/{game_id}/analysis", response_model=GameAnalysis)
    async def get_analysis(game_id: str) -> GameAnalysis:
        try:
            return await active_manager.analysis(game_id)
        except GameNotFound as exc:
            raise HTTPException(status_code=404, detail="Game not found.") from exc
        except EngineFailure as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except AnalysisSuperseded as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @application.post("/api/games/{game_id}/moves", response_model=GameSnapshot)
    async def make_move(
        game_id: str,
        request: MoveRequest,
        idempotency_key: Annotated[
            str | None,
            Header(
                alias="Idempotency-Key",
                min_length=8,
                max_length=128,
                pattern=r"^[A-Za-z0-9._:-]+$",
            ),
        ] = None,
    ) -> GameSnapshot:
        try:
            return await active_manager.make_human_move(
                game_id,
                request.move,
                request.position_version,
                idempotency_key,
                consultation_id=request.consultation_id,
                consultation_revision=request.consultation_revision,
            )
        except GameNotFound as exc:
            raise HTTPException(status_code=404, detail="Game not found.") from exc
        except (ClockExpired, StalePosition, ConcurrentGameUpdate) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except IdempotencyConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except MoveRejected as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @application.post("/api/games/{game_id}/reset", response_model=GameSnapshot)
    async def reset_game(game_id: str) -> GameSnapshot:
        try:
            return await active_manager.reset(game_id)
        except GameNotFound as exc:
            raise HTTPException(status_code=404, detail="Game not found.") from exc
        except ConcurrentGameUpdate as exc:
            raise HTTPException(status_code=409, detail="Concurrent match update.") from exc

    @application.post("/api/games/{game_id}/resign", response_model=GameSnapshot)
    async def resign_game(game_id: str, request: ResignRequest | None = None) -> GameSnapshot:
        try:
            request = request or ResignRequest()
            return await active_manager.resign(game_id, request.color, request.position_version)
        except GameNotFound as exc:
            raise HTTPException(status_code=404, detail="Game not found.") from exc
        except (ClockExpired, StalePosition) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except MoveRejected as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except ConcurrentGameUpdate as exc:
            raise HTTPException(status_code=409, detail="Concurrent match update.") from exc

    @application.post("/api/games/{game_id}/claim-draw", response_model=GameSnapshot)
    async def claim_draw(game_id: str, request: DrawClaimRequest) -> GameSnapshot:
        try:
            return await active_manager.claim_draw(
                game_id, request.position_version, request.intended_move
            )
        except GameNotFound as exc:
            raise HTTPException(status_code=404, detail="Game not found.") from exc
        except (ClockExpired, StalePosition, ConcurrentGameUpdate) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except MoveRejected as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    async def lifecycle_action(action, game_id: str, **kwargs) -> GameSnapshot:
        try:
            return await action(game_id, **kwargs)
        except GameNotFound as exc:
            raise HTTPException(status_code=404, detail="Game not found.") from exc
        except MatchTransitionRejected as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ConcurrentGameUpdate as exc:
            raise HTTPException(status_code=409, detail="Concurrent match update.") from exc

    @application.post("/api/games/{game_id}/pause", response_model=GameSnapshot)
    async def pause_game(game_id: str, request: LifecycleRequest | None = None) -> GameSnapshot:
        return await lifecycle_action(
            active_manager.pause,
            game_id,
            expected_revision=request.expected_revision if request else None,
        )

    @application.post("/api/games/{game_id}/resume", response_model=GameSnapshot)
    async def resume_game(game_id: str, request: LifecycleRequest | None = None) -> GameSnapshot:
        return await lifecycle_action(
            active_manager.resume,
            game_id,
            expected_revision=request.expected_revision if request else None,
        )

    @application.post(
        "/api/games/{game_id}/consultations", response_model=GameSnapshot, status_code=202
    )
    async def request_consultation(game_id: str, request: ConsultationRequest):
        try:
            return await active_manager.consultation.request(game_id, request)
        except GameNotFound as exc:
            raise HTTPException(status_code=404, detail="Game not found.") from exc
        except (MatchTransitionRejected, StalePosition, ConcurrentGameUpdate) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except AdapterConfigurationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @application.post(
        "/api/games/{game_id}/consultations/{advice_id}/cancel", response_model=GameSnapshot
    )
    async def cancel_consultation(game_id: str, advice_id: str, request: LifecycleRequest):
        try:
            return await active_manager.consultation.cancel(
                game_id, advice_id, request.expected_revision
            )
        except GameNotFound as exc:
            raise HTTPException(status_code=404, detail="Game not found.") from exc
        except (MatchTransitionRejected, StalePosition, ConcurrentGameUpdate) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @application.post("/api/games/{game_id}/seats/{color}", response_model=GameSnapshot)
    async def change_seat(game_id: str, color: str, request: SeatTakeoverRequest) -> GameSnapshot:
        if color not in {"white", "black"}:
            raise HTTPException(status_code=422, detail="Color must be white or black.")
        try:
            return await active_manager.change_seat(
                game_id, color, request.player, request.expected_revision
            )
        except GameNotFound as exc:
            raise HTTPException(status_code=404, detail="Game not found.") from exc
        except (MatchTransitionRejected, ConcurrentGameUpdate) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except AdapterConfigurationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @application.post("/api/games/{game_id}/retry-agent", response_model=GameSnapshot)
    async def retry_agent_turn(game_id: str) -> GameSnapshot:
        return await lifecycle_action(active_manager.retry_agent_turn, game_id)

    @application.post("/api/games/{game_id}/abort", response_model=GameSnapshot)
    async def abort_game(game_id: str) -> GameSnapshot:
        return await lifecycle_action(active_manager.abort, game_id)

    @application.post("/api/games/{game_id}/adjudicate", response_model=GameSnapshot)
    async def adjudicate_game(game_id: str, request: AdjudicateRequest) -> GameSnapshot:
        try:
            return await active_manager.adjudicate(game_id, request.result)
        except GameNotFound as exc:
            raise HTTPException(status_code=404, detail="Game not found.") from exc
        except MatchTransitionRejected as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ConcurrentGameUpdate as exc:
            raise HTTPException(status_code=409, detail="Concurrent match update.") from exc

    @application.websocket("/ws/games/{game_id}")
    async def game_socket(websocket: WebSocket, game_id: str) -> None:
        try:
            snapshot = await active_manager.subscribe(game_id, websocket)
        except GameNotFound:
            await websocket.close(code=4404, reason="Game not found")
            return
        marker = (snapshot.generation, snapshot.revision)
        try:
            while True:
                try:
                    await asyncio.wait_for(websocket.receive_text(), timeout=0.25)
                except TimeoutError:
                    next_marker = await active_manager.revision(game_id)
                    if next_marker > marker:
                        snapshot = await active_manager.snapshot(game_id)
                        await websocket.send_json(
                            {
                                "type": "snapshot",
                                "payload": snapshot.model_dump(mode="json"),
                            }
                        )
                        marker = next_marker
        except WebSocketDisconnect:
            active_manager.unsubscribe(game_id, websocket)

    @application.websocket("/ws/runners")
    async def runner_socket(websocket: WebSocket) -> None:
        try:
            token = bearer_token(websocket.headers.get("authorization"))
            await active_manager.remote_runners.socket_loop(websocket, token)
        except RunnerAuthenticationError:
            await websocket.close(code=4401, reason="Runner authentication failed")

    if web_dist.is_dir():
        assets = web_dist / "assets"
        if assets.is_dir():
            application.mount("/assets", StaticFiles(directory=assets), name="assets")

        @application.get("/{path:path}", include_in_schema=False)
        async def spa(path: str) -> FileResponse:
            candidate = web_dist / path
            if path and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(web_dist / "index.html")

    return application


manager = GameManager()
app = create_app(manager)
