"""Hosted friend games: first-move timers, the lobby, challenges and seat rules."""

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from lounge_api import hosted_auth
from lounge_api.domain import GameSession
from lounge_api.hosted_auth import InvalidToken, TokenVerifier
from lounge_api.main import create_app
from lounge_api.manager import GameManager
from lounge_api.models import MatchState, OpponentKind
from lounge_api.persistence import DatabaseStore
from test_hosted_access import ACCOUNTS, ORIGIN, auth, hosted_env, invite
from test_manager import FakeEngine

BOB, CAROL = "bob@example.com", "carol@example.com"
T0 = datetime(2026, 10, 18, 12, 0, tzinfo=UTC)


# --- first-move timers (domain) -------------------------------------------------------
def friend_session() -> GameSession:
    game = GameSession(
        opponent=OpponentKind.HUMAN,
        initial_time_ms=60_000,
        increment_ms=2_000,
        white_user_id="w",
        black_user_id="b",
        first_move_window_ms=30_000,
    )
    game.start(now=T0)
    return game


def test_clocks_wait_for_each_first_move_without_increment():
    game = friend_session()
    clock = game.clock_snapshot(T0 + timedelta(seconds=20))
    # Frozen: no running turn, full time, a first-move countdown instead.
    assert clock.turn_started_at is None and clock.white_remaining_ms == 60_000
    assert clock.first_move_deadline_at == (T0 + timedelta(seconds=30)).isoformat()
    game.apply_uci("e2e4", actor="human:white", now=T0 + timedelta(seconds=20))
    assert game.white_remaining_ms == 60_000  # nothing used, no increment
    game.apply_uci("e7e5", actor="human:black", now=T0 + timedelta(seconds=45))
    assert game.black_remaining_ms == 60_000
    # From here it is normal chess: White's clock runs.
    clock = game.clock_snapshot(T0 + timedelta(seconds=50))
    assert clock.first_move_deadline_at is None and clock.white_remaining_ms == 55_000
    game.apply_uci("g1f3", actor="human:white", now=T0 + timedelta(seconds=50))
    assert game.white_remaining_ms == 57_000  # 55 s + 2 s increment


@pytest.mark.parametrize("missing", ["white", "black"])
def test_a_missed_first_move_aborts_without_a_result(missing):
    game = friend_session()
    start = T0
    if missing == "black":
        game.apply_uci("d2d4", actor="human:white", now=T0 + timedelta(seconds=5))
        start = T0 + timedelta(seconds=5)
    assert not game.expire_if_needed(start + timedelta(seconds=29))
    assert game.expire_if_needed(start + timedelta(seconds=30))
    assert game.lifecycle is MatchState.ABORTED and game.result == "*"
    assert game.termination_reason == f"no_first_move_{missing}"
    assert f"{missing.title()} did not make a first move" in game.snapshot(now=T0).strategy_banner


def test_ordinary_games_keep_running_clocks():
    game = GameSession(opponent=OpponentKind.HUMAN, initial_time_ms=60_000, increment_ms=0)
    game.start(now=T0)
    assert game.clock_snapshot(T0 + timedelta(seconds=10)).white_remaining_ms == 50_000
    assert game.clock_snapshot(T0).first_move_deadline_at is None


# --- hosted lobby and challenges --------------------------------------------------------
class Clock:
    def __init__(self):
        self.now = datetime.now(UTC)

    def __call__(self):
        return self.now


def build(tmp_path: Path, monkeypatch, clock=None, **env):
    database = f"sqlite+aiosqlite:///{tmp_path / 'friends.db'}"
    monkeypatch.setenv("LOUNGE_DEPLOYMENT", "local")
    monkeypatch.setenv("LOUNGE_HOSTED_MODE", "0")
    store = DatabaseStore(database)
    asyncio.run(store.initialize())
    asyncio.run(store.close())
    hosted_env(monkeypatch, **env)

    async def verify(self, token):
        if token not in ACCOUNTS:
            raise InvalidToken
        return ACCOUNTS[token]

    monkeypatch.setattr(TokenVerifier, "verify", verify)
    manager = GameManager(
        engine=FakeEngine(),
        analysis_engine=FakeEngine(),
        store=DatabaseStore(database),
        clock=clock,
    )
    return TestClient(create_app(manager), base_url=ORIGIN)


