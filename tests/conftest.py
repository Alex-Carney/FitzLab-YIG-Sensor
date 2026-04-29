"""Shared pytest fixtures for the YIG dashboard tests."""
from __future__ import annotations

import datetime as dt
import sqlite3
from pathlib import Path

import numpy as np
import pytest


sqlite3.register_adapter(dt.datetime, lambda d: d.isoformat(sep=" "))
sqlite3.register_converter(
    "TIMESTAMP", lambda b: dt.datetime.fromisoformat(b.decode("utf-8"))
)


N_POINTS = 201
SPAN_HZ = 5e6
RBW_HZ = 30e3
INITIAL_CENTER = 6.46335e9
DRIFT_HZ_PER_SEC = 5_000.0  # large so retunes fire within reasonable n_rows


def _synth_trace(center: float, peak_offset: float, rng: np.random.Generator) -> np.ndarray:
    """Generate a single power spectrum with a Gaussian peak + noise (dBm)."""
    freqs = np.linspace(center - SPAN_HZ / 2, center + SPAN_HZ / 2, N_POINTS)
    peak_freq = center + peak_offset
    sigma = 80e3
    peak_dbm = -30.0
    floor_dbm = -85.0
    powers = floor_dbm + (peak_dbm - floor_dbm) * np.exp(
        -((freqs - peak_freq) ** 2) / (2 * sigma**2)
    )
    powers += rng.normal(0.0, 1.5, size=N_POINTS)
    return powers.astype(np.float32)


def _populate(db_path: Path, n_rows: int = 600, cadence_sec: float = 1.0) -> None:
    """Synthetic YIG run: drift + retunes. Bulk-inserts via sqlite3."""
    conn = sqlite3.connect(str(db_path), detect_types=sqlite3.PARSE_DECLTYPES)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute(
        """
        CREATE TABLE spectra (
            time_created TIMESTAMP,
            center_freq  REAL,
            span         REAL,
            rbw          REAL,
            n_points     INTEGER,
            powers       BLOB
        )
        """
    )

    rng = np.random.default_rng(seed=42)
    start = dt.datetime(2026, 4, 27, 12, 0, 0)
    center = INITIAL_CENTER
    retune_threshold = 0.5 * (SPAN_HZ / 2)

    rows = []
    cumulative_offset = 0.0
    for i in range(n_rows):
        t = start + dt.timedelta(seconds=i * cadence_sec)
        cumulative_offset += DRIFT_HZ_PER_SEC * cadence_sec

        if abs(cumulative_offset) > retune_threshold:
            center = center + cumulative_offset
            cumulative_offset = 0.0

        powers = _synth_trace(center, cumulative_offset, rng)
        rows.append(
            (t, float(center), float(SPAN_HZ), float(RBW_HZ),
             int(N_POINTS), powers.astype("<f4").tobytes())
        )

    conn.executemany(
        "INSERT INTO spectra VALUES (?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_spectra_time ON spectra(time_created)")
    conn.commit()
    conn.close()


@pytest.fixture(scope="session")
def synth_db_path(tmp_path_factory) -> Path:
    """Read-only fixture DB shared across tests."""
    path = tmp_path_factory.mktemp("yig") / "synth.sqlite"
    _populate(path, n_rows=600, cadence_sec=1.0)
    return path


@pytest.fixture
def writable_db_path(tmp_path) -> Path:
    """A writable, isolated DB used by watcher tests that need to insert rows."""
    path = tmp_path / "writable.sqlite"
    _populate(path, n_rows=10, cadence_sec=1.0)
    return path
