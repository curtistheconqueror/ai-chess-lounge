import asyncio
import json

import pytest
from fastapi.testclient import TestClient
from lounge_api.deployment_guard import require_local_runtime
from lounge_api.main import create_app
from lounge_api.manager import GameManager
from lounge_api.persistence import DatabaseStore
from lounge_api.private_network import NetworkSettings, PrivateNetworkMiddleware
from test_manager import FakeEngine


@pytest.fixture
def direct(monkeypatch):
    monkeypatch.setenv("LOUNGE_NETWORK_MODE", "tailscale")
    monkeypatch.setenv("LOUNGE_BIND_HOST", "100.100.10.1")
    monkeypatch.setenv("LOUNGE_PRIVATE_PEERS", "100.100.10.2")
    monkeypatch.setenv("LOUNGE_PRIVATE_ORIGINS", "http://100.100.10.1:8000")
    return NetworkSettings.from_environment()


@pytest.mark.parametrize(
    "name,value",
    [
        ("LOUNGE_NETWORK_MODE", "public"),
        ("LOUNGE_BIND_HOST", "0.0.0.0"),
        ("LOUNGE_BIND_HOST", "192.168.1.2"),
        ("LOUNGE_PRIVATE_PEERS", ""),
        ("LOUNGE_PRIVATE_PEERS", "100.64.0.0/10"),
        ("LOUNGE_PRIVATE_PEERS", "8.8.8.8"),
        ("LOUNGE_PRIVATE_ORIGINS", "*"),
        ("LOUNGE_PRIVATE_ORIGINS", "null"),
        ("LOUNGE_PRIVATE_ORIGINS", "https://example.com"),
        ("LOUNGE_PRIVATE_ORIGINS", "https://host.tail.ts.net/path"),
        ("LOUNGE_PRIVATE_ORIGINS", "https://user@host.tail.ts.net"),
        ("LOUNGE_PRIVATE_ORIGINS", "https://host.tail.ts.net:bad"),
    ],
)
def test_private_configuration_fails_closed(direct, monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(ValueError):
        NetworkSettings.from_environment()


def test_default_is_loopback_and_hosted_guard_stays_on(monkeypatch):
    for key in ("LOUNGE_NETWORK_MODE", "LOUNGE_BIND_HOST", "LOUNGE_PORT"):
        monkeypatch.delenv(key, raising=False)
    assert NetworkSettings.from_environment().host == "127.0.0.1"
    monkeypatch.setenv("LOUNGE_BIND_HOST", "0.0.0.0")
    with pytest.raises(ValueError):
        NetworkSettings.from_environment()
    monkeypatch.setenv("LOUNGE_HOSTED_MODE", "1")
    with pytest.raises(RuntimeError, match="Hosted startup"):
        require_local_runtime()


def dispatch(settings, peer, path="/api/games/id", origin=None, extra=(), kind="http"):
    async def run():
        sent = []

        async def target(scope, receive, send):
            await send(
                {"type": "websocket.accept"}
                if kind == "websocket"
                else {
                    "type": "http.response.start",
                    "status": 200,
                }
            )

        async def receive():
            return {"type": "http.request", "body": b""}

        async def send(message):
            sent.append(message)

        headers = [(b"host", settings.origins[0].split("//")[1].encode())]
        if origin is not None:
            headers.append((b"origin", origin.encode()))
        headers.extend(extra)
        await PrivateNetworkMiddleware(target, settings)(
            {"type": kind, "client": (peer, 1234), "path": path, "headers": headers},
            receive,
            send,
        )
        return sent[0]

    return asyncio.run(run())


def test_direct_peer_host_and_origin_are_independent(direct):
    assert dispatch(direct, "100.100.10.2")["status"] == 200
    for peer in ("127.0.0.1", "192.168.1.2", "8.8.8.8", "100.100.10.3"):
        assert (
            dispatch(direct, peer, extra=[(b"x-forwarded-for", b"100.100.10.2")])["status"] == 403
        )
    for origin in ("https://evil.example", "http://100.100.10.2:8000", "null"):
        assert dispatch(direct, "100.100.10.2", origin=origin)["status"] == 403
    assert dispatch(direct, "100.100.10.2", extra=[(b"host", b"evil.example")])["status"] == 403
    assert dispatch(direct, "100.100.10.2", kind="websocket")["code"] == 1008
    assert (
        dispatch(direct, "100.100.10.2", kind="websocket", origin=direct.origins[0])["type"]
        == "websocket.accept"
    )


@pytest.mark.parametrize(
    "path",
    [
        "/api/runner-pairings",
        "/api/runner-pairings/id/claim",
        "/api/runner-sessions",
        "/api/experiments",
        "/api/experiment-runs/id/control",
        "/api/ready",
        "/api/credentials",
        "/api/config",
        "/openapi.json",
        "/docs",
        "/ws/runners",
    ],
)
def test_private_mode_has_no_runner_credential_or_admin_routes(direct, path):
    assert dispatch(direct, "100.100.10.2", path=path)["status"] == 403


def test_serve_only_trusts_selected_logins_from_loopback(monkeypatch):
    monkeypatch.setenv("LOUNGE_NETWORK_MODE", "tailscale-serve")
    monkeypatch.setenv("LOUNGE_BIND_HOST", "127.0.0.1")
    monkeypatch.setenv("LOUNGE_PRIVATE_ORIGINS", "https://chess.tail.ts.net")
    monkeypatch.setenv("LOUNGE_TAILSCALE_USERS", "host@example.com,friend@example.com")
    settings = NetworkSettings.from_environment()
    login = [(b"tailscale-user-login", b"friend@example.com")]
    assert dispatch(settings, "127.0.0.1", extra=login)["status"] == 200
    assert dispatch(settings, "100.100.10.2", extra=login)["status"] == 403
    assert dispatch(settings, "127.0.0.1")["status"] == 403
    assert (
        dispatch(settings, "127.0.0.1", extra=[(b"tailscale-user-login", b"other@example.com")])[
            "status"
        ]
        == 403
    )
    monkeypatch.setenv("LOUNGE_TAILSCALE_USERS", "a@example.com,b@example.com,c@example.com")
    with pytest.raises(ValueError):
        NetworkSettings.from_environment()


def test_private_app_cors_and_provider_keys_stay_server_side(direct, monkeypatch, tmp_path):
    marker = "test-only-private-provider-canary"
    monkeypatch.setenv("OPENAI_API_KEY", marker)
    manager = GameManager(
        engine=FakeEngine(), store=DatabaseStore(f"sqlite+aiosqlite:///{tmp_path / 'private.db'}")
    )
    with TestClient(
        create_app(manager), base_url=direct.origins[0], client=(direct.peers[0], 1234)
    ) as c:
        preflight = c.options(
            "/api/games",
            headers={
                "Origin": direct.origins[0],
                "Access-Control-Request-Method": "POST",
            },
        )
        assert preflight.status_code == 200
        assert preflight.headers["access-control-allow-origin"] == direct.origins[0]
        assert (
            c.options("/api/games", headers={"Origin": "https://evil.example"}).status_code == 403
        )
        created = c.post("/api/games", json={"opponent": "human", "start_paused": True})
        assert created.status_code == 201
        game = created.json()
        for path in (
            "/api/player-adapters",
            "/api/health",
            f"/api/games/{game['id']}",
            f"/api/games/{game['id']}/events",
        ):
            response = c.get(path)
            assert response.status_code == 200
            assert marker not in response.text
        assert marker not in json.dumps(game)
        assert c.post("/api/runner-pairings", json={}).status_code == 403
        with c.websocket_connect(
            f"ws://100.100.10.1:8000/ws/games/{game['id']}",
            headers={"Origin": direct.origins[0]},
        ) as ws:
            assert marker not in json.dumps(ws.receive_json())


def test_launcher_check_does_not_listen_and_run_preserves_real_peer(direct, monkeypatch, capsys):
    from lounge_api import serve

    calls = []
    monkeypatch.setattr(serve.uvicorn, "run", lambda *args, **kwargs: calls.append(kwargs))
    monkeypatch.setattr("sys.argv", ["serve", "--check"])
    serve.main()
    assert calls == []
    assert "Valid tailscale configuration" in capsys.readouterr().out
    monkeypatch.setattr("sys.argv", ["serve"])
    serve.main()
    assert calls == [{"host": direct.host, "port": 8000, "proxy_headers": False}]
