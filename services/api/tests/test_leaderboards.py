import asyncio
import os
from copy import deepcopy

import pytest
from lounge_api.comparison_identity import IdentityDeclaration, snapshot
from lounge_api.domain import GameSession
from lounge_api.leaderboards import Leaderboards, aggregate
from lounge_api.models import CreateGameRequest, MatchState, OpponentKind
from lounge_api.persistence import ComparisonGameRow, ConcurrentGameUpdate, DatabaseStore
from lounge_api.player_protocol import PlayerConfiguration
from pydantic import ValidationError
from sqlalchemy import select


def player(version, **metadata):
    p = PlayerConfiguration(
        adapter_id="scripted",
        display_name="Fixture",
        provider="Reference",
        model="deterministic-v1",
        connection_mode="local",
        settings={},
    )
    return p.model_copy(
        update={
            "display_name": "Private operator name",
            "comparison": IdentityDeclaration(model_version=version, **metadata),
        }
    )


def fixture():
    g = GameSession(white_player=player("fixture-v1"), black_player=player("fixture-v2"))
    return snapshot(g), {
        "lifecycle": "completed",
        "status": "checkmate",
        "result": "1-0",
        "takeover": False,
        "consultation": False,
        "moves": 4,
    }


def test_denominators_draws_forfeits_and_head_to_head():
    doc, win = fixture()
    draw = {**win, "status": "draw", "result": "1/2-1/2"}
    lose = {**win, "status": "timeout", "result": "0-1"}
    aborted = {**win, "lifecycle": "aborted", "result": "*"}
    report = aggregate([(doc, x) for x in [win, draw, lose, aborted]])
    a = next(r for r in report["rows"] if r["identity"]["version"]["value"] == "fixture-v1")
    assert a["counts"] == {
        "total_games": 4,
        "eligible_games": 3,
        "wins": 1,
        "losses": 1,
        "draws": 1,
        "forfeits": 1,
        "excluded": {"aborted": 1},
        "rate_denominator": 3,
        "win_rate": 1 / 3,
        "draw_rate": 1 / 3,
        "loss_rate": 1 / 3,
        "score_rate": 0.5,
    }
    assert a["colors"]["white"]["eligible_games"] == 3
    assert a["colors"]["black"]["win_rate"] is None
    assert report["head_to_head"][0]["counts"]["total_games"] == 4
    assert report["head_to_head"][0]["counts"]["rate_denominator"] == 3
    filtered = aggregate([(doc, lose)], include_forfeits=False)
    assert filtered["excluded_games"] == {"forfeit_excluded": 1}


@pytest.mark.parametrize(
    "change, reason",
    [
        ({"takeover": True}, "assistance_changed"),
        ({"consultation": True}, "assistance_changed"),
        ({"lifecycle": "adjudicated"}, "adjudicated"),
        ({"lifecycle": "running", "result": "*"}, "unfinished_or_reset"),
    ],
)
def test_exclusions_never_become_losses(change, reason):
    doc, result = fixture()
    report = aggregate([(doc, {**result, **change})])
    assert report["excluded_games"] == {reason: 1}
    assert all(
        r["counts"]["eligible_games"] == 0 and r["counts"]["losses"] == 0 for r in report["rows"]
    )


def test_conditions_and_color_swaps_are_explicit():
    doc, result = fixture()
    swapped = deepcopy(doc)
    swapped["seats"] = {"white": doc["seats"]["black"], "black": doc["seats"]["white"]}
    other_clock = deepcopy(doc)
    other_clock["conditions"]["initial_time_ms"] = 1000
    engine = deepcopy(doc)
    engine["conditions"]["engines"] = [
        {"target_elo": 2500, "move_time_ms": 400, "version": {"value": None, "evidence": "unknown"}}
    ]
    report = aggregate(
        [
            (doc, result),
            (swapped, {**result, "result": "0-1"}),
            (other_clock, result),
            (engine, result),
        ]
    )
    assert len(report["rows"]) == 6
    a = next(
        r
        for r in report["rows"]
        if r["identity"]["version"]["value"] == "fixture-v1" and r["counts"]["total_games"] == 2
    )
    assert a["colors"]["white"]["wins"] == a["colors"]["black"]["wins"] == 1
    assert (
        aggregate([(doc, result)], color="black")["rows"][0]["colors"]["white"]["total_games"] == 0
    )


