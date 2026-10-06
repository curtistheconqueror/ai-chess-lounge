import asyncio
from copy import deepcopy
from uuid import uuid4

import chess
import pytest
from fastapi.testclient import TestClient
from lounge_api.adapters import AdapterRegistry, ScriptedPlayerAdapter
from lounge_api.experiments import ExperimentConfiguration, ExperimentService, SaveExperiment
from lounge_api.main import create_app
from lounge_api.manager import GameManager
from lounge_api.persistence import DatabaseStore
from test_manager import FakeEngine, scripted_player


def configuration():
    return {
        "name": "Comparison",
        "entrants": [
            {"key": key, "player": scripted_player(key).model_dump(mode="json")}
            for key in ["A", "B"]
        ],
        "openings": [{"name": "Start", "moves": []}, {"name": "Open", "moves": ["e2e4", "e7e5"]}],
        "repetitions": 2,
    }


def service():
    return ExperimentService(
        DatabaseStore("sqlite+aiosqlite:///:memory:"), AdapterRegistry([ScriptedPlayerAdapter()])
    )


def test_deterministic_schedule_color_balance_hash_and_opening():
    config = configuration()
    first = service().preview(ExperimentConfiguration.model_validate(config))
    assert first["game_count"] == 8
    assert first["status"] == "draft"
    assert first["exhibition"] is False
    for a, b in zip(first["schedule"][::2], first["schedule"][1::2], strict=True):
        assert a["white"] == b["black"] and a["black"] == b["white"]
        assert a["opening"] == b["opening"] and a["initial_fen"] == b["initial_fen"]
    board = chess.Board()
    board.push_uci("e2e4")
    board.push_uci("e7e5")
    assert first["schedule"][4]["initial_fen"] == board.fen()
    config["entrants"][0]["player"]["player_id"] = str(uuid4())
    again = service().preview(ExperimentConfiguration.model_validate(config))
    assert again == first
    config["increment_ms"] = 3000
    assert (
        service().preview(ExperimentConfiguration.model_validate(config))["configuration_hash"]
        != first["configuration_hash"]
    )


@pytest.mark.parametrize(
    "change",
    [
        "illegal",
        "null",
        "terminal",
        "duplicate",
        "unsupported",
        "huge",
        "color",
        "human",
        "unknown",
        "clock",
    ],
)
def test_invalid_plans_rejected(client, change):
    config = configuration()
    if change == "illegal":
        config["openings"][0]["moves"] = ["e2e5"]
    elif change == "null":
        config["openings"][0]["moves"] = ["0000"]
    elif change == "terminal":
        config["openings"][0]["moves"] = ["f2f3", "e7e5", "g2g4", "d8h4"]
    elif change == "duplicate":
        config["entrants"][1]["key"] = "A"
    elif change == "unsupported":
        config["entrants"][0]["efforts"] = ["deep"]
    elif change == "huge":
        config["openings"] = [{"name": str(i), "moves": []} for i in range(16)]
        config["repetitions"] = 20
    elif change == "color":
        config["entrants"][0]["player"]["settings"] = {"color": "white"}
    elif change == "human":
        config["entrants"][0]["player"].update(adapter_id="human", settings={})
    elif change == "unknown":
        config["secret_key"] = "should-not-persist"
    else:
        config["clock_information"] = "withheld"
    assert client.post("/api/experiments/preview", json=config).status_code == 422
    assert client.get("/api/experiments").json() == []


def test_effort_sweep_captures_provider_mapping_and_pair_count():
    class EffortAdapter(ScriptedPlayerAdapter):
        def capabilities(self, model):
            return {
                **super().capabilities(model),
                "effort_levels": ["fast", "deep"],
                "provider_effort_map": {"fast": "low", "deep": "high"},
            }

    config = configuration()
    config["entrants"][0]["efforts"] = ["fast", "deep"]
    registry = AdapterRegistry([EffortAdapter()])
    preview = ExperimentService(DatabaseStore("sqlite+aiosqlite:///:memory:"), registry).preview(
        ExperimentConfiguration.model_validate(config)
    )
    assert preview["game_count"] == 16
    assert [v["provider_effort"] for v in preview["variants"]] == ["low", "high", None]
    assert all(g["white"].split(":")[0] != g["black"].split(":")[0] for g in preview["schedule"])


def test_saved_plan_restart_idempotency_and_no_games(tmp_path):
    url = f"sqlite+aiosqlite:///{tmp_path / 'experiments.db'}"
    request = {"id": str(uuid4()), "configuration": configuration()}

    def manager():
        return GameManager(
            engine=FakeEngine(),
            store=DatabaseStore(url),
            schedule_agents=False,
            schedule_timeouts=False,
        )

    with TestClient(create_app(manager())) as client:
        first = client.post("/api/experiments", json=request)
        assert first.status_code == 201
        assert client.post("/api/experiments", json=request).json() == first.json()
        assert client.get("/api/experiments").json()[0]["id"] == request["id"]
        conflict = deepcopy(request)
        conflict["configuration"]["name"] = "Different"
        assert client.post("/api/experiments", json=conflict).status_code == 409
        assert client.get("/api/experiments/missing").status_code == 404
    with TestClient(create_app(manager())) as client:
        assert client.get(f"/api/experiments/{request['id']}").json() == first.json()
        assert client.get("/api/experiments?offset=50").json() == []
        from lounge_api.persistence import MatchRow
        from sqlalchemy import func, select

        async def count_games():
            store = DatabaseStore(url)
            try:
                async with store.sessions() as session:
                    return await session.scalar(select(func.count()).select_from(MatchRow))
            finally:
                await store.close()

        assert asyncio.run(count_games()) == 0


def test_concurrent_save_is_exactly_once(tmp_path):
    async def run():
        url = f"sqlite+aiosqlite:///{tmp_path / 'race.db'}"
        stores = [DatabaseStore(url), DatabaseStore(url)]
        for store in stores:
            await store.initialize()
        services = [
            ExperimentService(s, AdapterRegistry([ScriptedPlayerAdapter()])) for s in stores
        ]
        request = SaveExperiment(
            id=uuid4(), configuration=ExperimentConfiguration.model_validate(configuration())
        )
        try:
            a, b = await asyncio.gather(*(s.save(request) for s in services))
            assert a == b
            assert len(await services[0].list()) == 1
        finally:
            for store in stores:
                await store.close()

    asyncio.run(run())
