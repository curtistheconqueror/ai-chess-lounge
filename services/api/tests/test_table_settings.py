import asyncio
import copy
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from lounge_api.main import create_app
from lounge_api.manager import GameManager
from lounge_api.persistence import DatabaseStore
from lounge_api.table_settings import TableSettings, TableSettingsConflict

URL = "/api/table-settings"

DEFAULTS = {
    "white_seat": "human",
    "black_seat": "stockfish",
    "stockfish": {"mode": "elo", "elo": 1600, "skill_level": None},
    "time_control": "5+2",
    "start_paused": False,
}


def changed() -> dict:
    return {
        "white_seat": "anthropic",
        "black_seat": "openai",
        "stockfish": {"mode": "skill", "elo": None, "skill_level": 7},
        "time_control": "10+5",
        "start_paused": True,
    }


def database_url(path: Path) -> str:
    return f"sqlite+aiosqlite:///{path}"


def test_empty_database_returns_defaults_at_revision_zero(client):
    response = client.get(URL)
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"revision", "updated_at", "settings"}
    assert body["revision"] == 0
    assert body["settings"] == DEFAULTS
    assert datetime.fromisoformat(body["updated_at"].replace("Z", "+00:00")).tzinfo is not None
    assert client.get(URL).json() == body


def test_put_increments_revision_and_get_returns_it(client):
    first = client.put(URL, json={"revision": 0, "settings": changed()})
    assert first.status_code == 200
    assert first.json()["revision"] == 1
    assert first.json()["settings"] == changed()
    assert client.get(URL).json() == first.json()

    second_settings = {**changed(), "stockfish": {"mode": "full", "elo": None, "skill_level": None}}
    second = client.put(URL, json={"revision": 1, "settings": second_settings})
    assert second.status_code == 200
    assert second.json()["revision"] == 2
    assert second.json()["settings"] == second_settings
    assert client.get(URL).json() == second.json()
    assert second.json()["updated_at"] >= first.json()["updated_at"]


def test_stale_revision_is_409_and_changes_nothing(client):
    saved = client.put(URL, json={"revision": 0, "settings": changed()}).json()

    stale_zero = client.put(URL, json={"revision": 0, "settings": DEFAULTS})
    assert stale_zero.status_code == 409
    assert isinstance(stale_zero.json()["detail"], str)
    assert client.get(URL).json() == saved

    advanced = client.put(URL, json={"revision": 1, "settings": DEFAULTS}).json()
    assert advanced["revision"] == 2
    for stale in (0, 1, 3):
        rejected = client.put(URL, json={"revision": stale, "settings": changed()})
        assert rejected.status_code == 409
    assert client.get(URL).json() == advanced


def mutate(path: tuple[str, ...], value) -> dict:
    document = copy.deepcopy(changed())
    target = document
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    return document


def with_stockfish(**fields) -> dict:
    return {**changed(), "stockfish": fields}


@pytest.mark.parametrize(
    "settings",
    [
        mutate(("white_seat",), "grandmaster"),
        mutate(("black_seat",), ""),
        mutate(("black_seat",), None),
        mutate(("stockfish", "mode"), "turbo"),
        with_stockfish(mode="elo", elo=799, skill_level=None),
        with_stockfish(mode="elo", elo=3201, skill_level=None),
        with_stockfish(mode="elo", elo=None, skill_level=None),
        with_stockfish(mode="elo", elo=1600.5, skill_level=None),
        with_stockfish(mode="elo", elo="1600", skill_level=None),
        with_stockfish(mode="elo", elo=True, skill_level=None),
        with_stockfish(mode="elo", elo=1600, skill_level=5),
        with_stockfish(mode="skill", elo=1600, skill_level=5),
        with_stockfish(mode="skill", elo=None, skill_level=None),
        with_stockfish(mode="skill", elo=None, skill_level=21),
        with_stockfish(mode="skill", elo=None, skill_level=-1),
        with_stockfish(mode="full", elo=1600, skill_level=None),
        with_stockfish(mode="full", elo=None, skill_level=3),
        mutate(("time_control",), "7+3"),
        mutate(("time_control",), 5),
        mutate(("start_paused",), "yes"),
        mutate(("start_paused",), 1),
        {**changed(), "unexpected": 1},
        {**changed(), "stockfish": {**changed()["stockfish"], "extra": 1}},
        {key: value for key, value in changed().items() if key != "time_control"},
        {key: value for key, value in changed().items() if key != "start_paused"},
    ],
)
def test_invalid_settings_are_422_and_change_nothing(client, settings):
    before = client.get(URL).json()
    response = client.put(URL, json={"revision": 0, "settings": settings})
    assert response.status_code == 422
    assert client.get(URL).json() == before


def test_invalid_envelope_is_422(client):
    assert client.put(URL, json={"settings": changed()}).status_code == 422
    assert client.put(URL, json={"revision": 0}).status_code == 422
    assert client.put(URL, json={"revision": -1, "settings": changed()}).status_code == 422
    assert client.put(URL, json={"revision": "0", "settings": changed()}).status_code == 422
    assert client.put(URL, json={"revision": 0.0, "settings": changed()}).status_code == 422
    extra = {"revision": 0, "settings": changed(), "extra": 1}
    assert client.put(URL, json=extra).status_code == 422
    assert client.get(URL).json()["revision"] == 0


