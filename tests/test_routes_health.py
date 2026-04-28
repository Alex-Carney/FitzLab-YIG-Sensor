import pytest
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_healthz_ok(synth_db_path, monkeypatch):
    monkeypatch.setenv("YIG_DASHBOARD_PASSWORD", "pw")
    monkeypatch.setenv("YIG_DASHBOARD_SECRET", "s" * 32)
    monkeypatch.setenv("YIG_DB_PATH", str(synth_db_path))
    monkeypatch.setenv("YIG_COLLECTION_CADENCE_SEC", "1.0")
    monkeypatch.setenv("YIG_DEV_MODE", "1")

    from app.main import build_app
    app = build_app()

    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            r = await c.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["db_path"].endswith("synth.duckdb")
    assert "last_row_age_seconds" in body
    assert "ws_clients" in body
    assert "watcher_running" in body
    assert "stale" in body
