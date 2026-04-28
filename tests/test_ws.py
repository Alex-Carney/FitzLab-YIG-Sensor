import pytest
from starlette.testclient import TestClient

from app.auth import make_session_cookie


@pytest.fixture
def app_env(monkeypatch, synth_db_path):
    monkeypatch.setenv("YIG_DASHBOARD_PASSWORD", "pw")
    monkeypatch.setenv("YIG_DASHBOARD_SECRET", "s" * 32)
    monkeypatch.setenv("YIG_DB_PATH", str(synth_db_path))
    monkeypatch.setenv("YIG_COLLECTION_CADENCE_SEC", "1.0")
    monkeypatch.setenv("YIG_DEV_MODE", "1")
    from app.main import build_app
    return build_app()


def test_ws_rejects_without_cookie(app_env):
    """Connection must close (1008 policy violation) without a session cookie."""
    with TestClient(app_env) as client:
        with pytest.raises(Exception):
            with client.websocket_connect("/ws"):
                pass


def test_ws_accepts_with_cookie(app_env):
    cookie_value = make_session_cookie("s" * 32, ttl_sec=3600)
    with TestClient(app_env) as client:
        with client.websocket_connect(
            "/ws",
            headers={"cookie": f"yig_session={cookie_value}"},
        ) as ws:
            assert ws is not None
