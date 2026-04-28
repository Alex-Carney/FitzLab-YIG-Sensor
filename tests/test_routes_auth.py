import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def app_env(monkeypatch, synth_db_path):
    monkeypatch.setenv("YIG_DASHBOARD_PASSWORD", "hunter2")
    monkeypatch.setenv("YIG_DASHBOARD_SECRET", "s" * 32)
    monkeypatch.setenv("YIG_DB_PATH", str(synth_db_path))
    monkeypatch.setenv("YIG_COLLECTION_CADENCE_SEC", "1.0")
    monkeypatch.setenv("YIG_DEV_MODE", "1")
    from app.main import build_app
    return build_app()


@pytest.mark.asyncio
async def test_login_wrong_password(app_env):
    app = app_env
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            r = await c.post("/login", json={"password": "wrong"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_login_right_password_sets_cookie(app_env):
    app = app_env
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            r = await c.post("/login", json={"password": "hunter2"})
    assert r.status_code == 200
    set_cookie = r.headers.get("set-cookie", "")
    assert "yig_session=" in set_cookie


@pytest.mark.asyncio
async def test_logout_clears_cookie(app_env):
    app = app_env
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            await c.post("/login", json={"password": "hunter2"})
            r = await c.post("/logout")
    assert r.status_code == 200
    set_cookie = r.headers.get("set-cookie", "")
    assert "yig_session=" in set_cookie and "Max-Age=0" in set_cookie
