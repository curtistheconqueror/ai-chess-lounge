import asyncio

import chess
import pytest
from lounge_api.engine import StockfishService
from lounge_api.manager import GameManager
from lounge_api.models import CreateGameRequest
from lounge_api.persistence import DatabaseStore
from lounge_api.player_protocol import PlayerConfiguration
from pydantic import ValidationError
from test_stockfish_strength import recording_engine


@pytest.mark.parametrize("level", [0, 1, 10, 20])
def test_skill_mode_and_switches_reset_conflicting_uci_options(level):
    engine = recording_engine()
    board = chess.Board()
    engine._play_sync(board, 3190, 50)
    engine._play_sync(board, 1600, 50, skill_level=level)
    assert engine._engine.configurations[-1] == {"Skill Level": level, "UCI_LimitStrength": False}
    engine._play_sync(board, 1600, 50, full_strength=True)
    assert engine._engine.configurations[-1] == {"Skill Level": 20, "UCI_LimitStrength": False}
    engine._play_sync(board, 1320, 50)
    assert engine._engine.configurations[-1] == {
        "Skill Level": 20,
        "UCI_LimitStrength": True,
        "UCI_Elo": 1320,
    }


@pytest.mark.parametrize("level", [-1, 21, 1.5, True, "3"])
def test_skill_rejects_invalid_values_without_engine_configuration(level):
    with pytest.raises(ValidationError):
        CreateGameRequest(stockfish_skill_level=level)
    with pytest.raises(ValidationError):
        PlayerConfiguration.stockfish("black", skill_level=level)
    engine = recording_engine()
    with pytest.raises(ValueError):
        engine._play_sync(chess.Board(), 1600, 50, skill_level=level)
    assert engine._engine.configurations == []


def test_skill_cannot_be_full_strength_or_attached_to_non_engine_seats():
    with pytest.raises(ValidationError):
        CreateGameRequest(stockfish_skill_level=0, stockfish_full_strength=True)
    with pytest.raises(ValidationError):
        PlayerConfiguration.stockfish("black", skill_level=0, full_strength=True)
    human = PlayerConfiguration.human("white").model_dump()
    human["settings"]["skill_level"] = 0
    with pytest.raises(ValidationError):
        PlayerConfiguration.model_validate(human)
    engine = recording_engine()
    engine._engine.options = {k: v for k, v in engine._engine.options.items() if k != "Skill Level"}
    with pytest.raises(ValueError, match="does not advertise"):
        engine._play_sync(chess.Board(), 1600, 50, skill_level=0)


def test_skill_persists_and_resumes_per_seat_with_distinct_comparison_conditions(tmp_path):
    async def run():
        engine = recording_engine()
        uci = engine._engine
        manager = GameManager(
            engine=engine,
            store=DatabaseStore(f"sqlite+aiosqlite:///{tmp_path / 'skill.db'}"),
            schedule_timeouts=False,
        )
        await manager.start()
        try:
            caps = await engine.strength_capabilities()
            assert (caps["skill_min"], caps["skill_max"]) == (0, 20)
            game = await manager.create(
                CreateGameRequest(stockfish_skill_level=0, start_paused=True)
            )
            assert game.black_player.display_name == "Stockfish skill 0"
            assert game.engine_summary.skill_level == 0
            assert game.comparison_snapshot["conditions"]["engines"][0]["skill_level"] == 0
            assert game.comparison_snapshot["conditions"]["engines"][0]["target_elo"] is None
            saved = await manager.store.load_game(game.id)
            assert saved.black_player.settings["skill_level"] == 0
            assert saved.engine_summary.skill_level == 0
            changed = await manager.change_seat(
                game.id,
                "white",
                PlayerConfiguration.stockfish("white", skill_level=20),
                game.revision,
            )
            assert changed.black_player.settings["skill_level"] == 0
            restored = await manager.change_seat(
                game.id, "white", PlayerConfiguration.human("white"), changed.revision
            )
            manager.games.pop(game.id)
            await manager.resume(game.id, restored.revision)
            played = await manager.make_human_move(game.id, "e2e4", restored.version)
            assert len(played.moves) == 2
            assert uci.configurations[-1] == {"Skill Level": 0, "UCI_LimitStrength": False}
            paused = await manager.pause(game.id, played.revision)
            elo = await manager.change_seat(
                game.id,
                "black",
                PlayerConfiguration.stockfish("black", target_elo=1400),
                paused.revision,
            )
            assert "skill_level" not in elo.black_player.settings
            assert elo.engine.skill_level is None
            reset = await manager.reset(game.id)
            assert reset.black_player.settings["target_elo"] == 1400
            assert reset.engine.skill_level is None
        finally:
            await manager.close()

    asyncio.run(run())


def test_native_engine_reports_and_applies_skill_without_elo_limiter():
    async def run():
        engine = StockfishService()
        if not engine.available:
            pytest.skip("No native Stockfish installed")
        try:
            caps = await engine.strength_capabilities()
            if caps["skill_min"] is None:
                pytest.skip("Native engine does not advertise Skill Level")
            for elo, full, skill in [
                (3190, False, None),
                (1600, False, 0),
                (1600, False, 20),
                (1600, True, None),
                (1320, False, None),
            ]:
                if skill is None and not full:
                    elo = max(caps["elo_min"], min(elo, caps["elo_max"]))
                result = await engine.choose_move(
                    chess.Board(),
                    target_elo=elo,
                    move_time_ms=50,
                    full_strength=full,
                    skill_level=skill,
                )
                assert chess.Move.from_uci(result.uci) in chess.Board().legal_moves
                configured = engine._engine.protocol.config
                assert configured["UCI_LimitStrength"] is (skill is None and not full)
                assert configured["Skill Level"] == (
                    skill if skill is not None else caps["skill_max"]
                )
                if skill is None and not full:
                    assert configured["UCI_Elo"] == elo
        finally:
            await engine.close()

    asyncio.run(run())