def test_filters_grouping_and_unknown_evidence():
    doc, result = fixture()
    doc["seats"]["white"]["access"] = {"value": "subscription", "evidence": "declared"}
    doc["seats"]["white"]["effort_raw"] = {
        "value": "provider-specific-budget=8192",
        "evidence": "declared",
    }
    assert (
        aggregate([(doc, result)], filters={"version": "fixture-v1", "access": "subscription"})[
            "selected_games"
        ]
        == 1
    )
    assert aggregate([(doc, result)], filters={"version": "absent"})["selected_games"] == 0
    assert aggregate([(doc, result)], grouping="model")["excluded_games"] == {
        "same_comparison_group": 1
    }
    row = aggregate([(doc, result)], grouping="model")["rows"][0]
    assert row["counts"]["total_games"] == 1 and len(row["variants"]) == 2


def test_opt_in_names_and_verification_cannot_be_forged():
    with pytest.raises(ValidationError):
        IdentityDeclaration(listing_alias="Personal name")
    with pytest.raises(ValidationError):
        IdentityDeclaration(model_version="fixture-v1", evidence="verified")
    g = GameSession(
        white_player=player("fixture-v1"),
        black_player=player("fixture-v2", listing_opt_in=True, listing_alias="Opted bot"),
    )
    doc = snapshot(g)
    assert "Private operator name" not in str(doc)
    assert doc["seats"]["white"]["version"]["evidence"] == "declared"
    assert doc["seats"]["white"]["effort_normalized"]["value"] is None
    assert aggregate([(doc, fixture()[1])])["rows"][0]["opt_in_aliases"] == []
    assert sorted(
        a for r in aggregate([(doc, fixture()[1])])["rows"] for a in r["opt_in_aliases"]
    ) == ["Opted bot"]
    assert "comparison" not in PlayerConfiguration.human("white").model_dump(mode="json")


@pytest.mark.parametrize("backend", ["sqlite", "postgres"])
def test_persisted_snapshot_restart_cas_and_reset_history(tmp_path, backend):
    if backend == "postgres" and not os.getenv("TEST_POSTGRES_URL"):
        pytest.skip("TEST_POSTGRES_URL required for native snapshot transaction evidence")

    async def run():
        from lounge_api.manager import GameManager

        store = DatabaseStore(
            os.environ["TEST_POSTGRES_URL"]
            if backend == "postgres"
            else f"sqlite+aiosqlite:///{tmp_path / 'leaderboard.db'}"
        )
        manager = GameManager(store=store, schedule_agents=False, schedule_timeouts=False)
        try:
            game = await manager.create(
                CreateGameRequest(
                    opponent=OpponentKind.HUMAN,
                    white_player=player("fixture-v1"),
                    black_player=player("fixture-v2"),
                )
            )
            initial = deepcopy(game.comparison_snapshot)
            for move in ["f2f3", "e7e5", "g2g4", "d8h4"]:
                revision = game.revision
                record = game.apply_uci(move, actor="fixture", position_version=game.version)
                await store.record_move(game, record, [], expected_revision=revision)
            assert game.lifecycle == MatchState.COMPLETED
            game.white_player.comparison.model_version = "changed-after-game"
            await store.record_action(game, [], expected_revision=game.revision)
            with pytest.raises(ConcurrentGameUpdate):
                await store.record_action(game, [], expected_revision=-1)
            restored = await store.load_game(game.id)
            assert restored.comparison_snapshot == initial
            await manager.reset(game.id)
            async with store.sessions() as session:
                history = list(
                    await session.scalars(
                        select(ComparisonGameRow)
                        .where(ComparisonGameRow.match_id == game.id)
                        .order_by(ComparisonGameRow.generation)
                    )
                )
            assert len(history) == 2
            assert history[0].identity == initial
            assert history[0].outcome["result"] == "0-1"
            report = await Leaderboards(store).get()
            assert report["selected_games"] == 2
            assert report["excluded_games"] == {"unfinished_or_reset": 1}
            assert report["legacy_games_without_snapshot"] == 0
        finally:
            await manager.close()

    asyncio.run(run())


