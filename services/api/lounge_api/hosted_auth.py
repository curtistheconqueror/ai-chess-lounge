"""Hosted (invite-only) access: Supabase sign-in, members, ownership and live tickets.

Local mode never loads this. In hosted mode every /api and /ws request except a few
public paths needs a verified Supabase access token from an invited, active member,
and every game route is limited to the game's owner (or an admin). See ADR0043.
"""

from __future__ import annotations

import asyncio
import os
import re
import secrets
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from urllib.parse import parse_qs, urlsplit

import jwt
from fastapi.responses import JSONResponse

# Public: liveness and the configuration the sign-in screen needs.
PUBLIC_PATHS = frozenset({"/api/health", "/api/ready", "/api/auth/config"})
# The hosted feature scope: a player's own Stockfish table and the admin invite list.
MEMBER_PATHS = frozenset(
    {
        "/api/auth/me",
        "/api/ws-ticket",
        "/api/table-settings",
        "/api/live-match",
        "/api/games",
        "/api/engine/strength",
        "/api/player-adapters",
    }
)
GAME_PATH = re.compile(r"^/(?:api|ws)/games/([0-9a-fA-F-]{36})(?:/|$)")
# Game actions that call AI providers or agent seats: not part of the hosted release.
HOSTED_BLOCKED_ACTIONS = re.compile(
    r"^/api/games/[^/]+/(?:consultations|human-suggestion|retry-agent)(?:/|$)"
)
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
TICKET_SECONDS = 30
MAX_BODY_BYTES = 64 * 1024
# Per-player request budgets (sliding 60 s windows) for changes, and for new games.
WRITE_LIMIT_PER_MINUTE = 90
CREATE_LIMIT_PER_MINUTE = 6
SECURITY_HEADERS = [
    (b"x-frame-options", b"DENY"),
    (b"content-security-policy", b"frame-ancestors 'none'"),
    (b"x-content-type-options", b"nosniff"),
    (b"referrer-policy", b"strict-origin-when-cross-origin"),
    (b"strict-transport-security", b"max-age=31536000; includeSubDomains"),
]


def normalize_email(value: str) -> str:
    email = value.strip().lower()
    if len(email) > 254 or not EMAIL.match(email):
        raise ValueError("Enter a valid email address.")
    return email


@dataclass(frozen=True, slots=True)
class HostedSettings:
    supabase_url: str
    publishable_key: str
    public_origin: str
    admin_emails: frozenset[str]
    providers: tuple[str, ...]
    max_live_games: int

    @property
    def issuer(self) -> str:
        return f"{self.supabase_url}/auth/v1"

    @property
    def jwks_url(self) -> str:
        return f"{self.issuer}/.well-known/jwks.json"

    @classmethod
    def from_environment(cls) -> HostedSettings:
        """Fail closed: hosted startup needs every value, and nothing defaults open."""
        url = os.environ.get("SUPABASE_URL", "").rstrip("/")
        key = os.environ.get("SUPABASE_PUBLISHABLE_KEY", "")
        origin = os.environ.get("LOUNGE_PUBLIC_ORIGIN", "").rstrip("/")
        admins = os.environ.get("LOUNGE_ADMIN_EMAILS", "")
        database = os.environ.get("DATABASE_URL", "")
        problems = []
        if not re.fullmatch(r"https://[a-z0-9]{20}\.supabase\.co", url):
            problems.append("SUPABASE_URL")
        if not key or key.startswith("sb_secret_") or "service_role" in key:
            problems.append("SUPABASE_PUBLISHABLE_KEY (must be the public key)")
        parsed = urlsplit(origin)
        if parsed.scheme != "https" or not parsed.netloc or parsed.path:
            problems.append("LOUNGE_PUBLIC_ORIGIN")
        try:
            emails = frozenset(normalize_email(item) for item in admins.split(",") if item.strip())
        except ValueError:
            emails = frozenset()
        if not emails:
            problems.append("LOUNGE_ADMIN_EMAILS")
        if not database.startswith(("postgresql+asyncpg://", "postgresql://", "postgres://")):
            problems.append("DATABASE_URL (PostgreSQL)")
        providers = tuple(
            item.strip()
            for item in os.environ.get("LOUNGE_AUTH_PROVIDERS", "email,google,github").split(",")
            if item.strip() in {"email", "google", "github"}
        )
        if not providers:
            problems.append("LOUNGE_AUTH_PROVIDERS")
        try:
            max_live = int(os.environ.get("LOUNGE_MAX_LIVE_GAMES", "20"))
        except ValueError:
            max_live = 0
        if not 1 <= max_live <= 500:
            problems.append("LOUNGE_MAX_LIVE_GAMES")
        if problems:
            raise RuntimeError("Hosted startup refused; missing or invalid: " + ", ".join(problems))
        return cls(url, key, origin, emails, providers, max_live)


