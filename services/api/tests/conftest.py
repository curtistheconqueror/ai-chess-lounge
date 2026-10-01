from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))


@pytest.fixture
def client(tmp_path: Path):
    from lounge_api.main import create_app
    from lounge_api.manager import GameManager
    from lounge_api.persistence import DatabaseStore

    database_url = f"sqlite+aiosqlite:///{tmp_path / 'api.db'}"
    manager = GameManager(store=DatabaseStore(database_url))
    with TestClient(create_app(manager)) as test_client:
        yield test_client