def test_every_seat_time_control_and_stockfish_boundary_is_accepted(client):
    revision = 0
    seats = [
        "human",
        "stockfish",
        "scripted",
        "remote_runner",
        "openai",
        "anthropic",
        "google",
        "openrouter",
        "ollama",
        "vllm",
    ]
    controls = ["1+0", "3+2", "5+2", "10+5"]
    for index, seat in enumerate(seats):
        settings = {
            **changed(),
            "white_seat": seat,
            "black_seat": seat,
            "time_control": controls[index % len(controls)],
        }
        response = client.put(URL, json={"revision": revision, "settings": settings})
        assert response.status_code == 200, (seat, response.text)
        revision = response.json()["revision"]
    for control in controls:
        settings = {**changed(), "time_control": control}
        response = client.put(URL, json={"revision": revision, "settings": settings})
        assert response.status_code == 200, (control, response.text)
        revision = response.json()["revision"]
    for stockfish in (
        {"mode": "elo", "elo": 800, "skill_level": None},
        {"mode": "elo", "elo": 3200, "skill_level": None},
        {"mode": "skill", "elo": None, "skill_level": 0},
        {"mode": "skill", "elo": None, "skill_level": 20},
        {"mode": "full", "elo": None, "skill_level": None},
    ):
        settings = {**changed(), "stockfish": stockfish}
        response = client.put(URL, json={"revision": revision, "settings": settings})
        assert response.status_code == 200, (stockfish, response.text)
        assert response.json()["settings"]["stockfish"] == stockfish
        revision = response.json()["revision"]
    # Omitting a nullable stockfish field is the same as sending null.
    omitted = {**changed(), "stockfish": {"mode": "full"}}
    response = client.put(URL, json={"revision": revision, "settings": omitted})
    assert response.status_code == 200
    assert response.json()["settings"]["stockfish"] == {
        "mode": "full",
        "elo": None,
        "skill_level": None,
    }


def test_settings_persist_across_a_new_app_and_store(tmp_path):
    url = database_url(tmp_path / "persist.db")
    with TestClient(create_app(GameManager(store=DatabaseStore(url)))) as first:
        saved = first.put(URL, json={"revision": 0, "settings": changed()}).json()
        assert saved["revision"] == 1
    with TestClient(create_app(GameManager(store=DatabaseStore(url)))) as second:
        assert second.get(URL).json() == saved
        assert second.put(URL, json={"revision": 0, "settings": DEFAULTS}).status_code == 409
        advanced = second.put(URL, json={"revision": 1, "settings": DEFAULTS}).json()
        assert advanced["revision"] == 2
    with TestClient(create_app(GameManager(store=DatabaseStore(url)))) as third:
        assert third.get(URL).json() == advanced


def test_concurrent_puts_with_the_same_revision_have_exactly_one_winner(client):
    def attempt(index: int):
        settings = {**changed(), "stockfish": {"mode": "skill", "elo": None, "skill_level": index}}
        return client.put(URL, json={"revision": 0, "settings": settings}), index

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(attempt, range(8)))
    assert sorted(response.status_code for response, _ in results) == [200] + [409] * 7
    winner, index = next((response, i) for response, i in results if response.status_code == 200)
    stored = client.get(URL).json()
    assert stored["revision"] == 1
    assert stored["settings"]["stockfish"]["skill_level"] == index
    assert stored == winner.json()

    def update(_: int):
        return client.put(URL, json={"revision": 1, "settings": DEFAULTS})

    with ThreadPoolExecutor(max_workers=8) as pool:
        later = list(pool.map(update, range(8)))
    assert sorted(response.status_code for response in later) == [200] + [409] * 7
    assert client.get(URL).json()["revision"] == 2


def test_store_cas_is_exclusive_across_independent_connections(tmp_path):
    url = database_url(tmp_path / "race.db")

    async def run() -> None:
        stores = [DatabaseStore(url) for _ in range(6)]
        try:
            await stores[0].initialize()
            for expected in (0, 1):
                outcomes = await asyncio.gather(
                    *(
                        store.save_table_settings(
                            TableSettings.defaults(), expected_revision=expected
                        )
                        for store in stores
                    ),
                    return_exceptions=True,
                )
                wins = [o for o in outcomes if not isinstance(o, BaseException)]
                losses = [o for o in outcomes if isinstance(o, TableSettingsConflict)]
                assert len(wins) == 1, outcomes
                assert len(losses) == len(stores) - 1, outcomes
                assert wins[0][0] == expected + 1
            loaded = await stores[0].load_table_settings()
            assert loaded is not None
            assert loaded[0] == 2
            assert loaded[1] == TableSettings.defaults()
        finally:
            for store in stores:
                await store.close()

    asyncio.run(run())


def test_existing_0012_database_gains_the_table_on_startup(tmp_path):
    path = tmp_path / "old.db"
    url = database_url(path)
    with TestClient(create_app(GameManager(store=DatabaseStore(url)))) as seeded:
        assert seeded.get(URL).json()["revision"] == 0
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.execute("DROP TABLE table_settings")
        connection.execute("UPDATE alembic_version SET version_num='0012_comparison_games'")
    with TestClient(create_app(GameManager(store=DatabaseStore(url)))) as upgraded:
        assert upgraded.get(URL).json()["revision"] == 0
        saved = upgraded.put(URL, json={"revision": 0, "settings": changed()})
        assert saved.status_code == 200