@dataclass(frozen=True, slots=True)
class Identity:
    user_id: str
    email: str
    role: str  # "admin" | "player"

    @property
    def admin(self) -> bool:
        return self.role == "admin"


class InvalidToken(Exception):
    pass


class TokenVerifier:
    """Verifies Supabase access tokens against the project's public signing keys."""

    def __init__(self, settings: HostedSettings):
        self.settings = settings
        # The key set is cached for 10 minutes; individual keys are not cached forever,
        # so a key Supabase rotates out stops being trusted.
        self._keys = jwt.PyJWKClient(
            settings.jwks_url, cache_keys=False, cache_jwk_set=True, lifespan=600, timeout=5
        )

    async def verify(self, token: str) -> tuple[str, str]:
        try:
            key = await asyncio.to_thread(self._keys.get_signing_key_from_jwt, token)
            claims = jwt.decode(
                token,
                key.key,
                algorithms=["ES256", "RS256"],
                audience="authenticated",
                issuer=self.settings.issuer,
                options={"require": ["exp", "sub", "iss", "aud"]},
                leeway=30,
            )
        except (jwt.PyJWTError, OSError) as exc:
            raise InvalidToken from exc
        email = claims.get("email")
        if claims.get("role") != "authenticated" or claims.get("is_anonymous") or not email:
            raise InvalidToken
        if not _email_proven(claims):
            raise InvalidToken
        try:
            return str(claims["sub"]), normalize_email(str(email))
        except ValueError as exc:
            raise InvalidToken from exc


def _email_proven(claims: dict) -> bool:
    """The address was proven: confirmed, or signed in by link/code or a provider.

    Defense in depth beside Supabase's "Confirm email" setting: a password account
    whose address was never confirmed cannot claim an invitation.
    """
    metadata = claims.get("user_metadata")
    if isinstance(metadata, dict) and metadata.get("email_verified") is True:
        return True
    methods = {item.get("method") for item in claims.get("amr") or [] if isinstance(item, dict)}
    return bool(methods & {"otp", "magiclink", "oauth"})


class RateLimiter:
    """Small in-memory sliding-window limiter (one machine, see ADR0043)."""

    def __init__(self) -> None:
        self._hits: dict[str, list[float]] = {}

    def allow(self, key: str, limit: int, window: float = 60.0) -> bool:
        now = time.monotonic()
        hits = [t for t in self._hits.get(key, ()) if now - t < window]
        if len(hits) >= limit:
            self._hits[key] = hits
            return False
        hits.append(now)
        self._hits[key] = hits
        if len(self._hits) > 10_000:  # forget idle keys
            self._hits = {k: v for k, v in self._hits.items() if v and now - v[-1] < window}
        return True


class LiveTickets:
    """One-time, 30-second tickets that let a signed-in page open a game WebSocket.

    Browsers cannot attach an Authorization header to a WebSocket, and an access token
    in a URL would end up in logs. A ticket is single-use and expires quickly. They are
    held in memory, so the hosted app runs as one machine (ADR0043).
    """

    def __init__(self) -> None:
        self._tickets: dict[str, tuple[Identity, float]] = {}

    def issue(self, identity: Identity) -> str:
        now = time.monotonic()
        self._tickets = {k: v for k, v in self._tickets.items() if v[1] > now}
        ticket = secrets.token_urlsafe(32)
        self._tickets[ticket] = (identity, now + TICKET_SECONDS)
        return ticket

    def redeem(self, ticket: str) -> Identity | None:
        entry = self._tickets.pop(ticket, None)
        if entry is None or entry[1] <= time.monotonic():
            return None
        return entry[0]


MemberLookup = Callable[[str, str], Awaitable[str | None]]
OwnerLookup = Callable[[str], Awaitable[tuple[bool, str | None]]]


