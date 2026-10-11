"""Run with python -m lounge_api.serve; never activates Tailscale itself."""

import argparse

import uvicorn

from .deployment_guard import require_local_runtime


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Validate config without listening")
    args = parser.parse_args()
    # main loads the same host-only dotenv files used by ordinary startup.
    from .main import app
    from .private_network import NetworkSettings

    require_local_runtime()
    settings = NetworkSettings.from_environment()
    if args.check:
        print(f"Valid {settings.mode} configuration; bind {settings.host}:{settings.port}")
        return
    # Preserve the real socket peer; never trust client-supplied X-Forwarded-For.
    uvicorn.run(app, host=settings.host, port=settings.port, proxy_headers=False)


if __name__ == "__main__":
    main()
