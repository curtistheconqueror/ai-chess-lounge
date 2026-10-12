"""Hosted (invite-only) mode: sign-in, invites, ownership isolation and live tickets."""

import asyncio
import time
from pathlib import Path

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient
from lounge_api import hosted_auth
from lounge_api.hosted_auth import HostedSettings, InvalidToken, TokenVerifier
from lounge_api.main import create_app
from lounge_api.manager import GameManager
from lounge_api.persistence import DatabaseStore
from starlette.websockets import WebSocketDisconnect
from test_manager import FakeEngine

SUPABASE = "https://abcdefghijklmnopqrst.supabase.co"
ORIGIN = "https://lounge.example.com"
ADMIN = "owner@example.com"
ACCOUNTS = {
    "token-admin": ("11111111-1111-1111-1111-111111111111", ADMIN),
    "token-bob": ("22222222-2222-2222-2222-222222222222", "bob@example.com"),
    "token-carol": ("33333333-3333-3333-3333-333333333333", "carol@example.com"),
    "token-bob-other-account": ("44444444-4444-4444-4444-444444444444", "bob@example.com"),
}


def hosted_env(monkeypatch, **overrides):
    values = {
        "LOUNGE_DEPLOYMENT": "hosted",
        "LOUNGE_HOSTED_MODE": "1",
        "SUPABASE_URL": SUPABASE,
        "SUPABASE_PUBLISHABLE_KEY": "sb_publishable_test",
        "LOUNGE_PUBLIC_ORIGIN": ORIGIN,
        "LOUNGE_ADMIN_EMAILS": f" {ADMIN.upper()} ",
        "DATABASE_URL": "postgresql+asyncpg://user@db.invalid/postgres",
        **overrides,
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)


def build_hosted(tmp_path: Path, monkeypatch, **env):
    database = f"sqlite+aiosqlite:///{tmp_path / 'hosted.db'}"
    # Hosted startup only verifies a migrated schema; build it the local way first.
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
    manager = GameManager(engine=FakeEngine(), store=DatabaseStore(database))
    return TestClient(create_app(manager), base_url=ORIGIN)


@pytest.fixture
def hosted(tmp_path: Path, monkeypatch):
    with build_hosted(tmp_path, monkeypatch) as client:
        yield client


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def invite(client, email, role="player"):
    response = client.put(
        f"/api/admin/members/{email}", json={"role": role}, headers=auth("token-admin")
    )
    assert response.status_code == 204, response.text


def new_game(client, token, **extra):
    return client.post(
        "/api/games", json={"initial_time_ms": 600_000, **extra}, headers=auth(token)
    )


@pytest.mark.parametrize(
    "name,value",
    [
        ("SUPABASE_URL", ""),
        ("SUPABASE_URL", "http://abcdefghijklmnopqrst.supabase.co"),
        ("SUPABASE_PUBLISHABLE_KEY", ""),
        ("SUPABASE_PUBLISHABLE_KEY", "sb_secret_never"),
        ("LOUNGE_PUBLIC_ORIGIN", "http://lounge.example.com"),
        ("LOUNGE_PUBLIC_ORIGIN", "https://lounge.example.com/app"),
        ("LOUNGE_ADMIN_EMAILS", ""),
        ("LOUNGE_ADMIN_EMAILS", "not-an-email"),
        ("DATABASE_URL", "sqlite+aiosqlite:///x.db"),
        ("LOUNGE_AUTH_PROVIDERS", "facebook"),
        ("LOUNGE_MAX_LIVE_GAMES", "0"),
    ],
)
def test_hosted_startup_fails_closed_on_incomplete_configuration(
    monkeypatch, tmp_path, name, value
):
    hosted_env(monkeypatch, **{name: value})
    with pytest.raises(RuntimeError, match="Hosted startup refused"):
        HostedSettings.from_environment()
    manager = GameManager(
        engine=FakeEngine(), store=DatabaseStore(f"sqlite+aiosqlite:///{tmp_path / 'x.db'}")
    )
    with pytest.raises(RuntimeError):
        create_app(manager)
    assert not (tmp_path / "x.db").exists()


