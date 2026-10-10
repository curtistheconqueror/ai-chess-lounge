"""Resolve public web files without allowing paths outside the build directory."""

from pathlib import Path

from fastapi import HTTPException


def public_path(root: Path, requested: str) -> Path:
    # HTTP decoding occurs before routing. Treat both separator styles identically
    # on every host, and reject Windows drives/alternate data streams everywhere.
    normalized = requested.replace("\\", "/")
    if normalized.startswith("/") or ":" in normalized or ".." in normalized.split("/"):
        raise HTTPException(status_code=404, detail="Not found.")
    try:
        candidate = (root / normalized).resolve()
        candidate.relative_to(root)
    except (OSError, RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="Not found.") from exc
    return candidate