@pytest.fixture
def lounge(tmp_path, monkeypatch):
    # Generous write budget: these tests make many quick moves.
    monkeypatch.setattr(hosted_auth, "WRITE_LIMIT_PER_MINUTE", 10_000)
    with build(tmp_path, monkeypatch) as client:
        invite(client, BOB)
        invite(client, CAROL)
        for token in ("token-bob", "token-carol"):  # sign in once (binds the account)
            assert client.get("/api/auth/me", headers=auth(token)).status_code == 200
        yield client


def challenge(client, token, opponent, **extra):
    body = {"opponent_email": opponent, "initial_time_ms": 600_000, "increment_ms": 0, **extra}
    return client.post("/api/challenges", json=body, headers=auth(token))


def lobby(client, token):
    response = client.get("/api/lobby", headers=auth(token))
    assert response.status_code == 200, response.text
    return response.json()


def start_friend_game(client, color="white"):
    sent = challenge(client, "token-bob", CAROL, color=color)
    assert sent.status_code == 201, sent.text
    accepted = client.post(
        f"/api/challenges/{sent.json()['id']}/accept", headers=auth("token-carol")
    )
    assert accepted.status_code == 200, accepted.text
    game_id = accepted.json()["game_id"]
    return client.get(f"/api/games/{game_id}", headers=auth("token-bob")).json()


def move(client, token, game, uci):
    current = client.get(f"/api/games/{game['id']}", headers=auth(token)).json()
    return client.post(
        f"/api/games/{game['id']}/moves",
        headers=auth(token),
        json={"move": uci, "position_version": current["version"]},
    )


def test_lobby_shows_who_is_invited_online_and_in_a_game(tmp_path, monkeypatch):
    with build(tmp_path, monkeypatch) as client:
        invite(client, BOB)
        invite(client, CAROL)
        seen = {m["email"]: m["status"] for m in lobby(client, "token-admin")["members"]}
        assert seen == {BOB: "invited", CAROL: "invited"}  # neither has signed in
        assert client.get("/api/auth/me", headers=auth("token-bob")).status_code == 200
        seen = {m["email"]: m for m in lobby(client, "token-admin")["members"]}
        assert seen[BOB]["status"] == "online" and seen[BOB]["name"] == "bob"
        assert seen[CAROL]["status"] == "invited"
        assert "owner@example.com" not in seen  # you are not your own friend


def test_challenge_waits_then_starts_a_game_both_players_can_open(lounge):
    sent = challenge(lounge, "token-bob", CAROL, color="white")
    assert sent.status_code == 201
    outgoing = lobby(lounge, "token-bob")["outgoing"]
    assert [(c["to"], c["status"]) for c in outgoing] == [("carol", "pending")]
    incoming = lobby(lounge, "token-carol")["incoming"]
    assert [(c["from"], c["color"]) for c in incoming] == [("bob", "white")]
    # The admin sees no challenge that is not theirs.
    assert lobby(lounge, "token-admin")["incoming"] == []
    accepted = lounge.post(
        f"/api/challenges/{sent.json()['id']}/accept", headers=auth("token-carol")
    )
    game_id = accepted.json()["game_id"]
    # The challenger's lobby reports the acceptance and the game to open.
    done = lobby(lounge, "token-bob")["outgoing"][0]
    assert done["status"] == "accepted" and done["game_id"] == game_id
    for token in ("token-bob", "token-carol"):
        assert lounge.get("/api/live-match", headers=auth(token)).json()["id"] == game_id
        assert lobby(lounge, token)["live_game_id"] == game_id
    game = lounge.get(f"/api/games/{game_id}", headers=auth("token-carol")).json()
    assert game["white_user_id"] == ACCOUNTS["token-bob"][0]
    assert game["black_user_id"] == ACCOUNTS["token-carol"][0]
    assert game["white_player"]["display_name"] == "bob"
    assert game["clock"]["first_move_deadline_at"] is not None
    assert {m["email"]: m["status"] for m in lobby(lounge, "token-admin")["members"]} == {
        BOB: "in_game",
        CAROL: "in_game",
    }


