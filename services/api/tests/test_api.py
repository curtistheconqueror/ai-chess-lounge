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


def test_public_engine_summary_does_not_disclose_server_path(client: TestClient) -> None:
    created = client.post("/api/games", json={"opponent": "stockfish"})

    assert created.status_code == 201
    assert created.json()["engine"] is not None
    assert "path" not in created.json()["engine"]


def test_adapter_catalog_and_human_vs_scripted_game(client: TestClient) -> None:
    catalog = client.get("/api/player-adapters")
    assert catalog.status_code == 200
    assert catalog.json()["protocol_version"] == "1.0"
    assert {item["adapter_id"] for item in catalog.json()["adapters"]} >= {
        "openai",
        "scripted",
        "stockfish",
    }
    openai = next(item for item in catalog.json()["adapters"] if item["adapter_id"] == "openai")
    assert openai["models"]
    first_model = openai["models"][0]
    assert openai["capabilities"][first_model]["connection_mode"] == "direct_api"
    assert openai["capabilities"][first_model]["credentials_required"] is True
    assert openai["capabilities"][first_model]["availability"] in {
        "configured_unverified",
        "credentials_missing",
    }
    assert "key" not in catalog.text.lower()

    scripted_black = {
        "adapter_id": "scripted",
        "display_name": "Deterministic Black",
        "provider": "Lounge Test Harness",
        "model": "deterministic-v1",
        "connection_mode": "local",
        "division": "legal_assist",
        "settings": {"moves": ["e7e5"]},
    }
    created = client.post(
        "/api/games",
        json={"opponent": "human", "black_player": scripted_black},
    )
    assert created.status_code == 201
    game = created.json()
    assert game["white_player"]["adapter_id"] == "human"
    assert game["black_player"]["display_name"] == "Deterministic Black"

    moved = client.post(
        f"/api/games/{game['id']}/moves",
        json={"move": "e2e4", "position_version": game["version"]},
    )
    assert moved.status_code == 200
    snapshot = moved.json()
    assert [move["uci"] for move in snapshot["moves"]] == ["e2e4", "e7e5"]
    assert snapshot["moves"][1]["actor"] == "scripted:black"
    assert snapshot["moves"][1]["player_metadata"]["plan"]


def test_websocket_sends_reconnect_snapshot(client: TestClient) -> None:
    created = client.post("/api/games", json={"opponent": "human"}).json()
    with client.websocket_connect(f"/ws/games/{created['id']}") as websocket:
        message = websocket.receive_json()
        assert message["type"] == "snapshot"
        assert message["payload"]["id"] == created["id"]


def test_websocket_observes_move_committed_by_another_manager(client: TestClient) -> None:
    from lounge_api.main import create_app
    from lounge_api.manager import GameManager
    from lounge_api.persistence import DatabaseStore

    database_url = client.app.state.game_manager.store.url
    second_manager = GameManager(store=DatabaseStore(database_url), schedule_timeouts=False)
    created = client.post("/api/games", json={"opponent": "human"}).json()

    with TestClient(create_app(second_manager)) as second_client:
        with client.websocket_connect(f"/ws/games/{created['id']}") as websocket:
            initial = websocket.receive_json()
            moved = second_client.post(
                f"/api/games/{created['id']}/moves",
                json={"move": "e2e4", "position_version": 0},
                headers={"Idempotency-Key": "cross-process-0001"},
            )
            update = websocket.receive_json()

    assert initial["payload"]["version"] == 0
    assert moved.status_code == 200
    assert update["payload"]["version"] == 1
    assert update["payload"]["moves"][0]["uci"] == "e2e4"


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


def test_move_retry_with_same_idempotency_key_is_replayed(client: TestClient) -> None:
    game = client.post("/api/games", json={"opponent": "human"}).json()
    request = {"move": "e2e4", "position_version": game["version"]}
    headers = {"Idempotency-Key": "move-retry-0001"}

    accepted = client.post(f"/api/games/{game['id']}/moves", json=request, headers=headers)
    replayed = client.post(f"/api/games/{game['id']}/moves", json=request, headers=headers)
    events = client.get(f"/api/games/{game['id']}/events").json()

    assert accepted.status_code == 200
    assert replayed.status_code == 200
    assert replayed.json()["version"] == accepted.json()["version"] == 1
    assert len(replayed.json()["moves"]) == 1
    assert [event["type"] for event in events].count("move.accepted") == 1


def test_idempotency_key_cannot_be_reused_for_another_move(client: TestClient) -> None:
    game = client.post("/api/games", json={"opponent": "human"}).json()
    headers = {"Idempotency-Key": "move-conflict-0001"}
    accepted = client.post(
        f"/api/games/{game['id']}/moves",
        json={"move": "e2e4", "position_version": 0},
        headers=headers,
    )
    conflict = client.post(
        f"/api/games/{game['id']}/moves",
        json={"move": "d2d4", "position_version": 0},
        headers=headers,
    )

    assert accepted.status_code == 200
    assert conflict.status_code == 409
    assert "already used" in conflict.json()["detail"]


def test_invalid_idempotency_key_is_rejected(client: TestClient) -> None:
    game = client.post("/api/games", json={"opponent": "human"}).json()
    response = client.post(
        f"/api/games/{game['id']}/moves",
        json={"move": "e2e4", "position_version": 0},
        headers={"Idempotency-Key": "bad key"},
    )

    assert response.status_code == 422