def test_public_paths_and_sign_in_requirement(hosted):
    assert hosted.get("/api/health").status_code == 200
    config = hosted.get("/api/auth/config").json()
    assert config == {
        "mode": "hosted",
        "supabase_url": SUPABASE,
        "publishable_key": "sb_publishable_test",
        "providers": ["email", "google", "github"],
    }
    for path in ("/api/games", "/api/live-match", "/api/table-settings", "/api/auth/me"):
        assert hosted.get(path).status_code in {401, 405}
    assert hosted.get("/api/live-match", headers=auth("forged")).status_code == 401
    # Local-only features are not part of the hosted release, signed in or not.
    for path in (
        "/api/runner-sessions",
        "/api/experiments",
        "/api/leaderboards",
        "/docs",
        "/openapi.json",
        "/api/player-adapters/reliability",
    ):
        assert hosted.get(path, headers=auth("token-admin")).status_code == 404, path


def test_invite_only_admin_bootstrap_and_revocation(hosted):
    me = hosted.get("/api/auth/me", headers=auth("token-admin")).json()
    assert me == {"mode": "hosted", "email": ADMIN, "role": "admin"}
    assert hosted.get("/api/auth/me", headers=auth("token-bob")).status_code == 403
    invite(hosted, "Bob@Example.com")
    assert hosted.get("/api/auth/me", headers=auth("token-bob")).json()["role"] == "player"
    # Players cannot manage the list; configured admins cannot be revoked or demoted.
    assert hosted.get("/api/admin/members", headers=auth("token-bob")).status_code == 403
    assert (
        hosted.delete(f"/api/admin/members/{ADMIN}", headers=auth("token-admin")).status_code == 409
    )
    assert (
        hosted.put(
            f"/api/admin/members/{ADMIN}", json={"role": "player"}, headers=auth("token-admin")
        ).status_code
        == 409
    )
    members = {
        m["email"]: m for m in hosted.get("/api/admin/members", headers=auth("token-admin")).json()
    }
    assert members["bob@example.com"]["signed_in"] and members[ADMIN]["configured_admin"]
    # A second account presenting the same address is refused once one has bound.
    assert hosted.get("/api/auth/me", headers=auth("token-bob-other-account")).status_code == 403
    assert (
        hosted.delete("/api/admin/members/bob@example.com", headers=auth("token-admin")).status_code
        == 204
    )
    assert hosted.get("/api/auth/me", headers=auth("token-bob")).status_code == 403
    # Re-inviting reactivates and lets the address bind a new account.
    invite(hosted, "bob@example.com")
    assert hosted.get("/api/auth/me", headers=auth("token-bob-other-account")).status_code == 200


def test_each_player_has_a_private_table(hosted):
    invite(hosted, "bob@example.com")
    invite(hosted, "carol@example.com")
    bob = new_game(hosted, "token-bob")
    assert bob.status_code == 201, bob.text
    game = bob.json()
    # One live match per player; Carol's table is independent.
    assert new_game(hosted, "token-bob").status_code == 409
    carol = new_game(hosted, "token-carol")
    assert carol.status_code == 201
    assert hosted.get("/api/live-match", headers=auth("token-bob")).json()["id"] == game["id"]
    assert (
        hosted.get("/api/live-match", headers=auth("token-carol")).json()["id"]
        == carol.json()["id"]
    )
    # Carol can neither see nor act on Bob's game; it looks like it does not exist.
    for method, path, body in (
        ("get", f"/api/games/{game['id']}", None),
        ("get", f"/api/games/{game['id']}/events", None),
        ("post", f"/api/games/{game['id']}/moves", {"move": "e2e4", "position_version": 0}),
        ("post", f"/api/games/{game['id']}/abort", {}),
    ):
        response = (
            getattr(hosted, method)(path, json=body, headers=auth("token-carol"))
            if body is not None
            else getattr(hosted, method)(path, headers=auth("token-carol"))
        )
        assert response.status_code == 404, (path, response.text)
    moved = hosted.post(
        f"/api/games/{game['id']}/moves",
        json={"move": "e2e4", "position_version": 0},
        headers=auth("token-bob"),
    )
    assert moved.status_code == 200, moved.text
    # The admin can open any game (support and moderation).
    assert hosted.get(f"/api/games/{game['id']}", headers=auth("token-admin")).status_code == 200
    # Table settings are per player.
    settings = hosted.get("/api/table-settings", headers=auth("token-bob")).json()
    saved = hosted.put(
        "/api/table-settings",
        headers=auth("token-bob"),
        json={"revision": 0, "settings": {**settings["settings"], "time_control": "10+5"}},
    )
    assert saved.status_code == 200
    assert hosted.get("/api/table-settings", headers=auth("token-carol")).json()["revision"] == 0


