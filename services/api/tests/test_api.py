from __future__ import annotations

from fastapi.testclient import TestClient

from lounge_api.main import app, manager


def test_health_and_human_game_flow() -> None:
    with TestClient(app) as client:
        health = client.get("/api/health")
        assert health.status_code == 200
        assert health.json()["ok"] is True

        created = client.post(
            "/api/games",
            json={"opponent": "human", "stockfish_elo": 1600, "engine_move_time_ms": 100},
        )
        assert created.status_code == 201
        game = created.json()

        moved = client.post(
            f"/api/games/{game['id']}/moves",
            json={"move": "e2e4", "position_version": game["version"]},
        )
        assert moved.status_code == 200
        assert moved.json()["moves"][0]["san"] == "e4"


def test_websocket_sends_reconnect_snapshot() -> None:
    with TestClient(app) as client:
        created = client.post("/api/games", json={"opponent": "human"}).json()
        with client.websocket_connect(f"/ws/games/{created['id']}") as websocket:
            message = websocket.receive_json()
            assert message["type"] == "snapshot"
            assert message["payload"]["id"] == created["id"]

    manager.games.clear()
