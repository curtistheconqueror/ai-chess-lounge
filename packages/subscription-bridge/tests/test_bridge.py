from __future__ import annotations

import asyncio
import json
import os
import sys
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from ai_chess_lounge_runner import RunnerClient
from ai_chess_lounge_runner.models import MoveRequest, TurnDelivery, proposal_for
from lounge_api.main import create_app
from lounge_api.manager import GameManager
from lounge_api.persistence import DatabaseStore
from lounge_subscription.bridge import read_game_status, run_match, validate_profile
from lounge_subscription.cli import parser
from lounge_subscription.codex import CodexProvider, parse_proposal
from lounge_subscription.process import BridgeError, child_environment, run_process


def delivery(version=0, match_id=None):
    return TurnDelivery(
        str(uuid4()),
        (datetime.now(UTC) + timedelta(seconds=30)).isoformat(),
        MoveRequest(
            str(uuid4()),
            match_id or str(uuid4()),
            version,
            "white",
            "board",
            (),
            "",
            None,
            30000,
            30000,
            "open_agentic",
            True,
        ),
    )


def fake_cli(tmp_path: Path) -> Path:
    executable = tmp_path / "fake-codex"
    executable.write_text(
        f"#!{sys.executable}\n"
        + """
import sys, json, os
args = sys.argv[1:]
if args == ['exec', '--help']:
    print('--output-schema --ignore-user-config --ephemeral --sandbox --skip-git-repo-check')
elif args == ['login', 'status']:
    print('Logged in using ChatGPT')
else:
    forbidden = ('OPENAI_API_KEY', 'CODEX_API_KEY', 'LOUNGE_PAIRING_CODE')
    assert not any(k in os.environ for k in forbidden)
    assert '--ignore-user-config' in args and '--ephemeral' in args
    assert 'forced_login_method="chatgpt"' in args
    assert args[args.index('--sandbox')+1] == 'read-only'
    assert 'dangerously-bypass' not in ' '.join(args)
    request = json.loads(sys.stdin.read().split('\\n', 1)[1])
    moves = ['f2f3', 'e7e5', 'g2g4', 'd8h4']
    print(json.dumps(dict(move=moves[len(request['moves_uci'])],
                          plan='Public plan', threat='', confidence=50)))
"""
    )
    executable.chmod(0o700)
    return executable


def test_two_official_cli_contract_fakes_complete_authoritative_game(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "never-inherit-secret")
    monkeypatch.setenv("CODEX_API_KEY", "never-inherit-secret")
    monkeypatch.setenv("LOUNGE_PAIRING_CODE", "never-inherit-secret")

    async def run():
        provider = CodexProvider("fixture-model", str(fake_cli(tmp_path)))
        assert (await provider.doctor())["subscription_login"]
        manager = GameManager(store=DatabaseStore(f"sqlite+aiosqlite:///{tmp_path}/bridge.db"))
        app = create_app(manager)
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8000"
            ) as http,
        ):
            clients = []
            for color in ["white", "black"]:
                result = await http.post(
                    "/api/runner-pairings",
                    json={
                        "display_name": f"CLI {color}",
                        "provider": "OpenAI",
                        "model": "fixture-model",
                        "connection_mode": "subscription_bridge",
                        "division": "open_agentic",
                        "move_timeout_ms": 20000,
                    },
                )
                assert result.status_code == 201, result.text
                pairing = result.json()
                client = await RunnerClient.claim(
                    str(http.base_url),
                    pairing_id=pairing["pairing_id"],
                    pairing_code=pairing["pairing_code"],
                    http_client=http,
                )
                validate_profile(client.credentials.player, "fixture-model")
                clients.append(client)
            result = await http.post(
                "/api/games",
                json={
                    "white_player": clients[0].credentials.player,
                    "black_player": clients[1].credentials.player,
                    "initial_time_ms": 60000,
                },
            )
            assert result.status_code == 201, result.text
            game_id = result.json()["id"]

            async def choose(turn, timeout):
                return await provider.choose_move(turn, timeout=timeout)

            async def status(match_id):
                return await read_game_status(http, str(http.base_url).rstrip("/"), match_id)

            async with asyncio.timeout(20):
                counts = await asyncio.gather(
                    *(run_match(c, choose, status, max_turns=2) for c in clients)
                )
            assert counts == [2, 2]
            game = (await http.get(f"/api/games/{game_id}")).json()
            assert game["status"] == "checkmate"
            assert game["result"] == "0-1"
            assert len(game["moves"]) == 4
            assert game["white_player"]["connection_mode"] == "subscription_bridge"
            assert "never-inherit-secret" not in json.dumps(game)
            assert "Qh4#" in game["pgn"]

    asyncio.run(run())


@pytest.mark.parametrize(
    "payload",
    [
        b"not json",
        b'{"move":"e2e4"}',
        json.dumps(dict(move="e2e4", plan="", threat="", confidence=True)).encode(),
        json.dumps(dict(move="e2e4", plan="", threat="", confidence=101)).encode(),
        json.dumps(dict(move="e2e4", plan="x" * 281, threat="", confidence=None)).encode(),
        json.dumps(
            dict(move="e2e4", plan="", threat="", confidence=None, reasoning="private")
        ).encode(),
        b'{"move":"e2e4","move":"d2d4","plan":"","threat":"","confidence":null}',
    ],
)
def test_reject_malformed_output_without_echo(payload):
    with pytest.raises(BridgeError, match="invalid move response"):
        parse_proposal(payload, delivery())


def test_environment_does_not_inherit_credentials(monkeypatch):
    for name in [
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "CODEX_API_KEY",
        "LOUNGE_RUNNER_TOKEN",
        "HTTP_PROXY",
        "LOUNGE_PAIRING_CODE",
        "CODEX_ACCESS_TOKEN",
    ]:
        monkeypatch.setenv(name, "secret")
        assert name not in child_environment()


