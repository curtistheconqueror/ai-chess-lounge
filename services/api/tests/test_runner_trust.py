from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from lounge_api.adapters import AdapterError
from lounge_api.manager import GameManager
from lounge_api.models import (
    CreateGameRequest,
    OpponentKind,
    RunnerPairingCreate,
    RunnerProposalSubmission,
)
from lounge_api.persistence import DatabaseStore, RunnerTrustError
from lounge_api.player_protocol import MoveProposal, MoveRequest
from lounge_api.remote_runner import RemoteRunnerBroker, RunnerAuthenticationError

SECRET = b"stage5e-durable-trust-secret-value!"


async def paired(store, **limits):
    broker = RemoteRunnerBroker(store, secret=SECRET)
    await store.initialize()
    pair = await broker.create_pairing(
        RunnerPairingCreate(
            display_name="Trust test", provider="Independent", model="test", **limits
        )
    )
    credentials = await broker.claim_pairing(pair.pairing_id, pair.pairing_code)
    return broker, credentials


def request(match_id="match-a", color="white"):
    return MoveRequest(
        match_id=match_id,
        position_version=0,
        color=color,
        fen="start",
        moves_uci=[],
        pgn="*",
        legal_moves=["e2e4"],
        remaining_ms=5000,
        move_deadline_ms=5000,
        division="legal_assist",
    )


def signed(credentials, delivery):
    req = delivery.request
    proposal = MoveProposal(
        request_id=req.request_id,
        match_id=req.match_id,
        position_version=req.position_version,
        move="e2e4" if req.color == "white" else "e7e5",
    )
    key = "trust-proposal-1"
    return RunnerProposalSubmission(
        proposal=proposal,
        idempotency_key=key,
        signature=RemoteRunnerBroker.proposal_signature(
            credentials.signing_key, delivery.delivery_id, key, proposal
        ),
    )


def test_reconnect_replays_same_delivery_and_revoke_interrupts_wait(tmp_path):
    async def run():
        store = DatabaseStore(f"sqlite+aiosqlite:///{tmp_path / 'trust.db'}")
        broker, creds = await paired(store)
        turn = asyncio.create_task(broker.request_turn(request(), creds.player))
        try:
            first = await broker.next_turn(creds.runner_token, wait_ms=1000)
            second = await broker.next_turn(creds.runner_token, wait_ms=0)
            assert first == second and first is not None
            assert (await store.runner_grant(creds.session_id))["turns_dispatched"] == 1
            await broker.revoke(creds.session_id)
            with pytest.raises(AdapterError, match="revoked"):
                await turn
            with pytest.raises(RunnerAuthenticationError, match="revoked"):
                await broker.submit_proposal(
                    creds.runner_token, first.delivery_id, signed(creds, first)
                )
            await broker.revoke(creds.session_id)  # idempotent
            events = await store.runner_audit(creds.session_id)
            assert [e["kind"] for e in events] == [
                "session.claimed",
                "match.authorized",
                "turn.dispatched",
                "session.revoked",
            ]
            assert creds.runner_token not in str(events) and creds.signing_key not in str(events)
        finally:
            turn.cancel()
            await asyncio.gather(turn, return_exceptions=True)
            await broker.close()
            await store.close()

    asyncio.run(run())


def test_grant_survives_restart_and_rejects_other_match_seat_and_limit(tmp_path):
    async def run():
        url = f"sqlite+aiosqlite:///{tmp_path / 'restart.db'}"
        store = DatabaseStore(url)
        broker, creds = await paired(store, max_turns=1)
        now = datetime.now(UTC)
        await store.reserve_runner_turn(creds.session_id, "match-a", "white", now=now)
        await broker.close()
        await store.close()
        store = DatabaseStore(url)
        await store.initialize()
        try:
            for match_id, color, reason in [
                ("match-b", "white", "different"),
                ("match-a", "black", "different"),
                ("match-a", "white", "limit"),
            ]:
                with pytest.raises(RunnerTrustError, match=reason):
                    await store.reserve_runner_turn(creds.session_id, match_id, color, now=now)
            assert (await store.runner_grant(creds.session_id))["turns_dispatched"] == 1
            # Last permitted dispatch remains submittable at the cap.
            await store.check_runner_grant(creds.session_id, "match-a", "white", now=now)
            with pytest.raises(RunnerTrustError, match="expired"):
                await store.check_runner_grant(
                    creds.session_id, "match-a", "white", now=now + timedelta(days=2)
                )
        finally:
            await store.close()

    asyncio.run(run())


def test_concurrent_first_match_binding_has_exactly_one_winner(tmp_path):
    async def run():
        url = f"sqlite+aiosqlite:///{tmp_path / 'concurrent.db'}"
        first = DatabaseStore(url)
        broker, creds = await paired(first)
        second = DatabaseStore(url)
        await second.initialize()
        try:
            results = await asyncio.gather(
                *[
                    store.reserve_runner_turn(
                        creds.session_id, match, "white", now=datetime.now(UTC)
                    )
                    for store, match in [(first, "match-a"), (second, "match-b")]
                ],
                return_exceptions=True,
            )
            assert sum(isinstance(r, dict) for r in results) == 1
            assert sum(isinstance(r, RunnerTrustError) for r in results) == 1
            assert len(await first.runner_audit(creds.session_id)) == 3
        finally:
            await broker.close()
            await first.close()
            await second.close()

    asyncio.run(run())


