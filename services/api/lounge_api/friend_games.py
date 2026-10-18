"""Hosted friend games: the lobby (members and presence), challenges and seat rules.

Any active member may challenge any other. Accepting starts a game at once with
each seat owned by one account; clocks wait for each side's first move (30 s, or
the game is aborted). In a friend game a person may act only for their own side,
and pausing, resetting, re-seating and adjudicating are off (ADR0044).
"""

from __future__ import annotations

import asyncio
import secrets
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from .hosted_auth import HostedSettings, Identity, normalize_email
from .models import CreateGameRequest, MatchState, OpponentKind
from .player_protocol import PlayerConfiguration

FIRST_MOVE_WINDOW_MS = 30_000
CHALLENGE_MINUTES = 60
ONLINE_SECONDS = 45
ANSWERED_SECONDS = 120  # accepted/declined challenges stay visible to the challenger
# Actions that make no sense when two people own the two sides.
SOLO_ONLY_ACTIONS = {"pause", "resume", "reset", "seat", "adjudicate", "retry"}


class ChallengeCreate(BaseModel):
    opponent_email: str = Field(min_length=3, max_length=254)
    initial_time_ms: int = Field(ge=60_000, le=3_600_000)
    increment_ms: int = Field(ge=0, le=60_000)
    color: Literal["white", "black", "random"] = "random"


def display_name(email: str) -> str:
    """The part before the @, so friends see a name rather than a full address."""
    return email.split("@", 1)[0][:60] or "Player"


