import asyncio
from datetime import UTC, datetime, timedelta

import chess
import pytest
from fastapi.testclient import TestClient
from lounge_api.domain import ClockExpired, GameSession, MoveRejected
from lounge_api.models import GameStatus, MatchState, OpponentKind
from lounge_api.persistence import DatabaseStore


def human_game(board: chess.Board | None = None) -> GameSession:
    game = GameSession(opponent=OpponentKind.HUMAN, initial_time_ms=60_000, increment_ms=0)
    if board is not None:
        game.board = board
    game.start(now=datetime(2026, 1, 1, tzinfo=UTC))
    return game


def test_resign_settles_clock_without_increment() -> None:
    game = human_game()
    game.resign("black", now=datetime(2026, 1, 1, 0, 0, 5, tzinfo=UTC))
    assert game.result == "1-0"
    assert game.white_remaining_ms == 55_000
    assert game.black_remaining_ms == 60_000
    assert game.turn_started_at is None


def test_claim_by_intended_move_is_announced_without_playing_it() -> None:
    game = human_game()
    now = datetime(2026, 1, 1, tzinfo=UTC)
    for uci in ["g1f3", "g8f6", "f3g1", "f6g8", "g1f3", "g8f6", "f3g1"]:
        game.apply_uci(uci, actor="human", now=now)
    assert game.draw_claim_options() == (False, ["f6g8"])
    fen, version, ply = game.board.fen(), game.version, len(game.moves)
    with pytest.raises(MoveRejected):
        game.claim_draw(None, now=now)
    with pytest.raises(MoveRejected):
        game.claim_draw("a7a6", now=now)
    game.claim_draw("f6g8", now=now + timedelta(seconds=3))
    assert game.draw_reason == "threefold_repetition"
    assert game.board.fen() == fen
    assert len(game.moves) == ply
    assert game.version == version + 1
    assert game.status is GameStatus.DRAW
    assert game.lifecycle is MatchState.COMPLETED
    assert game.black_remaining_ms == 57_000
    assert '[Result "1/2-1/2"]' in game.pgn()
    game.reset(now=now + timedelta(seconds=4))
    assert game.draw_reason is None
    assert game.result == "*"


def test_fifty_move_claim_and_deadline_precedence() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    game = human_game(chess.Board("8/8/8/8/8/1k6/8/R6K w - - 100 80"))
    assert game.draw_claim_options() == (True, [])
    game.claim_draw(None, now=now + timedelta(seconds=1))
    assert game.draw_reason == "fifty_move_rule"
    late = human_game(chess.Board("8/8/8/8/8/1k6/8/R6K w - - 100 80"))
    with pytest.raises(ClockExpired):
        late.claim_draw(None, now=now + timedelta(seconds=60))
    assert late.status is GameStatus.TIMEOUT
    assert late.draw_reason is None


def test_claim_survives_store_reload(tmp_path) -> None:
    asyncio.run(_claim_survives_store_reload(tmp_path))


async def _claim_survives_store_reload(tmp_path) -> None:
    game = human_game(chess.Board("8/8/8/8/8/1k6/8/R6K w - - 100 80"))
    game.initial_fen = game.board.fen()
    game.claim_draw(None, now=datetime(2026, 1, 1, tzinfo=UTC))
    store = DatabaseStore(f"sqlite+aiosqlite:///{tmp_path / 'draw.db'}")
    await store.initialize()
    try:
        await store.create_game(game, [])
        restored = await store.load_game(game.id)
        assert restored is not None
        assert restored.draw_reason == "fifty_move_rule"
        assert restored.status is GameStatus.DRAW
        assert restored.result == "1/2-1/2"
    finally:
        await store.close()


def test_black_resignation_and_stale_request(client: TestClient) -> None:
    game = client.post("/api/games", json={"opponent": "human"}).json()
    url = f"/api/games/{game['id']}"
    moved = client.post(
        url + "/moves", json={"move": "e2e4", "position_version": game["version"]}
    ).json()
    stale = client.post(
        url + "/resign", json={"color": "black", "position_version": game["version"]}
    )
    assert stale.status_code == 409
    assert client.get(url).json()["status"] == "active"
    result = client.post(
        url + "/resign", json={"color": "black", "position_version": moved["version"]}
    )
    assert result.status_code == 200
    assert result.json()["result"] == "1-0"
    assert client.get(url).json()["status"] == "resigned"


def test_automated_seat_cannot_use_human_resignation(client: TestClient) -> None:
    game = client.post("/api/games", json={"opponent": "stockfish"}).json()
    url = f"/api/games/{game['id']}"
    assert client.post(url + "/resign", json={"color": "black"}).status_code == 422
    assert client.get(url).json()["status"] == "active"
    # Legacy requests choose the sole human, not an unconditional White default.
    assert client.post(url + "/resign").json()["result"] == "0-1"


def test_draw_claim_api_records_announced_move_and_rejects_stale(client: TestClient) -> None:
    game = client.post("/api/games", json={"opponent": "human"}).json()
    url = f"/api/games/{game['id']}"
    assert (
        client.post(url + "/claim-draw", json={"position_version": game["version"]}).status_code
        == 422
    )
    for uci in ["g1f3", "g8f6", "f3g1", "f6g8", "g1f3", "g8f6", "f3g1"]:
        game = client.post(
            url + "/moves", json={"move": uci, "position_version": game["version"]}
        ).json()
    assert game["draw_claim_moves"] == ["f6g8"]
    assert (
        client.post(
            url + "/claim-draw", json={"position_version": 0, "intended_move": "f6g8"}
        ).status_code
        == 409
    )
    result = client.post(
        url + "/claim-draw", json={"position_version": game["version"], "intended_move": "f6g8"}
    )
    assert result.status_code == 200
    assert result.json()["status"] == "draw"
    assert result.json()["fen"] == game["fen"]
    events = client.get(url + "/events").json()
    assert events[-2]["type"] == "match.draw_claimed"
    assert events[-2]["payload"]["intended_move"] == "f6g8"
    assert events[-1]["type"] == "match.completed"
