from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from lounge_api.main import create_app
from lounge_api.manager import GameManager
from lounge_api.persistence import DatabaseStore


def test_concurrent_new_and_stale_reset_keep_one_table(client):
    old = client.post("/api/games", json={"opponent": "human", "single_game": True}).json()
    ended = client.post(f"/api/games/{old['id']}/abort").json()
    with ThreadPoolExecutor(max_workers=5) as pool:
        attempts = list(
            pool.map(
                lambda _: client.post(
                    "/api/games",
                    json={
                        "opponent": "human",
                        "single_game": True,
                        "start_paused": True,
                    },
                ),
                range(4),
            )
        )
    assert sorted(r.status_code for r in attempts) == [201, 409, 409, 409]
    current = next(r.json() for r in attempts if r.status_code == 201)
    assert client.post(f"/api/games/{old['id']}/reset").status_code == 409
    assert client.get("/api/live-match").json()["id"] == current["id"]
    preserved = client.get(f"/api/games/{old['id']}").json()
    assert (preserved["status"], preserved["generation"], preserved["revision"]) == (
        "aborted",
        ended["generation"],
        ended["revision"],
    )
    client.post(f"/api/games/{current['id']}/abort")
    # Even with an empty table, an old tab cannot revive a finished archive.
    assert client.post(f"/api/games/{old['id']}/reset").status_code == 409
    assert client.post(f"/api/games/{old['id']}/resume").status_code == 409
    assert client.get("/api/live-match").status_code == 404


def test_abort_is_repeatable_but_pinned_to_the_confirmed_generation(client):
    game = client.post("/api/games", json={"opponent": "human"}).json()
    reset = client.post(f"/api/games/{game['id']}/reset").json()
    stale = client.post(
        f"/api/games/{game['id']}/abort", json={"expected_generation": game["generation"]}
    )
    assert stale.status_code == 409
    assert client.get(f"/api/games/{game['id']}").json()["lifecycle"] == "running"
    url = f"/api/games/{game['id']}/abort"
    body = {"expected_generation": reset["generation"]}
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: client.post(url, json=body), range(2)))
    assert [r.status_code for r in responses] == [200, 200]
    assert responses[0].json()["revision"] == responses[1].json()["revision"]
    events = client.get(f"/api/games/{game['id']}/events").json()
    assert sum(e["type"] == "match.aborted" for e in events) == 1


def test_reset_does_not_replace_another_live_match(client):
    first = client.post("/api/games", json={"opponent": "human", "start_paused": True}).json()
    second = client.post("/api/games", json={"opponent": "human", "start_paused": True}).json()
    response = client.post(f"/api/games/{first['id']}/reset")
    assert response.status_code == 409
    assert second["id"] in response.json()["detail"]
    for game in (first, second):
        stored = client.get(f"/api/games/{game['id']}").json()
        assert (stored["generation"], stored["revision"], stored["lifecycle"]) == (
            game["generation"],
            game["revision"],
            "paused",
        )


def test_live_guard_finds_older_paused_table_after_expiring_more_than_five_rows(tmp_path):
    now = [datetime(2026, 1, 1, tzinfo=UTC)]
    manager = GameManager(
        store=DatabaseStore(f"sqlite+aiosqlite:///{tmp_path / 'scan.db'}"),
        clock=lambda: now[0],
        schedule_agents=False,
        schedule_timeouts=False,
    )
    with TestClient(create_app(manager)) as client:
        paused = client.post("/api/games", json={"opponent": "human", "start_paused": True}).json()
        for _ in range(6):
            now[0] += timedelta(seconds=1)
            assert (
                client.post(
                    "/api/games", json={"opponent": "human", "initial_time_ms": 100}
                ).status_code
                == 201
            )
        now[0] += timedelta(seconds=1)
        assert client.get("/api/live-match").json()["id"] == paused["id"]
        assert (
            client.post("/api/games", json={"opponent": "human", "single_game": True}).status_code
            == 409
        )


def test_end_after_clock_expiry_preserves_the_result_and_releases_the_table(tmp_path):
    now = [datetime(2026, 1, 1, tzinfo=UTC)]
    manager = GameManager(
        store=DatabaseStore(f"sqlite+aiosqlite:///{tmp_path / 'expiry.db'}"),
        clock=lambda: now[0],
        schedule_agents=False,
        schedule_timeouts=False,
    )
    with TestClient(create_app(manager)) as client:
        game = client.post("/api/games", json={"opponent": "human", "initial_time_ms": 100}).json()
        now[0] += timedelta(seconds=1)
        ended = client.post(f"/api/games/{game['id']}/abort")
        assert ended.status_code == 200
        assert (ended.json()["lifecycle"], ended.json()["result"]) == ("completed", "0-1")
        assert (
            client.post("/api/games", json={"opponent": "human", "single_game": True}).status_code
            == 201
        )


def test_archive_and_blocking_table_survive_server_restart(tmp_path):
    url = f"sqlite+aiosqlite:///{tmp_path / 'restart.db'}"
    with TestClient(create_app(GameManager(store=DatabaseStore(url)))) as client:
        old = client.post("/api/games", json={"opponent": "human"}).json()
        archived = client.post(f"/api/games/{old['id']}/abort").json()
        live = client.post(
            "/api/games", json={"opponent": "human", "single_game": True, "start_paused": True}
        ).json()
    with TestClient(create_app(GameManager(store=DatabaseStore(url)))) as client:
        assert client.get("/api/live-match").json()["id"] == live["id"]
        saved = client.get(f"/api/games/{old['id']}").json()
        assert (saved["lifecycle"], saved["revision"]) == ("aborted", archived["revision"])
        assert client.post(f"/api/games/{old['id']}/reset").status_code == 409
        assert (
            client.post("/api/games", json={"opponent": "human", "single_game": True}).status_code
            == 409
        )
