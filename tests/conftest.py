"""Tests run against a throw-away database and data dir — never the dev journal, never the network."""

import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_tmp = Path(tempfile.mkdtemp(prefix="trader-tests-"))
os.environ.update({
    "DATABASE_URL": f"sqlite:///{_tmp}/test.db",
    "DATA_DIR": str(_tmp / "data"),
    "REPORTS_DIR": str(_tmp / "reports"),
    "RUN_WATCHER": "false",
    "TRADING_MODE": "paper",
})


@pytest.fixture
def client():
    from trader.main import app

    with TestClient(app, base_url="http://127.0.0.1:8000", headers={"X-Trader-UI": "1"}) as client:
        yield client
    app.dependency_overrides.clear()