def test_api_unknown_legacy_and_pairing_declarations(client):
    created = client.post("/api/games", json={"opponent": "human"}).json()
    assert created["comparison_snapshot"]["seats"]["white"]["version"] == {
        "value": None,
        "evidence": "unknown",
    }
    report = client.get("/api/leaderboards").json()
    assert report["selected_games"] >= 1
    assert client.get("/api/leaderboards?grouping=invalid").status_code == 422
    assert client.get("/api/leaderboards?color=red").status_code == 422
    paired = client.post(
        "/api/runner-pairings",
        json={
            "display_name": "Private bot",
            "provider": "Independent Runner",
            "model": "configured-alias",
            "comparison": {
                "underlying_provider": "Fixture Provider",
                "harness": "Fixture harness",
                "model_version": "declared-fixture-version",
                "effort_raw": "custom-budget",
            },
        },
    )
    assert paired.status_code == 201
    assert paired.json()["player"]["comparison"]["harness"] == "Fixture harness"


def test_provider_observations_are_untrusted_labels_and_changes_excluded():
    from lounge_api.player_protocol import MoveProposal

    proposal = MoveProposal(
        request_id="fixture",
        match_id="fixture",
        position_version=0,
        move="e2e4",
        plan="fixture",
        threat="fixture",
        provider_model="forged",
        _provider_model="forged",
    )
    assert proposal._provider_model is None
    assert "provider_model" not in proposal.model_dump()
    proposal.with_provider_observation("response-alias")
    assert proposal._provider_model == "response-alias"
    assert "response-alias" not in proposal.model_dump_json()
    proposal.with_provider_observation("x" * 161)
    assert proposal._provider_model == "response-alias"
    doc, result = fixture()
    report = aggregate(
        [
            (
                doc,
                {
                    **result,
                    "observed_models": {"white": ["alias-1", "alias-2"], "black": ["alias-3"]},
                },
            )
        ]
    )
    assert report["excluded_games"] == {"observed_model_changed": 1}
    assert all(r["counts"]["eligible_games"] == 0 for r in report["rows"])
    b = next(r for r in report["rows"] if r["identity"]["version"]["value"] == "fixture-v2")
    assert b["identity"]["observed_models"]["evidence"] == "observed_provider_response"
    assert b["identity"]["version"]["evidence"] == "declared"


def test_family_grouping_retains_variants_and_raw_declarations():
    doc, result = fixture()
    for color in ("white", "black"):
        doc["seats"][color]["family"] = {"value": "fixture-family", "evidence": "declared"}
    doc["seats"]["black"]["model"] = {
        "value": "different-alias",
        "evidence": "recorded_configuration",
    }
    grouped = aggregate([(doc, result)], grouping="family")
    assert len(grouped["rows"]) == 1
    assert len(grouped["rows"][0]["variants"]) == 2
    assert grouped["excluded_games"] == {"same_comparison_group": 1}
    with pytest.raises(ValidationError, match="whitespace-only"):
        IdentityDeclaration(model_version="   ")


def test_legacy_records_are_retained_and_not_reconstructed(tmp_path):
    async def run():
        store = DatabaseStore(f"sqlite+aiosqlite:///{tmp_path / 'legacy.db'}")
        try:
            game = GameSession(white_player=player("changed-current-setting"))
            await store.create_game(game, [])
            restored = await store.load_game(game.id)
            assert restored.comparison_snapshot is None
            await store.record_action(restored, [], expected_revision=restored.revision)
            report = await Leaderboards(store).get()
            assert report["selected_games"] == 0
            assert report["legacy_games_without_snapshot"] == 1
            assert report["rows"] == []
        finally:
            await store.close()

    asyncio.run(run())


def test_strength_and_request_bounds_never_collapse():
    a = PlayerConfiguration.stockfish("white", target_elo=1600)
    b = PlayerConfiguration.stockfish("black", target_elo=2500)
    game = GameSession(white_player=a, black_player=b)
    doc = snapshot(game)
    swapped = snapshot(GameSession(white_player=b, black_player=a))
    report = aggregate([(doc, fixture()[1]), (swapped, fixture()[1])], grouping="model")
    assert len(report["rows"]) == 2
    assert len(report["head_to_head"]) == 1
    assert all(r["counts"]["rate_denominator"] == 2 for r in report["rows"])

    assert all(
        r["colors"]["white"]["eligible_games"] == r["colors"]["black"]["eligible_games"] == 1
        for r in report["rows"]
    )


