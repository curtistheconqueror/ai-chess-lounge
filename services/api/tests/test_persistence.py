from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from lounge_api.domain import StalePosition
from lounge_api.manager import GameManager
from lounge_api.models import CreateGameRequest, MatchState, OpponentKind
from lounge_api.persistence import DatabaseStore


def database_url(path: Path) -> str:
    return f"sqlite+aiosqlite:///{path}"


def test_match_survives_manager_restart(tmp_path: Path) -> None:
    async def run() -> None:
        url = database_url(tmp_path / "restart.db")
        first = GameManager(store=DatabaseStore(url))
        await first.start()
        game = await first.create(CreateGameRequest(opponent=OpponentKind.HUMAN))
        moved = await first.make_human_move(game.id, "e2e4", 0)
        await first.close()

        second = GameManager(store=DatabaseStore(url))
        await second.start()
        try:
            restored = await second.get(game.id)
            assert restored.snapshot().fen == moved.fen
            assert restored.snapshot().pgn == moved.pgn
            assert restored.snapshot().moves[0].san == "e4"
            assert restored.lifecycle is MatchState.RUNNING
        finally:
            await second.close()

    asyncio.run(run())


def test_reset_keeps_append_only_history(tmp_path: Path) -> None:
    async def run() -> None:
        manager = GameManager(store=DatabaseStore(database_url(tmp_path / "events.db")))
        await manager.start()
        try:
            game = await manager.create(CreateGameRequest(opponent=OpponentKind.HUMAN))
            await manager.make_human_move(game.id, "e2e4", 0)
            reset = await manager.reset(game.id)
            events = await manager.events(game.id)

            assert reset.moves == []
            assert reset.generation == 1
            assert [event.type for event in events] == [
                "match.created",
                "match.started",
                "move.accepted",
                "match.reset",
            ]
        finally:
            await manager.close()

    asyncio.run(run())


def test_database_compare_and_swap_rejects_second_writer(tmp_path: Path) -> None:
    async def run() -> None:
        url = database_url(tmp_path / "concurrency.db")
        first = GameManager(store=DatabaseStore(url))
        await first.start()
        game = await first.create(CreateGameRequest(opponent=OpponentKind.HUMAN))

        second = GameManager(store=DatabaseStore(url))
        await second.start()
        await second.get(game.id)
        try:
            await first.make_human_move(game.id, "e2e4", 0)
            with pytest.raises(StalePosition):
                await second.make_human_move(game.id, "d2d4", 0)
            refreshed = await second.get(game.id)
            assert refreshed.version == 1
            assert refreshed.moves[0].uci == "e2e4"
        finally:
            await first.close()
            await second.close()

    asyncio.run(run())
