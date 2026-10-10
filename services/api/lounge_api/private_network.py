"""Explicit trusted-device sharing; this is not hosted account authorization."""

import ipaddress
import os
from dataclasses import dataclass
from urllib.parse import urlsplit

from starlette.responses import JSONResponse


def tailscale_ip(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
        return address in ipaddress.ip_network("100.64.0.0/10") or address in ipaddress.ip_network(
            "fd7a:115c:a1e0::/48"
        )
    except ValueError:
        return False


def csv(name: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in os.getenv(name, "").split(",") if item.strip())


@dataclass(frozen=True)
class NetworkSettings:
    mode: str
    host: str
    port: int
    origins: tuple[str, ...]
    peers: tuple[str, ...] = ()
    users: tuple[str, ...] = ()

    @classmethod
    def from_environment(cls):
        mode = os.getenv("LOUNGE_NETWORK_MODE", "local")
        host = os.getenv("LOUNGE_BIND_HOST", "127.0.0.1")
        try:
            port = int(os.getenv("LOUNGE_PORT", "8000"))
        except ValueError:
            raise ValueError("LOUNGE_PORT must be an integer") from None
        if not 1024 <= port <= 65535:
            raise ValueError("LOUNGE_PORT must be between 1024 and 65535")
        if mode == "local":
            if host not in {"127.0.0.1", "::1"}:
                raise ValueError("Local mode must bind loopback")
            return cls(mode, host, port, ("http://localhost:5173", "http://127.0.0.1:5173"))
        if mode not in {"tailscale", "tailscale-serve"}:
            raise ValueError("Unknown LOUNGE_NETWORK_MODE")
        origins = csv("LOUNGE_PRIVATE_ORIGINS")
        if not origins:
            raise ValueError("Private sharing requires exact LOUNGE_PRIVATE_ORIGINS")
        for origin in origins:
            parsed = urlsplit(origin)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
                or parsed.path
                or parsed.query
                or parsed.fragment
                or "*" in origin
                or not (tailscale_ip(parsed.hostname) or parsed.hostname.endswith(".ts.net"))
            ):
                raise ValueError("Private origins must be exact Tailscale scheme/host/port origins")
            _ = parsed.port  # Validate malformed ports as well.
            if mode == "tailscale-serve" and (
                parsed.scheme != "https" or not parsed.hostname.endswith(".ts.net")
            ):
                raise ValueError("Serve requires an HTTPS .ts.net origin")
        peers = csv("LOUNGE_PRIVATE_PEERS")
        users = csv("LOUNGE_TAILSCALE_USERS")
        if mode == "tailscale":
            if not tailscale_ip(host) or not peers or not all(tailscale_ip(p) for p in peers):
                raise ValueError("Direct sharing requires a Tailscale bind IP and exact peer IPs")
        elif (
            host != "127.0.0.1"
            or not 1 <= len(users) <= 2
            or any("@" not in user or any(c.isspace() for c in user) for user in users)
        ):
            raise ValueError("Serve requires IPv4 loopback and one or two exact Tailscale logins")
        return cls(mode, host, port, origins, peers, users)


class PrivateNetworkMiddleware:
    def __init__(self, app, settings: NetworkSettings):
        self.app, self.settings = app, settings

    async def __call__(self, scope, receive, send):
        if scope["type"] not in {"http", "websocket"}:
            return await self.app(scope, receive, send)
        settings = self.settings
        headers = {}
        duplicate = False
        for key, value in scope.get("headers", []):
            key = key.lower()
            if key in {b"host", b"origin", b"tailscale-user-login"} and key in headers:
                duplicate = True
            headers[key] = value.decode("latin1")
        peer = (scope.get("client") or ("", 0))[0]
        allowed_peer = (
            peer in settings.peers
            if settings.mode == "tailscale"
            else (peer == "127.0.0.1" and headers.get(b"tailscale-user-login") in settings.users)
        )
        # CORS alone does not prevent requests or authorize sockets. Check both.
        origin = headers.get(b"origin")
        allowed_host = headers.get(b"host") in {urlsplit(o).netloc for o in settings.origins}
        allowed_origin = origin in settings.origins if origin else scope["type"] == "http"
        path = scope.get("path", "")
        # No remote credential issuance, batch execution, diagnostics or API docs.
        allowed_path = not path.startswith(("/api", "/ws", "/docs", "/redoc", "/openapi"))
        allowed_path |= path in {
            "/api/health",
            "/api/engine/strength",
            "/api/player-adapters",
            "/api/live-match",
            "/api/games",
        } or path.startswith(("/api/games/", "/ws/games/"))
        if duplicate or not (allowed_peer and allowed_host and allowed_origin and allowed_path):
            if scope["type"] == "websocket":
                await send({"type": "websocket.close", "code": 1008})
            else:
                await JSONResponse({"detail": "Private sharing access denied."}, status_code=403)(
                    scope, receive, send
                )
            return
        await self.app(scope, receive, send)
