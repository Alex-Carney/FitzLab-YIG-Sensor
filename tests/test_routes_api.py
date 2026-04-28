import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def app_with_session(monkeypatch, synth_db_path):
    monkeypatch.setenv("YIG_DASHBOARD_PASSWORD", "pw")
    monkeypatch.setenv("YIG_DASHBOARD_SECRET", "s" * 32)
    monkeypatch.setenv("YIG_DB_PATH", str(synth_db_path))
    monkeypatch.setenv("YIG_COLLECTION_CADENCE_SEC", "1.0")
    monkeypatch.setenv("YIG_DEV_MODE", "1")
    from app.main import build_app
    return build_app()


@pytest.mark.asyncio
async def test_snapshot_requires_auth(app_with_session):
    app = app_with_session
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            r = await c.get("/api/snapshot")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_snapshot_with_session(app_with_session):
    app = app_with_session
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            await c.post("/login", json={"password": "pw"})
            r = await c.get("/api/snapshot")
    assert r.status_code == 200
    body = r.json()
    assert "data" in body
    assert "powers" in body["data"]
    assert "center_freq" in body["data"]


@pytest.mark.asyncio
async def test_range_returns_rows(app_with_session):
    app = app_with_session
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            await c.post("/login", json={"password": "pw"})
            r = await c.get(
                "/api/range",
                params={
                    "from": "2026-04-27T12:00:00",
                    "to":   "2026-04-27T12:00:09",
                    "max_rows": 100,
                },
            )
    assert r.status_code == 200
    body = r.json()
    assert "rows" in body
    assert 9 <= len(body["rows"]) <= 11


@pytest.mark.asyncio
async def test_range_rejects_too_wide(app_with_session):
    app = app_with_session
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            await c.post("/login", json={"password": "pw"})
            r = await c.get(
                "/api/range",
                params={
                    "from": "2025-01-01T00:00:00",
                    "to":   "2026-04-27T12:00:00",
                    "max_rows": 100,
                },
            )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_peak_track_shape(app_with_session):
    app = app_with_session
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            await c.post("/login", json={"password": "pw"})
            r = await c.get(
                "/api/peak-track",
                params={
                    "from": "2026-04-27T12:00:00",
                    "to":   "2026-04-27T12:00:09",
                    "max_rows": 100,
                },
            )
    assert r.status_code == 200
    body = r.json()
    assert "rows" in body
    assert len(body["rows"]) >= 9
    p = body["rows"][0]
    assert "peak_freq" in p
    assert "peak_power" in p
    assert "snr" in p
    assert "center_freq" in p


@pytest.mark.asyncio
async def test_stats_shape(app_with_session):
    app = app_with_session
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            await c.post("/login", json={"password": "pw"})
            r = await c.get("/api/stats", params={"window": "1h"})
    assert r.status_code == 200
    body = r.json()
    assert "drift_rate_hz_per_hr" in body
    assert "seconds_since_last_retune" in body
    assert "traces_in_window" in body
    assert "current_snr_db" in body