def test_hosted_seats_and_provider_actions_are_limited(hosted):
    invite(hosted, "bob@example.com")
    scripted = {
        "adapter_id": "scripted",
        "display_name": "Bot",
        "provider": "local",
        "model": "deterministic-v1",
        "connection_mode": "local",
    }
    rejected = new_game(hosted, "token-bob", black_player=scripted)
    assert rejected.status_code == 422 and "human and Stockfish" in rejected.json()["detail"]
    adapters = hosted.get("/api/player-adapters", headers=auth("token-bob")).json()["adapters"]
    assert {item["adapter_id"] for item in adapters} <= {"human", "stockfish"}
    game = new_game(hosted, "token-bob").json()
    for action in ("consultations", "human-suggestion", "retry-agent"):
        response = hosted.post(
            f"/api/games/{game['id']}/{action}", json={}, headers=auth("token-bob")
        )
        assert response.status_code == 404, action


def test_live_games_are_capped(tmp_path, monkeypatch):
    with build_hosted(tmp_path, monkeypatch, LOUNGE_MAX_LIVE_GAMES="1") as client:
        invite(client, "bob@example.com")
        invite(client, "carol@example.com")
        assert new_game(client, "token-bob").status_code == 201
        full = new_game(client, "token-carol")
        assert full.status_code == 503 and "busy" in full.json()["detail"]


def test_live_socket_needs_a_one_time_ticket_from_the_owner(hosted):
    invite(hosted, "bob@example.com")
    invite(hosted, "carol@example.com")
    game = new_game(hosted, "token-bob").json()
    url = f"/ws/games/{game['id']}"
    with pytest.raises(WebSocketDisconnect):
        with hosted.websocket_connect(url, headers={"origin": ORIGIN}) as socket:
            socket.receive_json()
    ticket = hosted.post("/api/ws-ticket", headers=auth("token-bob")).json()["ticket"]
    with pytest.raises(WebSocketDisconnect):  # wrong origin
        with hosted.websocket_connect(
            f"{url}?ticket={ticket}", headers={"origin": "https://evil.example"}
        ) as socket:
            socket.receive_json()
    ticket = hosted.post("/api/ws-ticket", headers=auth("token-bob")).json()["ticket"]
    with hosted.websocket_connect(f"{url}?ticket={ticket}", headers={"origin": ORIGIN}) as socket:
        assert socket.receive_json()["payload"]["id"] == game["id"]
    with pytest.raises(WebSocketDisconnect):  # single use
        with hosted.websocket_connect(
            f"{url}?ticket={ticket}", headers={"origin": ORIGIN}
        ) as socket:
            socket.receive_json()
    carol = hosted.post("/api/ws-ticket", headers=auth("token-carol")).json()["ticket"]
    with pytest.raises(WebSocketDisconnect):  # not her game
        with hosted.websocket_connect(
            f"{url}?ticket={carol}", headers={"origin": ORIGIN}
        ) as socket:
            socket.receive_json()


