from __future__ import annotations

from fastapi.testclient import TestClient


def test_health_and_human_game_flow(client: TestClient) -> None:
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["ok"] is True

    created = client.post(
        "/api/games",
        json={
            "opponent": "human",
            "stockfish_elo": 1600,
            "engine_move_time_ms": 100,
            "initial_time_ms": 60_000,
            "increment_ms": 1_000,
        },
    )
    assert created.status_code == 201
    game = created.json()
    assert game["lifecycle"] == "running"
    assert game["clock"]["initial_time_ms"] == 60_000
    assert game["clock"]["increment_ms"] == 1_000
    assert game["clock"]["deadline_at"] is not None

    moved = client.post(
        f"/api/games/{game['id']}/moves",
        json={"move": "e2e4", "position_version": game["version"]},
    )
    assert moved.status_code == 200
    assert moved.json()["moves"][0]["san"] == "e4"
    assert moved.json()["moves"][0]["white_remaining_ms"] > 59_000
    assert moved.json()["clock"]["deadline_at"] is not None

    events = client.get(f"/api/games/{game['id']}/events")
    assert [event["type"] for event in events.json()] == [
        "match.created",
        "match.started",
        "move.accepted",
    ]


def test_websocket_sends_reconnect_snapshot(client: TestClient) -> None:
    created = client.post("/api/games", json={"opponent": "human"}).json()
    with client.websocket_connect(f"/ws/games/{created['id']}") as websocket:
        message = websocket.receive_json()
        assert message["type"] == "snapshot"
        assert message["payload"]["id"] == created["id"]


def test_pause_resume_and_abort_endpoints(client: TestClient) -> None:
    game = client.post("/api/games", json={"opponent": "human"}).json()

    paused = client.post(f"/api/games/{game['id']}/pause")
    assert paused.status_code == 200
    assert paused.json()["lifecycle"] == "paused"
    assert paused.json()["can_move"] is False
    assert paused.json()["clock"]["deadline_at"] is None

    resumed = client.post(f"/api/games/{game['id']}/resume")
    assert resumed.status_code == 200
    assert resumed.json()["lifecycle"] == "running"
    assert resumed.json()["clock"]["deadline_at"] is not None

    aborted = client.post(f"/api/games/{game['id']}/abort")
    assert aborted.status_code == 200
    assert aborted.json()["status"] == "aborted"

    invalid = client.post(f"/api/games/{game['id']}/resume")
    assert invalid.status_code == 409


def test_invalid_time_control_is_rejected(client: TestClient) -> None:
    too_short = client.post(
        "/api/games",
        json={"opponent": "human", "initial_time_ms": 99, "increment_ms": 0},
    )
    excessive_increment = client.post(
        "/api/games",
        json={"opponent": "human", "initial_time_ms": 60_000, "increment_ms": 60_001},
    )

    assert too_short.status_code == 422
    assert excessive_increment.status_code == 422
