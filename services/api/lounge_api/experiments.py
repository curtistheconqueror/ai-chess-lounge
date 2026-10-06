"""Immutable, bounded experiment plans. Building a plan never dispatches a player."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from itertools import combinations, product
from typing import Literal
from uuid import UUID

import chess
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from .adapters import AdapterRegistry
from .persistence import DatabaseStore, ExperimentRow
from .player_protocol import EffortLevel, PlayerConfiguration


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ExperimentEntrant(StrictModel):
    key: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,40}$")
    player: PlayerConfiguration
    efforts: list[EffortLevel | None] = Field(default_factory=list, max_length=4)


class ExperimentOpening(StrictModel):
    name: str = Field(min_length=1, max_length=80)
    moves: list[str] = Field(default_factory=list, max_length=80)

    @model_validator(mode="after")
    def legal_line(self):
        board = chess.Board()
        for move in self.moves:
            try:
                parsed = chess.Move.from_uci(move)
                if parsed not in board.legal_moves:
                    raise ValueError("Illegal opening move.")
                board.push(parsed)
            except ValueError as exc:
                raise ValueError(
                    "Opening must contain a legal UCI sequence from start position."
                ) from exc
            if board.is_game_over(claim_draw=True):
                raise ValueError("Opening cannot reach a terminal or claimable-draw position.")
        return self


class ExperimentStops(StrictModel):
    max_plies: int = Field(default=300, ge=2, le=1000)
    max_failures: int = Field(default=3, ge=1, le=100)
    max_wall_time_ms: int = Field(default=3_600_000, ge=1000, le=86_400_000)


class ExperimentConfiguration(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    name: str = Field(min_length=1, max_length=120)
    entrants: list[ExperimentEntrant] = Field(min_length=2, max_length=8)
    openings: list[ExperimentOpening] = Field(
        default_factory=lambda: [ExperimentOpening(name="Starting position")],
        min_length=1,
        max_length=16,
    )
    repetitions: int = Field(default=1, ge=1, le=20)
    color_swap: bool = True
    initial_time_ms: int = Field(default=300_000, ge=100, le=86_400_000)
    increment_ms: int = Field(default=2000, ge=0, le=60_000)
    stops: ExperimentStops = Field(default_factory=ExperimentStops)
    clock_information: Literal["supplied"] = "supplied"
    effort_control: Literal["fixed"] = "fixed"
    prompt_version: Literal["player-protocol-v1"] = "player-protocol-v1"

    @model_validator(mode="after")
    def unique_keys(self):
        if len({e.key for e in self.entrants}) != len(self.entrants):
            raise ValueError("Entrant keys must be unique.")
        if len({o.name for o in self.openings}) != len(self.openings):
            raise ValueError("Opening names must be unique.")
        return self


class TournamentConfiguration(ExperimentConfiguration):
    schema_version: Literal["2.0"] = "2.0"
    format: Literal["round_robin", "gauntlet", "knockout"] = "round_robin"
    anchor: str | None = Field(default=None, max_length=60)

    @model_validator(mode="after")
    def anchor_only_for_gauntlet(self):
        if self.format != "gauntlet" and self.anchor is not None:
            raise ValueError("An anchor applies only to gauntlet tournaments.")
        return self


PlanConfiguration = ExperimentConfiguration | TournamentConfiguration
_plan_adapter = TypeAdapter(PlanConfiguration)


def parse_configuration(value: dict) -> PlanConfiguration:
    return _plan_adapter.validate_python(value)


class SaveExperiment(StrictModel):
    id: UUID
    configuration: PlanConfiguration


def canonical_hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


class ExperimentService:
    def __init__(self, store: DatabaseStore, adapters: AdapterRegistry):
        self.store, self.adapters = store, adapters

    def preview(self, config: PlanConfiguration) -> dict:
        normalized = config.model_dump(mode="json")
        variants = []
        for index, entrant in enumerate(config.entrants):
            player = entrant.player
            if player.adapter_id in {"human", "remote_runner"}:
                raise ValueError(
                    "Batch plans require direct/local automated entrants; "
                    "one-match runner grants cannot authorize a batch."
                )
            adapter = self.adapters.get(player.adapter_id)
            if player.model not in adapter.list_models():
                raise ValueError("Entrant model is not in the configured adapter catalog.")
            cap = adapter.capabilities(player.model)
            expected_mode = cap.get("connection_mode")
            if expected_mode and player.connection_mode != expected_mode:
                raise ValueError("Entrant connection mode does not match its adapter.")
            if "color" in player.settings:
                raise ValueError(
                    "Experiment entrants must be color-neutral; remove settings.color."
                )
            if player.adapter_id == "stockfish" and player.division != "engine_assisted":
                raise ValueError("Stockfish entrants must disclose engine assistance.")
            efforts = entrant.efforts or [player.effort]
            if len(set(efforts)) != len(efforts):
                raise ValueError("Effort sweep entries must be unique.")
            # Stockfish exposes legacy effort labels, but actually uses explicit UCI limits.
            if player.adapter_id == "stockfish" and len(efforts) > 1:
                raise ValueError(
                    "Stockfish strength uses explicit engine settings, not an effort sweep."
                )
            normalized["entrants"][index]["efforts"] = efforts
            normalized["entrants"][index]["player"]["player_id"] = entrant.key
            normalized["entrants"][index]["player"]["effort"] = efforts[0]
            for effort in efforts:
                if effort is not None and effort not in cap.get("effort_levels", []):
                    raise ValueError("The selected model does not support this effort level.")
                candidate = PlayerConfiguration.model_validate(
                    {**player.model_dump(), "player_id": entrant.key, "effort": effort}
                )
                adapter.validate_configuration(candidate)
                public = candidate.model_dump(mode="json")
                variants.append(
                    {
                        "key": f"{entrant.key}:{effort or 'default'}",
                        "entrant": entrant.key,
                        "player": public,
                        "profile_hash": canonical_hash(public),
                        "provider_effort": cap.get("provider_effort_map", {}).get(effort)
                        if isinstance(cap.get("provider_effort_map"), dict)
                        else None,
                    }
                )
        is_tournament = isinstance(config, TournamentConfiguration)
        # Count before allocating the schedule; expansion is bounded on every route.
        pairs = [(a, b) for a, b in combinations(variants, 2) if a["entrant"] != b["entrant"]]
        count = (
            len(pairs) * len(config.openings) * config.repetitions * (2 if config.color_swap else 1)
        )
        if count > 512 and not is_tournament:
            raise ValueError(
                "Experiment exceeds the 512-game plan limit. "
                "Reduce entrants, efforts, openings or repetitions."
            )
        schedule = []
        for (a, b), (opening_index, opening), repetition in product(
            [] if is_tournament else pairs, enumerate(config.openings), range(config.repetitions)
        ):
            board = chess.Board()
            for move in opening.moves:
                board.push_uci(move)
            for white, black in [(a, b), (b, a)] if config.color_swap else [(a, b)]:
                schedule.append(
                    {
                        "number": len(schedule) + 1,
                        "white": white["key"],
                        "black": black["key"],
                        "opening_index": opening_index,
                        "opening": opening.name,
                        "initial_fen": board.fen(),
                        "repetition": repetition + 1,
                    }
                )
        tournament = None
        if is_tournament:
            from .tournaments import build_tournament

            schedule, tournament = build_tournament(normalized, variants)
            count = len(schedule)
        mixed = len({v["player"]["division"] for v in variants}) > 1
        manifest = {
            "configuration": normalized,
            "variants": variants,
            "schedule": schedule,
            "game_count": count,
            "exhibition": mixed,
            "status": "draft",
        }
        if tournament is not None:
            manifest["tournament"] = tournament
        manifest["configuration_hash"] = canonical_hash(manifest)
        manifest["warnings"] = (
            ["Mixed divisions: exhibition only; results cannot share one rating pool."]
            if mixed
            else []
        ) + [
            "Plan only: no games have started. "
            "Stop rules are enforced by the scheduler when execution is available.",
            "Clock-withheld and adaptive-effort conditions are not supported yet.",
        ]
        return manifest

    async def save(self, request: SaveExperiment) -> dict:
        # Retry with the same ID/body returns the original snapshot, even if catalog changed.
        await self.store.initialize()
        request_hash = canonical_hash(request.configuration.model_dump(mode="json"))
        existing = await self.get(str(request.id))
        if existing is not None:
            if existing["request_hash"] != request_hash:
                raise FileExistsError("Experiment ID is already used by a different configuration.")
            return existing["document"]
        document = {
            **self.preview(request.configuration),
            "id": str(request.id),
            "created_at": datetime.now(UTC).isoformat(),
        }
        try:
            async with self.store.sessions.begin() as session:
                session.add(
                    ExperimentRow(id=str(request.id), request_hash=request_hash, document=document)
                )
        except IntegrityError:
            existing = await self.get(str(request.id))
            if existing is None or existing["request_hash"] != request_hash:
                raise FileExistsError(
                    "Experiment ID is already used by a different configuration."
                ) from None
            return existing["document"]
        return document

    async def get(self, experiment_id: str) -> dict | None:
        await self.store.initialize()
        async with self.store.sessions() as session:
            row = await session.get(ExperimentRow, experiment_id)
            return {"request_hash": row.request_hash, "document": row.document} if row else None

    async def list(self, offset: int = 0) -> list[dict]:
        await self.store.initialize()
        async with self.store.sessions() as session:
            rows = (
                await session.scalars(
                    select(ExperimentRow).order_by(ExperimentRow.id).offset(offset).limit(50)
                )
            ).all()
            return [
                {
                    "id": r.id,
                    "name": r.document["configuration"]["name"],
                    "configuration_hash": r.document["configuration_hash"],
                    "game_count": r.document["game_count"],
                    "created_at": r.document["created_at"],
                }
                for r in rows
            ]