def test_known_adapter_mapping_preserves_declared_raw_effort():
    from lounge_api.player_protocol import EffortLevel

    class Adapter:
        def capabilities(self, model):
            return {"provider_effort_map": {EffortLevel.DEEP: "fixture-native-budget"}}

    class Registry:
        def get(self, adapter):
            return Adapter()

    p = player("fixture-v1", effort_raw="declared-external-setting").model_copy(
        update={"effort": EffortLevel.DEEP}
    )
    seat = snapshot(GameSession(white_player=p), Registry())["seats"]["white"]
    assert seat["effort_raw"] == {
        "value": "fixture-native-budget",
        "evidence": "recorded_adapter_mapping",
    }
    assert seat["effort_declared"] == {"value": "declared-external-setting", "evidence": "declared"}
    assert seat["effort_normalized"] == {"value": "deep", "evidence": "recorded_adapter_mapping"}


def test_bounded_report_exposes_incomplete_coverage(tmp_path, monkeypatch):
    monkeypatch.setattr("lounge_api.leaderboards.MAX_RECORDS", 2)

    async def run():
        store = DatabaseStore(f"sqlite+aiosqlite:///{tmp_path / 'bounded.db'}")
        try:
            for _ in range(3):
                game = GameSession(
                    white_player=player("fixture-v1"), black_player=player("fixture-v2")
                )
                game.comparison_snapshot = snapshot(game)
                await store.create_game(game, [])
            report = await Leaderboards(store).get()
            assert report["truncated"] is True
            assert report["record_limit"] == report["selected_games"] == 2
            assert all(r["counts"]["total_games"] == 2 for r in report["rows"])
            assert report["legacy_games_without_snapshot"] == 0
        finally:
            await store.close()

    asyncio.run(run())


def test_reset_refreshes_engine_evidence_without_rewriting_history(tmp_path):
    from lounge_api.manager import GameManager
    from lounge_api.models import EngineSummary
    from test_manager import FakeEngine

    class ChangingEngine(FakeEngine):
        reported_version = "fixture-runtime-1"

        async def summary(self, target_elo, move_time_ms):
            return EngineSummary(
                name="Stockfish",
                available=True,
                target_elo=target_elo,
                move_time_ms=move_time_ms,
                version=self.reported_version,
            )

    async def run():
        engine = ChangingEngine()
        manager = GameManager(
            engine=engine,
            store=DatabaseStore(f"sqlite+aiosqlite:///{tmp_path / 'runtime.db'}"),
            schedule_agents=False,
            schedule_timeouts=False,
        )
        try:
            game = await manager.create(CreateGameRequest(opponent=OpponentKind.STOCKFISH))
            engine.reported_version = "fixture-runtime-2"
            new = await manager.reset(game.id)
            assert (
                new.comparison_snapshot["seats"]["black"]["version"]["value"] == "fixture-runtime-2"
            )
            async with manager.store.sessions() as session:
                old = await session.get(ComparisonGameRow, (game.id, 0))
                assert old.identity["seats"]["black"]["version"]["value"] == "fixture-runtime-1"
        finally:
            await manager.close()

    asyncio.run(run())


@pytest.mark.parametrize("connector", ["ollama", "vllm"])
def test_local_serving_connector_does_not_invent_underlying_provider(connector):
    p = PlayerConfiguration(
        adapter_id=connector,
        display_name="Private bot",
        provider=connector,
        model="installed-alias",
        connection_mode="local",
        settings={},
    )
    game = GameSession(white_player=p)
    seat = snapshot(game)["seats"]["white"]
    assert seat["provider"] == {"value": None, "evidence": "unknown"}
    assert seat["provider_label"]["value"] == connector
    assert seat["connector"] == connector
    p.comparison = IdentityDeclaration(underlying_provider="Fixture declared provider")
    assert snapshot(game)["seats"]["white"]["provider"]["evidence"] == "declared"