def test_revoke_between_receipt_and_commit_cannot_change_board(tmp_path):
    async def run():
        store = DatabaseStore(f"sqlite+aiosqlite:///{tmp_path / 'commit.db'}")
        broker, creds = await paired(store)
        manager = GameManager(store=store, remote_runners=broker, schedule_timeouts=False)
        await manager.start()
        original = store.record_move

        async def revoke_before_commit(game, move, events, **kwargs):
            if move.actor.startswith("remote_runner:"):
                await broker.revoke(creds.session_id)
            return await original(game, move, events, **kwargs)

        store.record_move = revoke_before_commit
        try:
            game = await manager.create(
                CreateGameRequest(opponent=OpponentKind.HUMAN, black_player=creds.player)
            )
            human = asyncio.create_task(manager.make_human_move(game.id, "e2e4", 0))
            delivery = await broker.next_turn(creds.runner_token, wait_ms=1000)
            assert delivery is not None
            await broker.submit_proposal(
                creds.runner_token, delivery.delivery_id, signed(creds, delivery)
            )
            await human
            restored = await store.load_game(game.id)
            assert restored is not None
            assert [m.uci for m in restored.moves] == ["e2e4"]
            assert restored.lifecycle.value == "paused"
            assert not any(
                e["kind"] == "move.committed" for e in await store.runner_audit(creds.session_id)
            )
        finally:
            await manager.close()

    asyncio.run(run())


def test_reset_generation_cannot_reuse_grant(tmp_path):
    async def run():
        store = DatabaseStore(f"sqlite+aiosqlite:///{tmp_path / 'reset.db'}")
        broker, creds = await paired(store)
        manager = GameManager(store=store, remote_runners=broker, schedule_timeouts=False)
        await manager.start()
        try:
            game = await manager.create(CreateGameRequest(opponent=OpponentKind.HUMAN))
            await store.reserve_runner_turn(
                creds.session_id, game.id, "white", now=datetime.now(UTC)
            )
            await manager.reset(game.id)
            with pytest.raises(RunnerTrustError, match="different"):
                await store.check_runner_grant(
                    creds.session_id, game.id, "white", now=datetime.now(UTC)
                )
        finally:
            await manager.close()

    asyncio.run(run())


@pytest.mark.parametrize("action", ["pause", "reset", "abort", "pause_resume"])
def test_other_worker_lifecycle_change_blocks_delivery_and_submission(tmp_path, action):
    async def run():
        url = f"sqlite+aiosqlite:///{tmp_path / 'lifecycle.db'}"
        store = DatabaseStore(url)
        broker, creds = await paired(store)
        manager = GameManager(store=store, remote_runners=broker, schedule_timeouts=False)
        other = GameManager(store=DatabaseStore(url), schedule_timeouts=False)
        await manager.start()
        await other.start()
        task = None
        try:
            game = await manager.create(CreateGameRequest(opponent=OpponentKind.HUMAN))
            task = asyncio.create_task(broker.request_turn(request(game.id), creds.player))
            delivery = await broker.next_turn(creds.runner_token, wait_ms=1000)
            assert delivery is not None
            if action == "pause_resume":
                await other.pause(game.id)
                await other.resume(game.id)
            else:
                await getattr(other, action)(game.id)
            with pytest.raises(RunnerAuthenticationError):
                await broker.next_turn(creds.runner_token, wait_ms=0)
            with pytest.raises(RunnerAuthenticationError):
                await broker.submit_proposal(
                    creds.runner_token, delivery.delivery_id, signed(creds, delivery)
                )
        finally:
            if task:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            await other.close()
            await manager.close()

    asyncio.run(run())


def test_stale_request_after_reset_does_not_consume_authorization(tmp_path):
    async def run():
        store = DatabaseStore(f"sqlite+aiosqlite:///{tmp_path / 'stale.db'}")
        broker, creds = await paired(store)
        manager = GameManager(store=store, remote_runners=broker, schedule_timeouts=False)
        await manager.start()
        try:
            game = await manager.create(CreateGameRequest(opponent=OpponentKind.HUMAN))
            await manager.reset(game.id)
            with pytest.raises(AdapterError, match="stale"):
                await broker.request_turn(request(game.id), creds.player)
            assert await store.runner_grant(creds.session_id) is None
            assert [e["kind"] for e in await store.runner_audit(creds.session_id)] == [
                "session.claimed"
            ]
        finally:
            await manager.close()

    asyncio.run(run())


def test_match_authorization_expires_without_extending_on_heartbeat(tmp_path):
    async def run():
        store = DatabaseStore(f"sqlite+aiosqlite:///{tmp_path / 'expiry.db'}")
        broker, creds = await paired(store, match_ttl_ms=1000)
        now = datetime.now(UTC)
        grant = await store.reserve_runner_turn(creds.session_id, "match-a", "white", now=now)
        await broker.heartbeat(creds.runner_token)
        assert (await store.runner_grant(creds.session_id))["expires_at"] == grant["expires_at"]
        with pytest.raises(RunnerTrustError, match="authorization has expired"):
            await store.check_runner_grant(
                creds.session_id, "match-a", "white", now=now + timedelta(seconds=2)
            )
        await broker.close()
        await store.close()

    asyncio.run(run())