def test_ticket_expires(monkeypatch):
    tickets = hosted_auth.LiveTickets()
    identity = hosted_auth.Identity(user_id="u", email="a@b.co", role="player")
    ticket = tickets.issue(identity)
    real = time.monotonic
    monkeypatch.setattr(
        hosted_auth.time, "monotonic", lambda: real() + hosted_auth.TICKET_SECONDS + 1
    )
    assert tickets.redeem(ticket) is None


class FakeKeys:
    def __init__(self, key):
        self.key = key

    def get_signing_key_from_jwt(self, token):
        return self


def test_token_verifier_checks_signature_audience_issuer_and_expiry(monkeypatch):
    hosted_env(monkeypatch)
    settings = HostedSettings.from_environment()
    private = ec.generate_private_key(ec.SECP256R1())
    verifier = TokenVerifier(settings)
    verifier._keys = FakeKeys(private.public_key())
    now = int(time.time())
    good = {
        "sub": "user-1",
        "email": "Bob@Example.com",
        "role": "authenticated",
        "aud": "authenticated",
        "iss": settings.issuer,
        "exp": now + 600,
        "amr": [{"method": "otp", "timestamp": now}],
    }

    def token(claims, key=private):
        return jwt.encode(claims, key, algorithm="ES256")

    assert asyncio.run(verifier.verify(token(good))) == ("user-1", "bob@example.com")
    confirmed = {**good, "amr": [{"method": "password"}], "user_metadata": {"email_verified": True}}
    assert asyncio.run(verifier.verify(token(confirmed)))[1] == "bob@example.com"
    assert (
        asyncio.run(verifier.verify(token({**good, "amr": [{"method": "oauth"}]})))[0] == "user-1"
    )
    other = ec.generate_private_key(ec.SECP256R1())
    for bad, key in (
        ({**good, "aud": "anon"}, private),
        ({**good, "iss": "https://zzzzzzzzzzzzzzzzzzzz.supabase.co/auth/v1"}, private),
        ({**good, "exp": now - 120}, private),
        ({**good, "is_anonymous": True}, private),
        ({**good, "role": "anon"}, private),
        ({k: v for k, v in good.items() if k != "email"}, private),
        (good, other),
        # A password account whose address was never confirmed cannot claim an invite.
        ({**good, "amr": [{"method": "password", "timestamp": now}]}, private),
        ({**good, "amr": [], "user_metadata": {"email_verified": False}}, private),
    ):
        with pytest.raises(InvalidToken):
            asyncio.run(verifier.verify(token(bad, key)))
    with pytest.raises(InvalidToken):
        asyncio.run(verifier.verify(jwt.encode(good, "s" * 48, algorithm="HS256")))


def test_existing_local_database_gains_the_owner_column(tmp_path, monkeypatch):
    """A local database at 0013 keeps working: games load and the revision advances."""
    import sqlite3

    monkeypatch.setenv("LOUNGE_DEPLOYMENT", "local")
    monkeypatch.setenv("LOUNGE_HOSTED_MODE", "0")
    path = tmp_path / "old.db"
    store = DatabaseStore(f"sqlite+aiosqlite:///{path}")

    async def build_old():
        await store.initialize()
        await store.close()

    asyncio.run(build_old())
    with sqlite3.connect(path) as db:  # rewind to the 0013 shape
        db.execute("DROP INDEX ix_matches_owner_id")
        db.execute("ALTER TABLE matches DROP COLUMN owner_id")
        db.execute("UPDATE alembic_version SET version_num = '0013_table_settings'")
    manager = GameManager(engine=FakeEngine(), store=DatabaseStore(f"sqlite+aiosqlite:///{path}"))
    with TestClient(create_app(manager)) as client:
        game = client.post("/api/games", json={"initial_time_ms": 600_000}).json()
        assert client.get(f"/api/games/{game['id']}").status_code == 200
        assert client.get("/api/live-match").json()["id"] == game["id"]
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT version_num FROM alembic_version").fetchall() == [
            ("0014_hosted_members",)
        ]