class HostedAccessMiddleware:
    """Authenticates members and confines every game route to its owner or an admin."""

    def __init__(
        self,
        app,
        settings: HostedSettings,
        verifier: TokenVerifier,
        tickets: LiveTickets,
        member_role: MemberLookup,
        match_owner: OwnerLookup,
    ):
        self.app, self.settings, self.verifier, self.tickets = app, settings, verifier, tickets
        self.member_role, self.match_owner = member_role, match_owner
        self.limits = RateLimiter()

    async def __call__(self, scope, receive, send):
        if scope["type"] not in {"http", "websocket"}:
            return await self.app(scope, receive, send)
        if scope["type"] == "http":
            send = _with_security_headers(send)
        path = scope.get("path", "")
        if not path.startswith(("/api", "/ws", "/docs", "/redoc", "/openapi")):
            return await self.app(scope, receive, send)  # the web app itself
        if scope["type"] == "http" and path in PUBLIC_PATHS:
            return await self.app(scope, receive, send)
        headers = {
            key.decode("latin1").lower(): value.decode("latin1")
            for key, value in scope.get("headers", [])
        }
        game = GAME_PATH.match(path)
        allowed = not HOSTED_BLOCKED_ACTIONS.match(path) and (
            path in MEMBER_PATHS
            or path.startswith("/api/admin/members")
            or (game is not None and path.startswith("/api/games/"))
            or (game is not None and scope["type"] == "websocket")
        )
        if not allowed:
            return await self._deny(
                scope, receive, send, 404, "Not available on the hosted Lounge."
            )
        identity = await self._identity(scope, headers)
        if identity is None:
            return await self._deny(scope, receive, send, 401, "Sign in to continue.")
        if identity == "not-invited":
            return await self._deny(
                scope, receive, send, 403, "This account has not been invited to the Lounge."
            )
        if path.startswith("/api/admin/") and not identity.admin:
            return await self._deny(scope, receive, send, 403, "Admins only.")
        method = scope.get("method", "GET")
        if scope["type"] == "http" and method not in {"GET", "HEAD", "OPTIONS"}:
            length = headers.get("content-length", "0")
            if not length.isdigit() or int(length) > MAX_BODY_BYTES:
                return await self._deny(scope, receive, send, 413, "Request too large.")
            creating = path == "/api/games" and method == "POST"
            if not self.limits.allow(f"write:{identity.user_id}", WRITE_LIMIT_PER_MINUTE) or (
                creating
                and not self.limits.allow(f"create:{identity.user_id}", CREATE_LIMIT_PER_MINUTE)
            ):
                return await self._deny(
                    scope, receive, send, 429, "Too many actions at once. Wait a moment."
                )
        if game is not None:
            exists, owner = await self.match_owner(game.group(1))
            # Unowned (pre-hosting) games belong to the admins. Never reveal others' games.
            if not exists or not (
                identity.admin or (owner is not None and owner == identity.user_id)
            ):
                return await self._deny(scope, receive, send, 404, "Game not found.")
        scope.setdefault("state", {})["identity"] = identity
        await self.app(scope, receive, send)

    async def _identity(self, scope, headers) -> Identity | str | None:
        if scope["type"] == "websocket":
            if headers.get("origin") != self.settings.public_origin:
                return None
            ticket = parse_qs(scope.get("query_string", b"").decode("latin1")).get("ticket", [""])[
                0
            ]
            return self.tickets.redeem(ticket) if ticket else None
        authorization = headers.get("authorization", "")
        if not authorization.lower().startswith("bearer "):
            return None
        try:
            user_id, email = await self.verifier.verify(authorization[7:].strip())
        except InvalidToken:
            return None
        role = await self.member_role(email, user_id)
        if role is None:
            return "not-invited"
        return Identity(user_id=user_id, email=email, role=role)

    async def still_allowed(self, identity: Identity, game_id: str) -> bool:
        """Re-check an open socket: still a member, still allowed on this game."""
        role = await self.member_role(identity.email, identity.user_id)
        if role is None:
            return False
        exists, owner = await self.match_owner(game_id)
        return exists and (role == "admin" or owner == identity.user_id)

    @staticmethod
    async def _deny(scope, receive, send, status: int, detail: str):
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008})
            return
        await JSONResponse(
            {"detail": detail}, status_code=status, headers={"Cache-Control": "no-store"}
        )(scope, receive, send)


def _with_security_headers(send):
    """Hosted responses refuse framing (clickjacking) and insist on HTTPS."""

    async def wrapped(message):
        if message["type"] == "http.response.start":
            present = {name.lower() for name, _ in message.get("headers", [])}
            message = {
                **message,
                "headers": [
                    *message.get("headers", []),
                    *[(name, value) for name, value in SECURITY_HEADERS if name not in present],
                ],
            }
        await send(message)

    return wrapped
