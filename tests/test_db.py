import datetime as dt

import pytest

from app.db import Database


def test_open_readonly(synth_db_path):
    db = Database(synth_db_path)
    db.connect()
    assert db.is_connected()
    db.close()


def test_latest_row(synth_db_path):
    db = Database(synth_db_path)
    db.connect()
    row = db.latest_row()
    db.close()
    assert row is not None
    assert "time_created" in row
    assert "center_freq" in row
    assert "span" in row
    assert "rbw" in row
    assert "n_points" in row
    assert "powers" in row
    assert isinstance(row["powers"], list)
    assert len(row["powers"]) == row["n_points"]


def test_latest_row_age_seconds(synth_db_path):
    db = Database(synth_db_path)
    db.connect()
    age = db.latest_row_age_seconds(now=dt.datetime(2026, 4, 27, 13, 0, 0))
    db.close()
    # Fixture starts at 12:00:00 with 600 rows at 1s cadence -> last row at 12:09:59
    # now is 13:00:00 -> age ~50 minutes 1 second
    assert 2900 < age < 3100


def test_count_rows(synth_db_path):
    db = Database(synth_db_path)
    db.connect()
    n = db.count_rows()
    db.close()
    assert n == 600


def test_rows_after(synth_db_path):
    db = Database(synth_db_path)
    db.connect()
    very_old = dt.datetime(2025, 1, 1)
    rows = db.rows_after(very_old, limit=5)
    db.close()
    assert len(rows) == 5
    times = [r["time_created"] for r in rows]
    assert times == sorted(times)


def test_range_rows_no_decimation(synth_db_path):
    db = Database(synth_db_path)
    db.connect()
    t0 = dt.datetime(2026, 4, 27, 12, 0, 0)
    t1 = dt.datetime(2026, 4, 27, 12, 0, 9)
    rows = db.range_rows(t0, t1, max_rows=2000)
    db.close()
    assert 9 <= len(rows) <= 11
    times = [r["time_created"] for r in rows]
    assert times == sorted(times)


def test_range_rows_with_decimation(synth_db_path):
    db = Database(synth_db_path)
    db.connect()
    t0 = dt.datetime(2026, 4, 27, 12, 0, 0)
    t1 = dt.datetime(2026, 4, 27, 12, 9, 59)  # all 600 rows
    rows = db.range_rows(t0, t1, max_rows=100)
    db.close()
    # stride = ceil(600/100) = 6 -> ~100 rows
    assert 90 <= len(rows) <= 100


def test_range_rows_full_window_no_cap(synth_db_path):
    db = Database(synth_db_path)
    db.connect()
    t0 = dt.datetime(2026, 4, 27, 12, 0, 0)
    t1 = dt.datetime(2026, 4, 27, 12, 9, 59)
    rows = db.range_rows(t0, t1, max_rows=10**9)
    db.close()
    assert len(rows) == 600


def test_peak_track_range_shape(synth_db_path):
    db = Database(synth_db_path)
    db.connect()
    t0 = dt.datetime(2026, 4, 27, 12, 0, 0)
    t1 = dt.datetime(2026, 4, 27, 12, 0, 9)
    pts = db.peak_track_range(t0, t1, max_rows=2000)
    db.close()
    assert len(pts) >= 9
    p = pts[0]
    assert "time_created" in p
    assert "peak_freq" in p
    assert "peak_power" in p
    assert "snr" in p
    assert "center_freq" in p
    assert p["snr"] > 0


def test_range_rows_empty_window(synth_db_path):
    db = Database(synth_db_path)
    db.connect()
    t0 = dt.datetime(2030, 1, 1)
    t1 = dt.datetime(2030, 1, 2)
    rows = db.range_rows(t0, t1, max_rows=100)
    db.close()
    assert rows == []