@pytest.mark.parametrize("mode", ["timeout", "overflow", "cancel"])
def test_child_cleanup_and_sanitized_failures(tmp_path, mode):
    async def run():
        pidfile = tmp_path / "pid"
        source = (
            "import os,time,pathlib; "
            f"pathlib.Path({str(pidfile)!r}).write_text(str(os.getpid())); "
            + ("print('private-output'*10000, flush=True); " if mode == "overflow" else "")
            + "time.sleep(30)"
        )
        task = asyncio.create_task(
            run_process(
                [sys.executable, "-c", source],
                cwd=tmp_path,
                timeout=0.3 if mode == "timeout" else 5,
                output_limit=100,
            )
        )
        if mode == "cancel":
            for _ in range(100):
                if pidfile.exists():
                    break
                await asyncio.sleep(0.01)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            with pytest.raises(BridgeError) as caught:
                await task
            assert "private-output" not in str(caught.value)
        pid = int(pidfile.read_text())
        with pytest.raises(ProcessLookupError):
            os.kill(pid, 0)

    asyncio.run(run())


def test_one_match_scope_and_duplicate_delivery():
    async def run():
        first = delivery()
        other = delivery(1)
        turns = iter([first, first, other])
        proposed = []
        submitted = []

        class Client:
            async def heartbeat(self):
                return {}

            async def next_turn(self, **kwargs):
                return next(turns)

            async def submit(self, turn, proposal):
                submitted.append(proposal)

        async def choose(turn, timeout):
            proposed.append(turn)
            return proposal_for(turn, move="e2e4")

        async def status(_):
            return "active"

        with pytest.raises(BridgeError, match="another match"):
            await run_match(Client(), choose, status)
        assert len(proposed) == 1
        assert len(submitted) == 2
        assert submitted[0] is submitted[1]

    asyncio.run(run())


def test_profile_and_authorization_are_required():
    with pytest.raises(BridgeError):
        validate_profile({"connection_mode": "remote_runner"}, "model")
    with pytest.raises(SystemExit):
        parser().parse_args(["run", "--pairing-id", str(uuid4()), "--model", "model"])


def test_expired_turn_never_calls_provider():
    async def run():
        turn = replace(
            delivery(), expires_at=(datetime.now(UTC) - timedelta(seconds=1)).isoformat()
        )

        class Client:
            async def heartbeat(self):
                pass

            async def next_turn(self, **kwargs):
                return turn

        async def choose(*_):
            pytest.fail("expired turn reached model")

        async def status(_):
            return "active"

        with pytest.raises(BridgeError, match="already expired"):
            await run_match(Client(), choose, status)

    asyncio.run(run())


def test_diagnostic_categories_never_echo_provider_details():
    from lounge_subscription.process import diagnostic_hint

    for raw in [
        b"401 secret-token",
        b"429 secret-token",
        b"connection secret-token",
        b"invalid schema secret-token",
        b"private reasoning secret-token",
    ]:
        assert "secret-token" not in diagnostic_hint(raw)
        assert "private reasoning" not in diagnostic_hint(raw)


def test_doctor_rejects_api_auth_and_old_cli(tmp_path):
    executable = fake_cli(tmp_path)
    executable.write_text(
        executable.read_text().replace(
            "Logged in using ChatGPT", "Logged in using API key secret-key"
        )
    )
    provider = CodexProvider("model", str(executable))
    report = asyncio.run(provider.doctor())
    assert report["subscription_login"] is False
    assert "secret-key" not in json.dumps(report)
    executable.write_text(executable.read_text().replace("--ignore-user-config", "--old-config"))
    with pytest.raises(BridgeError, match="lacks required"):
        asyncio.run(provider.doctor())


def test_credential_free_proxy_routing_is_preserved(monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.example:8080")
    monkeypatch.setenv("NO_PROXY", "localhost,127.0.0.1")
    assert child_environment()["HTTPS_PROXY"] == "http://proxy.example:8080"
    assert child_environment()["NO_PROXY"] == "localhost,127.0.0.1"


@pytest.mark.parametrize(
    "proxy",
    [
        "http://user:secret@proxy.example",
        "https://proxy.example/?token=secret",
        "https://proxy.example/private-token",
        "https://proxy.example/#secret",
        "not-a-url",
        "http://[invalid",
    ],
)
def test_unsafe_proxy_values_are_not_inherited(monkeypatch, proxy):
    monkeypatch.setenv("HTTPS_PROXY", proxy)
    assert "HTTPS_PROXY" not in child_environment()


@pytest.mark.parametrize(
    "raw",
    [
        b"2026-10-02T22:03:37.429Z error sending request",
        b"trace_id=abcd429abcd401 connection reset",
        b"HTTP request failed; request_id=abc429xyz",
    ],
)
def test_diagnostic_digits_are_not_http_statuses(raw):
    from lounge_subscription.process import diagnostic_hint

    hint = diagnostic_hint(raw)
    assert "rate limiting" not in hint
    assert "authentication failure" not in hint
    assert "quota error" not in hint


@pytest.mark.parametrize(
    "raw, expected",
    [
        (b"unexpected status 429 Too Many Requests", "rate limiting"),
        (b"HTTP/1.1 401 Unauthorized", "authentication failure"),
        (b"status code: 403", "access denial"),
        (b'{"code":"usage_limit_reached"}', "quota error"),
    ],
)
def test_diagnostic_status_and_quota_categories_are_distinct(raw, expected):
    from lounge_subscription.process import diagnostic_hint

    assert expected in diagnostic_hint(raw)
