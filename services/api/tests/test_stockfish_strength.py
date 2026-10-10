import asyncio
from types import SimpleNamespace

import chess
import chess.engine
import pytest
from fastapi.testclient import TestClient
from lounge_api.engine import StockfishService
from lounge_api.main import create_app
from lounge_api.manager import GameManager
from lounge_api.models import CreateGameRequest
from lounge_api.persistence import DatabaseStore
from lounge_api.player_protocol import PlayerConfiguration
from pydantic import ValidationError


class RecordingUCI:
    options = {
        "UCI_LimitStrength": chess.engine.Option(
            "UCI_LimitStrength", "check", False, None, None, None
        ),
        "UCI_Elo": chess.engine.Option("UCI_Elo", "spin", 1320, 1320, 3190, None),
        "Skill Level": chess.engine.Option("Skill Level", "spin", 20, 0, 20, None),
    }

    def __init__(self):
        self.configurations = []

    def configure(self, settings):
        self.configurations.append(settings)

    def play(self, board, limit):
        return SimpleNamespace(move=next(iter(board.legal_moves)))

    def quit(self):
        pass

    def close(self):
        pass


def recording_engine():
    engine = StockfishService()
    engine.path = "recording-fixture"
    engine._engine = RecordingUCI()
    engine._version = "Recording Stockfish options"
    return engine


@pytest.mark.parametrize("elo", [1320, 1600, 3100, 3190])
def test_exact_elo_reaches_uci_including_maximum(elo):
    engine = recording_engine()
    move = engine._play_sync(chess.Board(), elo, 50)
    assert move in chess.Board().legal_moves
    assert engine._engine.configurations == [
        {"Skill Level": 20, "UCI_LimitStrength": True, "UCI_Elo": elo}
    ]


def test_full_strength_and_return_to_rated_reset_all_limits():
    engine = recording_engine()
    engine._play_sync(chess.Board(), 1320, 50)
    engine._play_sync(chess.Board(), 1600, 50, full_strength=True)
    engine._play_sync(chess.Board(), 3190, 50)
    assert engine._engine.configurations[1] == {"Skill Level": 20, "UCI_LimitStrength": False}
    assert engine._engine.configurations[2]["UCI_LimitStrength"] is True
    assert engine._engine.configurations[2]["UCI_Elo"] == 3190


def test_unavailable_engine_does_not_invent_a_supported_range():
    engine = StockfishService()
    engine.path = None
    caps = asyncio.run(engine.strength_capabilities())
    assert caps["available"] is False
    assert caps["elo_min"] is None and caps["elo_max"] is None
    assert caps["full_strength_available"] is False


@pytest.mark.parametrize("elo", [1319, 3191])
def test_engine_rejects_instead_of_silently_clamping(elo):
    engine = recording_engine()
    with pytest.raises(ValueError, match="1320 and 3190"):
        engine._play_sync(chess.Board(), elo, 50)
    assert engine._engine.configurations == []


@pytest.mark.parametrize("value", ["true", 1, None])
def test_full_strength_is_a_strict_boolean(value):
    with pytest.raises(ValidationError):
        CreateGameRequest(stockfish_full_strength=value)
    settings = PlayerConfiguration.stockfish("black").model_dump()
    settings["settings"]["full_strength"] = value
    with pytest.raises(ValidationError):
        PlayerConfiguration.model_validate(settings)


def test_capabilities_backend_validation_and_active_seat_fence(tmp_path):
    manager = GameManager(
        engine=recording_engine(),
        store=DatabaseStore(f"sqlite+aiosqlite:///{tmp_path / 'strength.db'}"),
        schedule_agents=False,
        schedule_timeouts=False,
    )
    with TestClient(create_app(manager)) as client:
        caps = client.get("/api/engine/strength").json()
        assert (caps["elo_min"], caps["elo_max"], caps["full_strength_available"]) == (
            1320,
            3190,
            True,
        )
        assert "path" not in caps
        for elo in (1319, 3191):
            assert client.post("/api/games", json={"stockfish_elo": elo}).status_code == 422
        for elo in (1320, 3100, 3190):
            created = client.post("/api/games", json={"stockfish_elo": elo})
            assert created.status_code == 201
            assert created.json()["black_player"]["settings"]["target_elo"] == elo
            # Retire each strength fixture before exercising the shared-table reset.
            assert client.post(f"/api/games/{created.json()['id']}/abort").status_code == 200
        full = client.post("/api/games", json={"stockfish_full_strength": True}).json()
        assert full["black_player"]["settings"]["full_strength"] is True
        assert full["engine"]["full_strength"] is True
        player = PlayerConfiguration.stockfish("black", target_elo=3100).model_dump(mode="json")
        route = f"/api/games/{full['id']}"
        reset = client.post(f"{route}/reset")
        assert reset.status_code == 200
        full = reset.json()
        assert full["engine"]["full_strength"] is True
        assert full["black_player"]["settings"]["full_strength"] is True
        change = {"player": player, "expected_revision": full["revision"]}
        assert client.post(f"{route}/seats/black", json=change).status_code == 409
        paused = client.post(f"{route}/pause", json={"expected_revision": full["revision"]}).json()
        invalid = PlayerConfiguration.stockfish("black", target_elo=1319).model_dump(mode="json")
        assert (
            client.post(
                f"{route}/seats/black",
                json={"player": invalid, "expected_revision": paused["revision"]},
            ).status_code
            == 422
        )
        changed = client.post(
            f"{route}/seats/black", json={**change, "expected_revision": paused["revision"]}
        )
        assert changed.status_code == 200
        assert changed.json()["black_player"]["settings"]["target_elo"] == 3100
        assert changed.json()["fen"] == full["fen"]
        assert changed.json()["moves"] == full["moves"]


def test_strength_survives_database_reload_and_reaches_adapter(tmp_path):
    async def run():
        engine = recording_engine()
        uci = engine._engine
        manager = GameManager(
            engine=engine,
            store=DatabaseStore(f"sqlite+aiosqlite:///{tmp_path / 'saved.db'}"),
            schedule_agents=True,
            schedule_timeouts=False,
        )
        await manager.start()
        try:
            for elo, full in [(1320, False), (3190, False), (1600, True)]:
                game = await manager.create(
                    CreateGameRequest(stockfish_elo=elo, stockfish_full_strength=full)
                )
                restored = await manager.store.load_game(game.id)
                assert restored.black_player.settings.get("full_strength", False) == full
                assert restored.black_player.settings["target_elo"] == elo
                assert restored.engine_summary.full_strength == full
                manager.games.pop(game.id)  # Exercise the persisted configuration on the next turn.
                snapshot = await manager.make_human_move(game.id, "e2e4", 0)
                assert len(snapshot.moves) == 2
                assert uci.configurations[-1]["UCI_LimitStrength"] is (not full)
                if not full:
                    assert uci.configurations[-1]["UCI_Elo"] == elo
        finally:
            await manager.close()

    asyncio.run(run())
