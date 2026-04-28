import pytest

from app.config import Settings


def test_settings_required_fields(monkeypatch, tmp_path):
    monkeypatch.setenv("YIG_DASHBOARD_PASSWORD", "pw")
    monkeypatch.setenv("YIG_DASHBOARD_SECRET", "s" * 32)
    db = tmp_path / "x.duckdb"
    db.touch()
    monkeypatch.setenv("YIG_DB_PATH", str(db))
    monkeypatch.setenv("YIG_COLLECTION_CADENCE_SEC", "0.5")
    s = Settings.from_env()
    assert s.password == "pw"
    assert s.secret == "s" * 32
    assert s.db_path == db
    assert s.cadence_sec == 0.5
    assert s.dev_mode is False


def test_settings_dev_mode(monkeypatch, tmp_path):
    monkeypatch.setenv("YIG_DASHBOARD_PASSWORD", "pw")
    monkeypatch.setenv("YIG_DASHBOARD_SECRET", "s" * 32)
    db = tmp_path / "x.duckdb"
    db.touch()
    monkeypatch.setenv("YIG_DB_PATH", str(db))
    monkeypatch.setenv("YIG_COLLECTION_CADENCE_SEC", "1.0")
    monkeypatch.setenv("YIG_DEV_MODE", "1")
    s = Settings.from_env()
    assert s.dev_mode is True


def test_settings_missing_required(monkeypatch):
    monkeypatch.delenv("YIG_DASHBOARD_PASSWORD", raising=False)
    monkeypatch.delenv("YIG_DASHBOARD_SECRET", raising=False)
    with pytest.raises(RuntimeError, match="YIG_DASHBOARD_PASSWORD"):
        Settings.from_env()