class FriendGames:
    def __init__(self, manager, settings: HostedSettings, creation_lock: asyncio.Lock):
        self.manager, self.settings, self.creation_lock = manager, settings, creation_lock

    @property
    def store(self):
        return self.manager.store

    # --- seat rules ---------------------------------------------------------------
    async def guard(
        self, identity: Identity | None, game_id: str, action: str, color: str | None = None
    ) -> None:
        """Raise unless this person may take this action in this (friend) game."""
        if identity is None:
            return
        game = await self.manager.get(game_id)
        if not game.friend_game:
            return
        mine = game.color_of_user(identity.user_id)
        if action in SOLO_ONLY_ACTIONS:
            raise HTTPException(status_code=409, detail="That is not available in friend games.")
        if mine is None:
            raise HTTPException(status_code=403, detail="Only the two players can do that.")
        if action == "abort" and not game.in_first_move_phase():
            raise HTTPException(
                status_code=409,
                detail="A friend game can be aborted only before both first moves. Resign instead.",
            )
        if action in {"move", "claim_draw"}:
            side = "white" if game.board.turn else "black"
            if side != mine:
                raise HTTPException(status_code=403, detail="It is not your move.")
        if action == "resign" and color is not None and color != mine:
            raise HTTPException(status_code=403, detail="You can only resign your own side.")

    async def analysis_allowed(self, identity: Identity | None, game_id: str) -> bool:
        """No engine help while people are still playing a friend game."""
        if identity is None:
            return True
        game = await self.manager.get(game_id)
        live = game.lifecycle in {MatchState.RUNNING, MatchState.PAUSED}
        people = any(game.player_for_color(c).is_human for c in ("white", "black"))
        return not (game.friend_game and live and people)

    # --- lobby ---------------------------------------------------------------------
    async def lobby(self, identity: Identity) -> dict[str, object]:
        now = datetime.now(UTC)
        await self.store.expire_challenges(now)
        members = await self.store.active_members()
        busy = await self.store.busy_user_ids()
        friends = []
        for member in members:
            if member["email"] == identity.email:
                continue
            if member["user_id"] is None:
                status = "invited"
            elif member["user_id"] in busy:
                status = "in_game"
            elif member["last_seen_at"] and now - member["last_seen_at"] < timedelta(
                seconds=ONLINE_SECONDS
            ):
                status = "online"
            else:
                status = "offline"
            friends.append(
                {"email": member["email"], "name": display_name(member["email"]), "status": status}
            )
        incoming, outgoing = [], []
        for challenge in await self.store.challenges_for(identity.user_id, identity.email):
            public = self._public(challenge)
            recent = now - challenge["created_at"] < timedelta(minutes=CHALLENGE_MINUTES + 5)
            if challenge["challenger_id"] == identity.user_id:
                answered = challenge["status"] in {"accepted", "declined"}
                if not answered or now - _updated(challenge) < timedelta(seconds=ANSWERED_SECONDS):
                    outgoing.append(public)
            elif challenge["status"] == "pending" and recent:
                incoming.append(public)
        live = await self.manager.live_snapshot_for_user(identity.user_id)
        return {
            "me": {"email": identity.email, "name": display_name(identity.email)},
            "members": friends,
            "incoming": incoming,
            "outgoing": outgoing,
            "live_game_id": live.id if live else None,
        }

    @staticmethod
    def _public(challenge: dict[str, object]) -> dict[str, object]:
        return {
            "id": challenge["id"],
            "from": display_name(str(challenge["challenger_email"])),
            "from_email": challenge["challenger_email"],
            "to": display_name(str(challenge["opponent_email"])),
            "to_email": challenge["opponent_email"],
            "initial_time_ms": challenge["initial_time_ms"],
            "increment_ms": challenge["increment_ms"],
            "color": challenge["color"],
            "status": challenge["status"],
            "game_id": challenge["game_id"],
            "expires_at": challenge["expires_at"],
        }

    # --- challenges ------------------------------------------------------------------
    async def create(self, identity: Identity, request: ChallengeCreate) -> dict[str, object]:
        try:
            opponent = normalize_email(request.opponent_email)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if opponent == identity.email:
            raise HTTPException(status_code=422, detail="You cannot challenge yourself.")
        members = {m["email"]: m for m in await self.store.active_members()}
        if opponent not in members:
            raise HTTPException(status_code=404, detail="That person is not a Lounge member.")
        if await self.store.live_match_ids_for_user(identity.user_id):
            raise HTTPException(status_code=409, detail="Finish or abort your current game first.")
        now = datetime.now(UTC)
        await self.store.expire_challenges(now)
        mine = await self.store.challenges_for(identity.user_id, identity.email)
        if any(
            c["challenger_id"] == identity.user_id and c["status"] in {"pending", "accepting"}
            for c in mine
        ):
            raise HTTPException(
                status_code=409, detail="You already have a challenge waiting. Cancel it first."
            )
        challenge = await self.store.create_challenge(
            {
                "id": str(uuid4()),
                "challenger_id": identity.user_id,
                "challenger_email": identity.email,
                "opponent_email": opponent,
                "initial_time_ms": request.initial_time_ms,
                "increment_ms": request.increment_ms,
                "color": request.color,
                "status": "pending",
                "game_id": None,
                "created_at": now,
                "updated_at": now,
                "expires_at": now + timedelta(minutes=CHALLENGE_MINUTES),
            }
        )
        return self._public(challenge)

    async def _challenge_for(self, challenge_id: str) -> dict[str, object]:
        challenge = await self.store.get_challenge(challenge_id)
        if challenge is None:
            raise HTTPException(status_code=404, detail="Challenge not found.")
        return challenge

    async def accept(self, identity: Identity, challenge_id: str) -> dict[str, object]:
        challenge = await self._challenge_for(challenge_id)
        if challenge["opponent_email"] != identity.email:
            raise HTTPException(status_code=404, detail="Challenge not found.")
        now = datetime.now(UTC)
        if challenge["status"] != "pending" or challenge["expires_at"] <= now:
            raise HTTPException(status_code=409, detail="This challenge is no longer open.")
        async with self.creation_lock:
            for user_id, who in ((identity.user_id, "You are"), (challenge["challenger_id"], None)):
                if await self.store.live_match_ids_for_user(str(user_id)):
                    name = display_name(str(challenge["challenger_email"]))
                    raise HTTPException(
                        status_code=409,
                        detail=f"{who or name + ' is'} already in a game. Try again when it ends.",
                    )
            if len(await self.store.latest_live_match_ids()) >= self.settings.max_live_games:
                raise HTTPException(
                    status_code=503, detail="Every table is busy right now. Try again in a minute."
                )
            if not await self.store.transition_challenge(
                challenge_id, from_status="pending", to_status="accepting", now=now
            ):
                raise HTTPException(status_code=409, detail="This challenge is no longer open.")
            try:
                game = await self._start_game(challenge, identity)
            except Exception:
                await self.store.transition_challenge(
                    challenge_id,
                    from_status="accepting",
                    to_status="pending",
                    now=datetime.now(UTC),
                )
                raise
            await self.store.transition_challenge(
                challenge_id,
                from_status="accepting",
                to_status="accepted",
                now=datetime.now(UTC),
                game_id=game.id,
            )
        return {"game_id": game.id}

    async def _start_game(self, challenge: dict[str, object], opponent: Identity):
        choice = str(challenge["color"])
        if choice == "random":
            choice = secrets.choice(["white", "black"])
        challenger = (str(challenge["challenger_id"]), str(challenge["challenger_email"]))
        accepter = (opponent.user_id, opponent.email)
        white, black = (challenger, accepter) if choice == "white" else (accepter, challenger)

        def seat(color: str, email: str) -> PlayerConfiguration:
            return PlayerConfiguration.human(color).model_copy(
                update={"display_name": display_name(email), "provider": "Lounge member"}
            )

        request = CreateGameRequest(
            opponent=OpponentKind.HUMAN,
            initial_time_ms=int(challenge["initial_time_ms"]),
            increment_ms=int(challenge["increment_ms"]),
            white_player=seat("white", white[1]),
            black_player=seat("black", black[1]),
        )
        return await self.manager.create(
            request,
            owner_id=challenger[0],
            seat_users=(white[0], black[0]),
            first_move_window_ms=FIRST_MOVE_WINDOW_MS,
        )

    async def decline(self, identity: Identity, challenge_id: str) -> None:
        challenge = await self._challenge_for(challenge_id)
        if challenge["opponent_email"] != identity.email:
            raise HTTPException(status_code=404, detail="Challenge not found.")
        if not await self.store.transition_challenge(
            challenge_id, from_status="pending", to_status="declined", now=datetime.now(UTC)
        ):
            raise HTTPException(status_code=409, detail="This challenge is no longer open.")

    async def cancel(self, identity: Identity, challenge_id: str) -> None:
        challenge = await self._challenge_for(challenge_id)
        if challenge["challenger_id"] != identity.user_id:
            raise HTTPException(status_code=404, detail="Challenge not found.")
        if not await self.store.transition_challenge(
            challenge_id, from_status="pending", to_status="cancelled", now=datetime.now(UTC)
        ):
            raise HTTPException(status_code=409, detail="This challenge is no longer open.")

    async def rematch(self, identity: Identity, game_id: str) -> dict[str, object]:
        game = await self.manager.get(game_id)
        mine = game.color_of_user(identity.user_id) if game.friend_game else None
        if mine is None:
            raise HTTPException(status_code=409, detail="Rematch is for friend games.")
        if game.lifecycle in {MatchState.RUNNING, MatchState.PAUSED}:
            raise HTTPException(status_code=409, detail="The game is still being played.")
        other = game.seat_user("black" if mine == "white" else "white")
        email = next(
            (m["email"] for m in await self.store.active_members() if m["user_id"] == other),
            None,
        )
        if email is None:
            raise HTTPException(status_code=404, detail="Your opponent is no longer a member.")
        # Colours swap: you take the side you did not have.
        return await self.create(
            identity,
            ChallengeCreate(
                opponent_email=email,
                initial_time_ms=game.initial_time_ms,
                increment_ms=game.increment_ms,
                color="black" if mine == "white" else "white",
            ),
        )


