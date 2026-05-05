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


def test_earliest_time_empty_db(tmp_path):
    """earliest_time returns None when there are no rows."""
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

    db = Database(p)
    db.connect()
    try:
        assert db.earliest_time() is None
    finally:
        db.close()


def test_earliest_time_with_rows(synth_db_path):
    """earliest_time returns the smallest time_created in the table."""
    db = Database(synth_db_path)
    db.connect()
    try:
        earliest = db.earliest_time()
        assert earliest is not None
        # synth fixture starts at 2026-04-27T12:00:00
        assert earliest == dt.datetime(2026, 4, 27, 12, 0, 0)
    finally:
        db.close()


def test_range_rows_no_freq_clipping_unchanged(synth_db_path):
    """range_rows with no freq params behaves exactly as before."""
    db = Database(synth_db_path)
    db.connect()
    try:
        earliest = db.earliest_time()
        rows = db.range_rows(earliest, earliest + dt.timedelta(hours=24), max_rows=50)
        assert len(rows) > 0
        for r in rows:
            assert r["n_points"] > 0
            assert len(r["powers"]) == r["n_points"]
    finally:
        db.close()


def test_range_rows_clips_to_freq_window(synth_db_path):
    """When freq window is narrower than sweep, rows return clipped powers
    with recomputed n_points/center_freq/span."""
    db = Database(synth_db_path)
    db.connect()
    try:
        earliest = db.earliest_time()
        sample = db.range_rows(earliest, earliest + dt.timedelta(hours=24), max_rows=1)[0]
        orig_center = sample["center_freq"]
        orig_span = sample["span"]
        orig_npts = sample["n_points"]
        # Clip to the middle 20% of the sweep
        f_lo = orig_center - orig_span * 0.1
        f_hi = orig_center + orig_span * 0.1
        rows = db.range_rows(
            earliest, earliest + dt.timedelta(hours=24), max_rows=50,
            freq_min_hz=f_lo, freq_max_hz=f_hi,
        )
        assert len(rows) > 0
        for r in rows:
            assert r["n_points"] < orig_npts
            assert r["n_points"] > 0
            assert len(r["powers"]) == r["n_points"]
            # Reconstructed axis must lie within [f_lo, f_hi]
            f0 = r["center_freq"] - r["span"] / 2
            f1 = r["center_freq"] + r["span"] / 2
            assert f0 >= f_lo - 1.0  # allow 1 Hz rounding tolerance
            assert f1 <= f_hi + 1.0
    finally:
        db.close()


def test_range_rows_skips_rows_outside_freq_window(synth_db_path):
    """Rows whose sweep doesn't intersect the freq window are dropped."""
    db = Database(synth_db_path)
    db.connect()
    try:
        earliest = db.earliest_time()
        rows = db.range_rows(
            earliest, earliest + dt.timedelta(hours=24), max_rows=50,
            freq_min_hz=1.0e15, freq_max_hz=1.0e15 + 1e6,
        )
        assert rows == []
    finally:
        db.close()


def test_range_rows_empty_db_returns_empty_list(tmp_path):
    """range_rows on an empty DB returns []."""
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

    db = Database(p)
    db.connect()
    try:
        rows = db.range_rows(
            dt.datetime(2026, 1, 1), dt.datetime(2026, 12, 31), max_rows=10
        )
        assert rows == []
    finally:
        db.close()
