import datetime as dt

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


@pytest.mark.asyncio
async def test_range_endpoint_envelope_has_actual_from_to(app_with_session):
    app = app_with_session
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            await c.post("/login", json={"password": "pw"})
            r = await c.get("/api/range", params={
                "from": "2026-04-27T12:00:00",
                "to":   "2026-04-27T12:00:09",
            })
    assert r.status_code == 200
    body = r.json()
    for k in ("rows", "requested_from", "requested_to", "actual_from", "actual_to"):
        assert k in body, f"missing key {k}"


@pytest.mark.asyncio
async def test_range_endpoint_actual_from_clamps_to_earliest(app_with_session):
    """Requesting a window earlier than data returns actual_from = earliest."""
    app = app_with_session
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            await c.post("/login", json={"password": "pw"})
            r = await c.get("/api/range", params={
                "from": "2026-04-27T02:00:00",  # 10h before earliest
                "to":   "2026-04-27T13:00:00",
            })
    assert r.status_code == 200
    body = r.json()
    assert body["requested_from"].startswith("2026-04-27T02:00:00")
    assert body["actual_from"].startswith("2026-04-27T12:00:00")


@pytest.mark.asyncio
async def test_range_endpoint_freq_clipping(app_with_session):
    """freq_min_hz + freq_max_hz clip rows to the freq window."""
    app = app_with_session
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            await c.post("/login", json={"password": "pw"})
            # Synth fixture: center 6.46335e9, span 5e6, n_points 201.
            # Clip to middle 10% (~500 kHz around center).
            f_lo = 6.46335e9 - 250_000
            f_hi = 6.46335e9 + 250_000
            r = await c.get("/api/range", params={
                "from": "2026-04-27T12:00:00",
                "to":   "2026-04-27T12:00:09",
                "freq_min_hz": str(f_lo),
                "freq_max_hz": str(f_hi),
                "max_rows": "10",
            })
    assert r.status_code == 200
    body = r.json()
    assert len(body["rows"]) > 0
    for row in body["rows"]:
        assert row["n_points"] < 201
        assert len(row["powers"]) == row["n_points"]


@pytest.mark.asyncio
async def test_range_endpoint_only_one_freq_param_is_400(app_with_session):
    """Specifying freq_min_hz alone is rejected."""
    app = app_with_session
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            await c.post("/login", json={"password": "pw"})
            r = await c.get("/api/range", params={
                "from": "2026-04-27T12:00:00",
                "to":   "2026-04-27T12:00:09",
                "freq_min_hz": "1e9",
            })
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_range_endpoint_inverted_freq_window_is_400(app_with_session):
    """freq_min_hz > freq_max_hz is rejected."""
    app = app_with_session
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            await c.post("/login", json={"password": "pw"})
            r = await c.get("/api/range", params={
                "from": "2026-04-27T12:00:00",
                "to":   "2026-04-27T12:00:09",
                "freq_min_hz": "2e9",
                "freq_max_hz": "1e9",
            })
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_range_endpoint_nonfinite_freq_param_is_400(app_with_session):
    """NaN/Inf in freq params is rejected with 400 (not 500 from a math crash)."""
    app = app_with_session
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            await c.post("/login", json={"password": "pw"})
            for bad_min, bad_max in (("nan", "1e9"), ("1e9", "inf"), ("-inf", "inf")):
                r = await c.get("/api/range", params={
                    "from": "2026-04-27T12:00:00",
                    "to":   "2026-04-27T12:00:09",
                    "freq_min_hz": bad_min,
                    "freq_max_hz": bad_max,
                })
                assert r.status_code == 400, f"({bad_min}, {bad_max}) should be 400"


@pytest.mark.asyncio
async def test_range_endpoint_empty_db_envelope(tmp_path, monkeypatch):
    """On an empty DB, /api/range returns rows=[] and actual_from=None."""
    import sqlite3
    p = tmp_path / "empty.sqlite"
    conn = sqlite3.connect(str(p))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        "CREATE TABLE spectra (time_created TIMESTAMP, center_freq REAL, "
        "span REAL, rbw REAL, n_points INTEGER, powers BLOB)"
    )
    conn.commit()
    conn.close()

    monkeypatch.setenv("YIG_DASHBOARD_PASSWORD", "pw")
    monkeypatch.setenv("YIG_DASHBOARD_SECRET", "s" * 32)
    monkeypatch.setenv("YIG_DB_PATH", str(p))
    monkeypatch.setenv("YIG_COLLECTION_CADENCE_SEC", "1.0")
    monkeypatch.setenv("YIG_DEV_MODE", "1")
    from app.main import build_app
    app = build_app()

    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            await c.post("/login", json={"password": "pw"})
            r = await c.get("/api/range", params={
                "from": "2026-04-27T12:00:00",
                "to":   "2026-04-27T12:00:09",
            })
    assert r.status_code == 200
    body = r.json()
    assert body["rows"] == []
    assert body["actual_from"] is None