def test_hosted_tables_need_a_person_and_a_quick_engine(hosted):
    invite(hosted, "bob@example.com")
    engine = {
        "adapter_id": "stockfish",
        "display_name": "Stockfish",
        "provider": "stockfish",
        "model": "stockfish",
        "connection_mode": "local",
    }
    both = new_game(
        hosted,
        "token-bob",
        white_player={**engine, "settings": {"target_elo": 3200}},
        black_player={**engine, "settings": {"target_elo": 3200}},
    )
    assert both.status_code == 422 and "person" in both.json()["detail"]
    slow = new_game(hosted, "token-bob", engine_move_time_ms=10_000)
    assert slow.status_code == 422 and "one second" in slow.json()["detail"]
    game = new_game(hosted, "token-bob").json()
    # Swapping the human seat for a second engine is refused too.
    takeover = hosted.post(
        f"/api/games/{game['id']}/seats/white",
        headers=auth("token-bob"),
        json={
            "player": {**engine, "settings": {"target_elo": 1600}},
            "expected_revision": game["revision"],
        },
    )
    assert takeover.status_code == 422


def test_rate_body_and_header_limits(hosted, monkeypatch):
    invite(hosted, "bob@example.com")
    huge = hosted.post(
        "/api/games",
        headers={**auth("token-bob"), "content-type": "application/json"},
        content=b"{" + b" " * (hosted_auth.MAX_BODY_BYTES + 10) + b"}",
    )
    assert huge.status_code == 413
    monkeypatch.setattr(hosted_auth, "CREATE_LIMIT_PER_MINUTE", 2)
    codes = [new_game(hosted, "token-bob").status_code for _ in range(3)]
    assert codes[-1] == 429, codes
    page = hosted.get("/api/health")
    assert page.headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in page.headers["content-security-policy"]
    assert page.headers["strict-transport-security"].startswith("max-age=")


def test_open_socket_closes_when_access_ends_and_sockets_are_capped(tmp_path, monkeypatch):
    from lounge_api import main as main_module

    monkeypatch.setattr(main_module, "SOCKET_RECHECK_SECONDS", 0.2)
    with build_hosted(tmp_path, monkeypatch) as client:
        invite(client, "bob@example.com")
        game = new_game(client, "token-bob").json()
        url = f"/ws/games/{game['id']}"

        def connect():
            ticket = client.post("/api/ws-ticket", headers=auth("token-bob")).json()["ticket"]
            return client.websocket_connect(f"{url}?ticket={ticket}", headers={"origin": ORIGIN})

        with connect() as socket:
            socket.receive_json()
            assert (
                client.delete(
                    "/api/admin/members/bob@example.com", headers=auth("token-admin")
                ).status_code
                == 204
            )
            with pytest.raises(WebSocketDisconnect) as closed:
                for _ in range(20):
                    socket.receive_json()
            assert closed.value.code == 1008
        invite(client, "bob@example.com")
        monkeypatch.setattr(main_module, "HOSTED_SOCKETS_PER_PLAYER", 1)
        with connect() as first:
            first.receive_json()
            with pytest.raises(WebSocketDisconnect):
                with connect() as second:
                    second.receive_json()


def test_admin_binding_can_be_reset_for_one_deploy(tmp_path, monkeypatch):
    with build_hosted(tmp_path, monkeypatch) as client:
        assert client.get("/api/auth/me", headers=auth("token-admin")).status_code == 200
    ACCOUNTS["token-admin-recreated"] = ("55555555-5555-5555-5555-555555555555", ADMIN)
    try:
        monkeypatch.setenv("LOUNGE_ADMIN_REBIND", "1")
        database = f"sqlite+aiosqlite:///{tmp_path / 'hosted.db'}"
        manager = GameManager(engine=FakeEngine(), store=DatabaseStore(database))
        with TestClient(create_app(manager), base_url=ORIGIN) as client:
            assert (
                client.get("/api/auth/me", headers=auth("token-admin-recreated")).status_code == 200
            )
    finally:
        del ACCOUNTS["token-admin-recreated"]