def test_challenge_rules(lounge):
    assert challenge(lounge, "token-bob", BOB).status_code == 422
    assert challenge(lounge, "token-bob", "stranger@example.com").status_code == 404
    first = challenge(lounge, "token-bob", CAROL)
    assert challenge(lounge, "token-bob", "owner@example.com").status_code == 409  # one at a time
    cid = first.json()["id"]
    # Only the opponent may accept or decline; only the challenger may cancel.
    assert (
        lounge.post(f"/api/challenges/{cid}/accept", headers=auth("token-admin")).status_code == 404
    )
    assert (
        lounge.post(f"/api/challenges/{cid}/cancel", headers=auth("token-carol")).status_code == 404
    )
    assert (
        lounge.post(f"/api/challenges/{cid}/decline", headers=auth("token-carol")).status_code
        == 204
    )
    assert lobby(lounge, "token-bob")["outgoing"][0]["status"] == "declined"
    assert (
        lounge.post(f"/api/challenges/{cid}/accept", headers=auth("token-carol")).status_code == 409
    )
    again = challenge(lounge, "token-bob", CAROL).json()["id"]
    assert (
        lounge.post(f"/api/challenges/{again}/cancel", headers=auth("token-bob")).status_code == 204
    )
    assert lobby(lounge, "token-carol")["incoming"] == []


def test_two_people_cannot_both_win_an_accept(lounge):
    cid = challenge(lounge, "token-bob", CAROL).json()["id"]
    with ThreadPoolExecutor(4) as pool:
        codes = list(
            pool.map(
                lambda _: (
                    lounge.post(
                        f"/api/challenges/{cid}/accept", headers=auth("token-carol")
                    ).status_code
                ),
                range(4),
            )
        )
    assert sorted(codes) == [200, 409, 409, 409]
    assert len({lobby(lounge, t)["live_game_id"] for t in ("token-bob", "token-carol")}) == 1


def test_a_busy_challenger_cannot_be_dragged_into_a_second_game(lounge):
    cid = challenge(lounge, "token-bob", CAROL).json()["id"]
    # Bob starts a solo game against Stockfish while the challenge waits.
    assert (
        lounge.post(
            "/api/games", json={"initial_time_ms": 600_000}, headers=auth("token-bob")
        ).status_code
        == 201
    )
    busy = lounge.post(f"/api/challenges/{cid}/accept", headers=auth("token-carol"))
    assert busy.status_code == 409 and "bob is already in a game" in busy.json()["detail"]


def test_each_player_acts_only_for_their_own_side(lounge):
    game = start_friend_game(lounge, color="white")  # bob is White
    gid = game["id"]
    assert move(lounge, "token-carol", game, "e7e5").status_code == 403  # not her move
    assert move(lounge, "token-bob", game, "e2e4").status_code == 200
    assert move(lounge, "token-bob", game, "d2d4").status_code == 403  # not his move now
    assert move(lounge, "token-carol", game, "e7e5").status_code == 200
    revision = lounge.get(f"/api/games/{gid}", headers=auth("token-bob")).json()["revision"]
    for action, body in (
        ("pause", {"expected_revision": revision}),
        ("reset", None),
        ("adjudicate", {"result": "1-0"}),
    ):
        response = lounge.post(f"/api/games/{gid}/{action}", json=body, headers=auth("token-bob"))
        assert response.status_code == 409, action
    seat = {
        "player": {
            "adapter_id": "stockfish",
            "display_name": "SF",
            "provider": "stockfish",
            "model": "stockfish",
            "connection_mode": "local",
        },
        "expected_revision": 0,
    }
    assert (
        lounge.post(
            f"/api/games/{gid}/seats/black", json=seat, headers=auth("token-bob")
        ).status_code
        == 409
    )
    # Both have moved: abort is over, resign instead.
    assert (
        lounge.post(f"/api/games/{gid}/abort", json={}, headers=auth("token-bob")).status_code
        == 409
    )
    assert (
        lounge.post(
            f"/api/games/{gid}/resign", json={"color": "black"}, headers=auth("token-bob")
        ).status_code
        == 403
    )
    # Engine analysis would be a built-in cheat while the game is live.
    assert lounge.get(f"/api/games/{gid}/analysis", headers=auth("token-bob")).status_code == 403
    resigned = lounge.post(f"/api/games/{gid}/resign", json={}, headers=auth("token-carol"))
    assert resigned.status_code == 200 and resigned.json()["result"] == "1-0"
    assert lounge.get(f"/api/games/{gid}/analysis", headers=auth("token-bob")).status_code == 200