def _updated(challenge: dict[str, object]) -> datetime:
    return challenge.get("updated_at") or challenge["created_at"]  # type: ignore[return-value]


def register(application: FastAPI, friends: FriendGames, identity_of) -> None:
    def who(request: Request) -> Identity:
        identity = identity_of(request)
        if identity is None:
            raise HTTPException(status_code=404, detail="Not available in local mode.")
        return identity

    @application.get("/api/lobby")
    async def get_lobby(request: Request) -> dict[str, object]:
        return await friends.lobby(who(request))

    @application.post("/api/challenges", status_code=201)
    async def create_challenge(body: ChallengeCreate, request: Request) -> dict[str, object]:
        return await friends.create(who(request), body)

    @application.post("/api/challenges/{challenge_id}/accept")
    async def accept_challenge(challenge_id: str, request: Request) -> dict[str, object]:
        return await friends.accept(who(request), challenge_id)

    @application.post("/api/challenges/{challenge_id}/decline", status_code=204)
    async def decline_challenge(challenge_id: str, request: Request) -> None:
        await friends.decline(who(request), challenge_id)

    @application.post("/api/challenges/{challenge_id}/cancel", status_code=204)
    async def cancel_challenge(challenge_id: str, request: Request) -> None:
        await friends.cancel(who(request), challenge_id)

    @application.post("/api/games/{game_id}/rematch", status_code=201)
    async def rematch(game_id: str, request: Request) -> dict[str, object]:
        return await friends.rematch(who(request), game_id)


__all__ = ["FriendGames", "register"]
