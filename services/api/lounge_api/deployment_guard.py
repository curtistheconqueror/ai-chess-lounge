"""Keep the local operator runtime from being mistaken for a hosted release."""

import os


def require_local_runtime() -> None:
    deployment = os.environ.get("LOUNGE_DEPLOYMENT", "local")
    hosted = os.environ.get("LOUNGE_HOSTED_MODE", "0")
    if deployment not in {"local", "hosted"} or hosted not in {"0", "1"}:
        raise RuntimeError("Invalid Lounge deployment mode; refusing startup.")
    if deployment == "hosted" or hosted == "1":
        raise RuntimeError(
            "Hosted startup is disabled in this build: integrate and verify private "
            "ownership, authentication and isolation before enabling it."
        )