def test_outsiders_cannot_see_a_friend_game_but_the_players_can_watch_it_live(lounge):
    game = start_friend_game(lounge)
    assert lounge.get(f"/api/games/{game['id']}", headers=auth("token-admin")).status_code == 200
    ACCOUNTS["token-dave"] = ("66666666-6666-6666-6666-666666666666", "dave@example.com")
    try:
        invite(lounge, "dave@example.com")
        assert lounge.get(f"/api/games/{game['id']}", headers=auth("token-dave")).status_code == 404
    finally:
        del ACCOUNTS["token-dave"]
    for token in ("token-bob", "token-carol"):
        ticket = lounge.post("/api/ws-ticket", headers=auth(token)).json()["ticket"]
        with lounge.websocket_connect(
            f"/ws/games/{game['id']}?ticket={ticket}", headers={"origin": ORIGIN}
        ) as ws:
            assert ws.receive_json()["payload"]["id"] == game["id"]


def test_abort_is_allowed_before_the_first_moves(lounge):
    game = start_friend_game(lounge)
    aborted = lounge.post(f"/api/games/{game['id']}/abort", json={}, headers=auth("token-carol"))
    assert aborted.status_code == 200 and aborted.json()["lifecycle"] == "aborted"


def test_missing_the_first_move_aborts_the_game_for_both(tmp_path, monkeypatch):
    clock = Clock()
    with build(tmp_path, monkeypatch, clock=clock) as client:
        invite(client, BOB)
        invite(client, CAROL)
        for token in ("token-bob", "token-carol"):
            client.get("/api/auth/me", headers=auth(token))
        game = start_friend_game(client)
        clock.now += timedelta(seconds=31)
        # The server's own timeout job may hold the game for an instant; the abort lands
        # on the next read (and is pushed to both boards).
        for _ in range(20):
            late = client.get(f"/api/games/{game['id']}", headers=auth("token-carol")).json()
            if late["lifecycle"] == "aborted":
                break
            time.sleep(0.05)
        assert (
            late["lifecycle"] == "aborted" and late["termination_reason"] == "no_first_move_white"
        )
        # Both are free to play again.
        assert lobby(client, "token-bob")["live_game_id"] is None


def test_rematch_swaps_colours(lounge):
    game = start_friend_game(lounge, color="white")  # bob White
    lounge.post(f"/api/games/{game['id']}/abort", json={}, headers=auth("token-bob"))
    rematch = lounge.post(f"/api/games/{game['id']}/rematch", headers=auth("token-carol"))
    assert rematch.status_code == 201
    # Carol was Black, so she asks for White this time.
    assert rematch.json()["color"] == "white" and rematch.json()["to_email"] == BOB
    accepted = lounge.post(
        f"/api/challenges/{rematch.json()['id']}/accept", headers=auth("token-bob")
    )
    second = lounge.get(
        f"/api/games/{accepted.json()['game_id']}", headers=auth("token-bob")
    ).json()
    assert second["white_user_id"] == ACCOUNTS["token-carol"][0]


def test_challenges_expire(tmp_path, monkeypatch):
    with build(tmp_path, monkeypatch) as client:
        invite(client, BOB)
        invite(client, CAROL)
        client.get("/api/auth/me", headers=auth("token-bob"))
        cid = challenge(client, "token-bob", CAROL).json()["id"]
        from lounge_api import friend_games

        monkeypatch.setattr(friend_games, "datetime", _Shifted(timedelta(minutes=61)))
        assert lobby(client, "token-carol")["incoming"] == []
        assert (
            client.post(f"/api/challenges/{cid}/accept", headers=auth("token-carol")).status_code
            == 409
        )


class _Shifted:
    """datetime stand-in that runs ahead by a fixed offset."""

    def __init__(self, offset):
        self.offset = offset

    def now(self, tz=None):
        return datetime.now(tz) + self.offset
