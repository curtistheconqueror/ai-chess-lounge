from __future__ import annotations

import asyncio
import os
import re
import signal
from pathlib import Path
from urllib.parse import urlsplit


class BridgeError(RuntimeError):
    """Safe operator-facing failure; never include child output or credentials."""


def child_environment() -> dict[str, str]:
    # Preserve official CLI auth locations without reading, copying, or rewriting them.
    # In particular, no API key, runner token, pairing code, or proxy credential inherits.
    allowed = {
        "PATH",
        "HOME",
        "USER",
        "LOGNAME",
        "LANG",
        "LC_ALL",
        "TMPDIR",
        "CODEX_HOME",
        "XDG_CONFIG_HOME",
        "XDG_DATA_HOME",
        "XDG_RUNTIME_DIR",
        "DBUS_SESSION_BUS_ADDRESS",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
    }
    environment = {key: value for key, value in os.environ.items() if key in allowed}
    # Hosted environments may require their configured outbound proxy. Preserve
    # ordinary routing, but never pass a credential-bearing proxy URL to the child.
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        value = os.environ.get(key)
        if not value:
            continue
        try:
            parsed = urlsplit(value)
            safe = (
                parsed.scheme in {"http", "https"}
                and bool(parsed.hostname)
                and parsed.username is None
                and parsed.password is None
                and parsed.path in {"", "/"}
                and not parsed.query
                and not parsed.fragment
            )
            if safe:
                environment[key] = value
        except ValueError:
            continue
    for key in ("NO_PROXY", "no_proxy"):
        if key in os.environ:
            environment[key] = os.environ[key]
    return environment


async def run_process(
    argv: list[str],
    *,
    cwd: Path,
    stdin: bytes = b"",
    timeout: float = 15,
    output_limit: int = 32_768,
) -> tuple[int, bytes, bytes]:
    if os.name != "posix":
        raise BridgeError("This bridge currently requires Linux or macOS process isolation.")
    if len(stdin) > 262_144:
        raise BridgeError("Turn input exceeds the bridge limit.")
    try:
        process = await asyncio.create_subprocess_exec(
            *argv,
            cwd=cwd,
            env=child_environment(),
            start_new_session=True,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except OSError:
        raise BridgeError("Could not launch the installed provider CLI.") from None

    stdout_buffer, stderr_buffer = bytearray(), bytearray()

    async def read(stream: asyncio.StreamReader, result: bytearray) -> bytes:
        while chunk := await stream.read(4096):
            result.extend(chunk)
            if len(result) > output_limit:
                raise BridgeError("Provider CLI output exceeded the bridge limit.")
        return bytes(result)

    async def write() -> None:
        assert process.stdin is not None
        process.stdin.write(stdin)
        try:
            await process.stdin.drain()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            process.stdin.close()

    assert process.stdout is not None and process.stderr is not None
    tasks = [
        asyncio.create_task(read(process.stdout, stdout_buffer)),
        asyncio.create_task(read(process.stderr, stderr_buffer)),
        asyncio.create_task(write()),
    ]
    try:
        async with asyncio.timeout(timeout):
            stdout, stderr, _ = await asyncio.gather(*tasks)
            code = await process.wait()
            return code, stdout, stderr
    except TimeoutError:
        hint = diagnostic_hint(bytes(stderr_buffer))
        raise BridgeError(f"Provider CLI exceeded its turn deadline. {hint}") from None
    finally:
        # Kill the entire process group, including descendants that outlive their parent.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

        # A killed writer may leave a paused pipe transport with buffered output.
        # Drain without retaining it so process.wait cannot deadlock on pipe closure.
        async def discard(stream: asyncio.StreamReader) -> None:
            while await stream.read(4096):
                pass

        await asyncio.gather(discard(process.stdout), discard(process.stderr))
        await process.wait()


def diagnostic_hint(stderr: bytes) -> str:
    """Classify locally; never interpolate raw diagnostics, paths, or server bodies."""
    normalized = stderr.lower()
    statuses = set(
        re.findall(
            rb"\b(?:http(?:/\d(?:\.\d)?)?|status(?: code)?)\s*[:=]?\s*(401|403|429)\b",
            normalized,
        )
    )
    if b"401" in statuses or b"unauthorized" in normalized:
        return "The CLI reported an authentication failure."
    if b"403" in statuses:
        return "The CLI reported an access denial."
    if b"429" in statuses or b"rate limit" in normalized or b"too many requests" in normalized:
        return "The CLI reported rate limiting; account quota exhaustion is not established."
    if b"usage_limit_reached" in normalized or b"insufficient_quota" in normalized:
        return "The CLI reported a quota error; check the official account usage information."
    if b"error sending request" in normalized or b"connection" in normalized:
        return "The CLI reported a connection problem."
    if b"schema" in normalized and b"invalid" in normalized:
        return "The CLI reported an output-schema error."
    return "Check the official CLI locally for diagnostics."
