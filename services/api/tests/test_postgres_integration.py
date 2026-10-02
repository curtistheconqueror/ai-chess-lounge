from __future__ import annotations

import asyncio
import os

import pytest
from lounge_api.manager import GameManager
from lounge_api.models import CreateGameRequest, OpponentKind
from lounge_api.persistence import DatabaseStore, TurnLeaseUnavailable

POSTGRES_URL = os.getenv("TEST_POSTGRES_URL")

pytestmark = pytest.mark.skipif(
    not POSTGRES_URL,
    reason="TEST_POSTGRES_URL is required for PostgreSQL integration coverage.",
)


def test_postgres_concurrent_retry_and_turn_lease() -> None:
    async def run() -> None:
        assert POSTGRES_URL is not None
        first = GameManager(store=DatabaseStore(POSTGRES_URL), schedule_timeouts=False)
        second = GameManager(store=DatabaseStore(POSTGRES_URL), schedule_timeouts=False)
        await first.start()
        game = await first.create(CreateGameRequest(opponent=OpponentKind.HUMAN))
        await second.start()
        await second.get(game.id)
        try:
            accepted, replayed = await asyncio.gather(
                first.make_human_move(game.id, "e2e4", 0, "postgres-move-0001"),
                second.make_human_move(game.id, "e2e4", 0, "postgres-move-0001"),
            )
            events = await first.events(game.id)

            assert accepted.version == replayed.version == 1
            assert len(accepted.moves) == len(replayed.moves) == 1
            assert [event.type for event in events].count("move.accepted") == 1

            leases = await asyncio.gather(
                first.acquire_turn_lease(game.id, "runner:first", 1),
                second.acquire_turn_lease(game.id, "runner:second", 1),
                return_exceptions=True,
            )
            assert sum(not isinstance(result, Exception) for result in leases) == 1
            assert sum(isinstance(result, TurnLeaseUnavailable) for result in leases) == 1
        finally:
            await first.close()
            await second.close()

    asyncio.run(run())
