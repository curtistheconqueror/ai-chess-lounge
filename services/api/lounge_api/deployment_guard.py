"""Keep each deployment mode to what it has been verified for.

Local mode is the operator's own Lounge. Hosted mode is the invite-only public
release (ADR0043): it starts only with complete identity configuration and a
migrated schema, and local-only components (batch worker, remote runners) refuse it.
"""

import os


def deployment_mode() -> str:
    deployment = os.environ.get("LOUNGE_DEPLOYMENT", "local")
    hosted = os.environ.get("LOUNGE_HOSTED_MODE", "0")
    if deployment not in {"local", "hosted"} or hosted not in {"0", "1"}:
        raise RuntimeError("Invalid Lounge deployment mode; refusing startup.")
    if (deployment == "hosted") != (hosted == "1"):
        raise RuntimeError("LOUNGE_DEPLOYMENT and LOUNGE_HOSTED_MODE disagree; refusing startup.")
    return deployment


def require_supported_runtime() -> str:
    """The deployment mode, after checking hosted mode is fully configured."""
    mode = deployment_mode()
    if mode == "hosted":
        from .hosted_auth import HostedSettings

        HostedSettings.from_environment()
    return mode


def require_local_runtime() -> None:
    """For components that are not part of the hosted release."""
    if deployment_mode() != "local":
        raise RuntimeError(
            "Hosted startup is disabled for this component: it is not part of the "
            "invite-only hosted release."
        )
