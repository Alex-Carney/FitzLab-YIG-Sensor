# YIG Streaming Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (inline) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a live web dashboard that streams YIG-oscillator spectra from `spectrum_data_ovn.duckdb` to a no-build Lit + Plotly frontend over REST + WebSocket, gated by a single shared password, deployable behind a Cloudflare Tunnel.

**Architecture:** FastAPI process (read-only DuckDB connection + polling watcher) serves both REST/WS endpoints and static frontend files. Tracker process is the only writer to DuckDB. Frontend is Lit web components consuming a small REST surface and a push-only WebSocket.

**Tech Stack:** Python 3.11 + FastAPI + uvicorn + DuckDB + numpy + python-dotenv + httpx (test) + websockets (test) + Lit (CDN) + Plotly (CDN).

**Spec:** `docs/superpowers/specs/2026-04-27-yig-streaming-dashboard-design.md`

---

## File Structure

```
FastAPIProject/
├── pyproject.toml                          (modify: add deps)
├── .env.example                            (create)
├── .gitignore                              (modify: add .env, *.duckdb)
├── README.md                               (create at end)
├── CLAUDE.md                               (create at end)
├── docs/
│   ├── future-ideas.md                     (existing)
│   └── superpowers/
│       ├── specs/2026-04-27-...md          (existing)
│       └── plans/2026-04-27-...md          (this file)
├── tracker/
│   └── duck_db_tracker.py                  (move from project root)
├── app/
│   ├── __init__.py
│   ├── main.py                             (replace existing main.py logic)
│   ├── config.py                           (env-var settings)
│   ├── db.py                               (read-only query layer)
│   ├── auth.py                             (HMAC cookie sessions)
│   ├── watcher.py                          (polling background task)
│   ├── ws_manager.py                       (WS connection set + broadcast)
│   ├── analytics.py                        (peak/SNR/stats computations)
│   └── routes/
│       ├── __init__.py
│       ├── health.py
│       ├── auth.py
│       ├── api.py
│       └── ws.py
├── frontend/
│   ├── index.html
│   ├── login.html
│   ├── styles.css
│   ├── lib/
│   │   ├── api.js
│   │   ├── ws-client.js
│   │   ├── store.js
│   │   └── plotly-theme.js
│   └── components/
│       ├── yig-app.js
│       ├── yig-header.js
│       ├── yig-live-trace.js
│       ├── yig-spectrogram.js
│       ├── yig-peak-track.js
│       ├── yig-peak-power.js
│       ├── yig-stats.js
│       └── yig-history-browser.js
├── scripts/
│   └── cleanup_old_data.py
├── cloudflared/
│   └── config.yml.example
└── tests/
    ├── __init__.py
    ├── conftest.py                          (synthetic DuckDB fixture)
    ├── test_db.py
    ├── test_auth.py
    ├── test_routes_health.py
    ├── test_routes_api.py
    ├── test_watcher.py
    └── test_ws.py
```

---

## Task 1: Project setup — dependencies and structure

**Files:**
- Modify: `pyproject.toml`
- Modify: `.gitignore` (or create at project root if missing)
- Create: `.env.example`
- Create: `tracker/__init__.py`
- Move: `duck_db_tracker.py` → `tracker/duck_db_tracker.py`
- Delete: `main.py` (will be replaced by `app/main.py`)
- Create: `app/__init__.py`
- Create: `app/routes/__init__.py`
- Create: `tests/__init__.py`

- [ ] **Step 1: Update `pyproject.toml`** — add the runtime + test dependencies.

```toml
[project]
name = "fastapiproject"
version = "0.1.0"
description = "YIG-based oscillator streaming dashboard"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.136.1",
    "uvicorn[standard]>=0.46.0",
    "duckdb>=1.0.0",
    "numpy>=1.26",
    "python-dotenv>=1.0",
    "pydantic>=2.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "httpx>=0.27",
    "websockets>=12.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["app", "tracker"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

- [ ] **Step 2: Update `.gitignore`** — append (or create) these lines.

```
# Python
__pycache__/
*.py[cod]
*.egg-info/
.pytest_cache/
.venv/

# Project
.env
*.duckdb
*.duckdb.wal
spectrogram.png

# IDE
.vscode/
```

- [ ] **Step 3: Create `.env.example`** — template for required env vars.

```
# Required
YIG_DASHBOARD_PASSWORD=changeme
YIG_DASHBOARD_SECRET=replace-with-32-bytes-of-random-hex
YIG_DB_PATH=spectrum_data_ovn.duckdb
YIG_COLLECTION_CADENCE_SEC=1.0

# Optional — set in local dev to allow non-HTTPS cookies
# YIG_DEV_MODE=1

# Optional — log level (default INFO)
# LOG_LEVEL=INFO
```

- [ ] **Step 4: Move tracker into its own package.**

```bash
mkdir -p tracker
git mv duck_db_tracker.py tracker/duck_db_tracker.py
```

Create `tracker/__init__.py` (empty file).

- [ ] **Step 5: Create empty package `__init__.py` files.**

Create `app/__init__.py`, `app/routes/__init__.py`, `tests/__init__.py`. All empty.

- [ ] **Step 6: Delete the placeholder `main.py`.**

```bash
rm main.py
```

- [ ] **Step 7: Install deps and verify environment.**

```bash
uv sync --all-extras
```

Expected: dependency resolution completes, `uv.lock` updates, no errors.

- [ ] **Step 8: Commit.**

```bash
git add pyproject.toml .gitignore .env.example tracker/ app/ tests/
git rm main.py duck_db_tracker.py
git commit -m "chore: scaffold app/tracker/tests packages and add deps"
```

---

## Task 2: Synthetic DuckDB fixture (`tests/conftest.py`)

**Files:**
- Create: `tests/conftest.py`
- Test: `tests/test_fixture_smoke.py` (delete at end of task)

The fixture generates a temporary DuckDB file populated with realistic YIG data: slow drift + occasional retunes + Gaussian peak + noise. Used by every later test.

- [ ] **Step 1: Write the failing smoke test.**

Create `tests/test_fixture_smoke.py`:

```python
import duckdb


def test_synth_db_has_rows(synth_db_path):
    conn = duckdb.connect(str(synth_db_path), read_only=True)
    n = conn.execute("SELECT count(*) FROM spectra").fetchone()[0]
    conn.close()
    assert n >= 60, f"expected at least 60 rows, got {n}"


def test_synth_db_has_retunes(synth_db_path):
    conn = duckdb.connect(str(synth_db_path), read_only=True)
    centers = conn.execute("SELECT DISTINCT center_freq FROM spectra").fetchall()
    conn.close()
    assert len(centers) >= 2, "expected at least one retune in fixture"


def test_synth_db_powers_array_length(synth_db_path):
    conn = duckdb.connect(str(synth_db_path), read_only=True)
    row = conn.execute(
        "SELECT n_points, len(powers) FROM spectra LIMIT 1"
    ).fetchone()
    conn.close()
    assert row[0] == row[1], "n_points must match len(powers)"
```

- [ ] **Step 2: Run the test to verify it fails.**

Run: `pytest tests/test_fixture_smoke.py -v`
Expected: FAIL with "fixture 'synth_db_path' not found".

- [ ] **Step 3: Implement `tests/conftest.py`.**

```python
"""Shared pytest fixtures for the YIG dashboard tests."""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import duckdb
import numpy as np
import pytest


N_POINTS = 501
SPAN_HZ = 5e6
RBW_HZ = 30e3
INITIAL_CENTER = 6.46335e9


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
    """Synthetic YIG run: slow linear drift, two retunes."""
    conn = duckdb.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE spectra (
            time_created TIMESTAMP,
            center_freq  DOUBLE,
            span         DOUBLE,
            rbw          DOUBLE,
            n_points     INTEGER,
            powers       FLOAT[]
        )
        """
    )

    rng = np.random.default_rng(seed=42)
    start = dt.datetime(2026, 4, 27, 12, 0, 0)
    center = INITIAL_CENTER
    drift_hz_per_sec = 30.0  # 108 kHz/hour
    retune_threshold = 0.5 * (SPAN_HZ / 2)

    rows = []
    cumulative_offset = 0.0
    for i in range(n_rows):
        t = start + dt.timedelta(seconds=i * cadence_sec)
        cumulative_offset += drift_hz_per_sec * cadence_sec

        # Retune logic: if drift exceeds threshold, recenter.
        if abs(cumulative_offset) > retune_threshold:
            center = center + cumulative_offset
            cumulative_offset = 0.0

        powers = _synth_trace(center, cumulative_offset, rng)
        rows.append(
            (t, float(center), float(SPAN_HZ), float(RBW_HZ),
             int(N_POINTS), powers.tolist())
        )

    conn.executemany(
        "INSERT INTO spectra VALUES (?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_spectra_time ON spectra(time_created)")
    conn.close()


@pytest.fixture(scope="session")
def synth_db_path(tmp_path_factory) -> Path:
    """Read-only fixture DB shared across tests."""
    path = tmp_path_factory.mktemp("yig") / "synth.duckdb"
    _populate(path, n_rows=600, cadence_sec=1.0)
    return path


@pytest.fixture
def writable_db_path(tmp_path) -> Path:
    """A writable, isolated DB used by watcher tests that need to insert rows."""
    path = tmp_path / "writable.duckdb"
    _populate(path, n_rows=10, cadence_sec=1.0)
    return path
```

- [ ] **Step 4: Run smoke tests.**

Run: `pytest tests/test_fixture_smoke.py -v`
Expected: 3 PASS.

- [ ] **Step 5: Delete the smoke test file.** Its only purpose was to drive the fixture; we don't need it long-term.

```bash
rm tests/test_fixture_smoke.py
```

- [ ] **Step 6: Commit.**

```bash
git add tests/conftest.py
git commit -m "test: add synthetic DuckDB fixture with drift + retunes"
```

---

## Task 3: Config module (`app/config.py`)

**Files:**
- Create: `app/config.py`
- Test: `tests/test_config.py`

Loads env vars (via `python-dotenv`) into a frozen settings object.

- [ ] **Step 1: Write the failing test.**

Create `tests/test_config.py`:

```python
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
```

- [ ] **Step 2: Run test to verify failure.**

Run: `pytest tests/test_config.py -v`
Expected: FAIL with "No module named 'app.config'".

- [ ] **Step 3: Implement `app/config.py`.**

```python
"""Settings loaded from environment variables."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    password: str
    secret: str
    db_path: Path
    cadence_sec: float
    dev_mode: bool
    log_level: str
    cookie_name: str = "yig_session"
    cookie_max_age_sec: int = 30 * 24 * 3600
    range_max_days: int = 7
    api_max_rows_default: int = 2000
    api_max_rows_hard_cap: int = 10000
    ws_ping_interval_sec: float = 30.0
    db_connect_max_wait_sec: float = 300.0

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv(override=False)

        password = os.environ.get("YIG_DASHBOARD_PASSWORD")
        if not password:
            raise RuntimeError("YIG_DASHBOARD_PASSWORD is required")
        secret = os.environ.get("YIG_DASHBOARD_SECRET")
        if not secret:
            raise RuntimeError("YIG_DASHBOARD_SECRET is required")
        if len(secret) < 16:
            raise RuntimeError("YIG_DASHBOARD_SECRET must be at least 16 chars")

        db_path_str = os.environ.get("YIG_DB_PATH", "spectrum_data_ovn.duckdb")
        cadence = float(os.environ.get("YIG_COLLECTION_CADENCE_SEC", "1.0"))
        dev_mode = os.environ.get("YIG_DEV_MODE", "").strip() not in ("", "0", "false", "False")
        log_level = os.environ.get("LOG_LEVEL", "INFO")

        return cls(
            password=password,
            secret=secret,
            db_path=Path(db_path_str),
            cadence_sec=cadence,
            dev_mode=dev_mode,
            log_level=log_level,
        )
```

- [ ] **Step 4: Run test to verify pass.**

Run: `pytest tests/test_config.py -v`
Expected: 3 PASS.

- [ ] **Step 5: Commit.**

```bash
git add app/config.py tests/test_config.py
git commit -m "feat(config): load settings from env with validation"
```

---

## Task 4: DB module (`app/db.py`) — connection + simple queries

**Files:**
- Create: `app/db.py`
- Test: `tests/test_db.py`

This task covers connection management and the simplest queries: latest snapshot and row count. Range/peak-track come in Task 5 to keep tasks bite-sized.

- [ ] **Step 1: Write the failing test.**

Create `tests/test_db.py`:

```python
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
    # Fixture starts at 12:00:00 with 600 rows at 1s cadence → last row at 12:09:59
    # now is 13:00:00 → age ≈ 50 minutes 1 second
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
    # Get first row
    first = db.latest_row()  # latest is most recent
    # ask for rows after a time well before first row
    very_old = dt.datetime(2025, 1, 1)
    rows = db.rows_after(very_old, limit=5)
    db.close()
    assert len(rows) == 5
    # rows must be sorted ascending by time_created
    times = [r["time_created"] for r in rows]
    assert times == sorted(times)
```

- [ ] **Step 2: Run test to verify failure.**

Run: `pytest tests/test_db.py -v`
Expected: FAIL with "No module named 'app.db'".

- [ ] **Step 3: Implement `app/db.py`.**

```python
"""Read-only DuckDB access layer.

The API process opens DuckDB with read_only=True. The tracker is the only writer.
Connections are opened lazily and held for the lifetime of the process.
"""
from __future__ import annotations

import datetime as dt
import logging
import time
from pathlib import Path
from typing import Optional

import duckdb

logger = logging.getLogger("yig.db")


class Database:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._conn: Optional[duckdb.DuckDBPyConnection] = None

    def connect(self, max_wait_sec: float = 300.0) -> None:
        """Open a read-only connection, retrying with backoff if locked."""
        deadline = time.monotonic() + max_wait_sec
        delay = 1.0
        last_err: Optional[Exception] = None
        while time.monotonic() < deadline:
            try:
                self._conn = duckdb.connect(str(self.path), read_only=True)
                logger.info("opened read-only connection to %s", self.path)
                return
            except (duckdb.IOException, duckdb.Error) as e:
                last_err = e
                logger.warning("DB connect failed (%s); retrying in %.1fs", e, delay)
                time.sleep(delay)
                delay = min(delay * 2, 30.0)
        raise RuntimeError(f"Could not open DB at {self.path}: {last_err}")

    def is_connected(self) -> bool:
        return self._conn is not None

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def _row_to_dict(self, row, cols: list[str]) -> dict:
        return {c: v for c, v in zip(cols, row)}

    def latest_row(self) -> Optional[dict]:
        assert self._conn is not None
        cols = ["time_created", "center_freq", "span", "rbw", "n_points", "powers"]
        row = self._conn.execute(
            f"SELECT {', '.join(cols)} FROM spectra "
            "ORDER BY time_created DESC LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        return self._row_to_dict(row, cols)

    def latest_row_age_seconds(self, now: Optional[dt.datetime] = None) -> Optional[float]:
        assert self._conn is not None
        row = self._conn.execute(
            "SELECT time_created FROM spectra ORDER BY time_created DESC LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        if now is None:
            now = dt.datetime.now()
        return (now - row[0]).total_seconds()

    def count_rows(self) -> int:
        assert self._conn is not None
        return self._conn.execute("SELECT count(*) FROM spectra").fetchone()[0]

    def rows_after(self, after: dt.datetime, limit: int = 200) -> list[dict]:
        """Rows strictly newer than `after`, ascending, capped at `limit`."""
        assert self._conn is not None
        cols = ["time_created", "center_freq", "span", "rbw", "n_points", "powers"]
        rows = self._conn.execute(
            f"SELECT {', '.join(cols)} FROM spectra "
            "WHERE time_created > ? ORDER BY time_created ASC LIMIT ?",
            [after, limit],
        ).fetchall()
        return [self._row_to_dict(r, cols) for r in rows]
```

- [ ] **Step 4: Run test to verify pass.**

Run: `pytest tests/test_db.py -v`
Expected: 5 PASS.

- [ ] **Step 5: Commit.**

```bash
git add app/db.py tests/test_db.py
git commit -m "feat(db): add read-only DuckDB layer with latest/rows_after/count"
```

---

## Task 5: DB module — range queries with stride decimation

**Files:**
- Modify: `app/db.py`
- Modify: `tests/test_db.py`

Add `range_rows()` (full traces) and `peak_track_range()` (computed peak/SNR/center) with server-side stride decimation.

- [ ] **Step 1: Add failing tests for range queries.**

Append to `tests/test_db.py`:

```python
def test_range_rows_no_decimation(synth_db_path):
    db = Database(synth_db_path)
    db.connect()
    # Fixture: 600 rows starting at 12:00:00, 1s cadence
    t0 = dt.datetime(2026, 4, 27, 12, 0, 0)
    t1 = dt.datetime(2026, 4, 27, 12, 0, 9)  # inclusive of 10 seconds → 10 rows
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
    # stride = ceil(600/100) = 6 → ~100 rows
    assert 90 <= len(rows) <= 100


def test_range_rows_caps_max_rows_at_hard_limit(synth_db_path):
    db = Database(synth_db_path)
    db.connect()
    t0 = dt.datetime(2026, 4, 27, 12, 0, 0)
    t1 = dt.datetime(2026, 4, 27, 12, 9, 59)
    rows = db.range_rows(t0, t1, max_rows=10**9)  # extreme request
    db.close()
    # Caller passes hard cap from config; db layer should respect what it gets
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
    # SNR should be a positive number for our synthetic peaked data
    assert p["snr"] > 0


def test_range_rows_empty_window(synth_db_path):
    db = Database(synth_db_path)
    db.connect()
    t0 = dt.datetime(2030, 1, 1)
    t1 = dt.datetime(2030, 1, 2)
    rows = db.range_rows(t0, t1, max_rows=100)
    db.close()
    assert rows == []
```

- [ ] **Step 2: Run tests to verify failure.**

Run: `pytest tests/test_db.py -v`
Expected: 5 OLD pass, 5 NEW FAIL with "no attribute 'range_rows'".

- [ ] **Step 3: Append range methods to `app/db.py`.**

Add to the `Database` class:

```python
    def range_rows(
        self,
        t_from: dt.datetime,
        t_to: dt.datetime,
        max_rows: int = 2000,
    ) -> list[dict]:
        """Full traces between t_from and t_to (inclusive), stride-decimated to <=max_rows."""
        assert self._conn is not None
        cols = ["time_created", "center_freq", "span", "rbw", "n_points", "powers"]

        total = self._conn.execute(
            "SELECT count(*) FROM spectra WHERE time_created BETWEEN ? AND ?",
            [t_from, t_to],
        ).fetchone()[0]
        if total == 0:
            return []

        stride = max(1, (total + max_rows - 1) // max_rows)
        rows = self._conn.execute(
            f"""
            SELECT {", ".join(cols)} FROM (
                SELECT {", ".join(cols)},
                       row_number() OVER (ORDER BY time_created) AS rn
                FROM spectra
                WHERE time_created BETWEEN ? AND ?
            )
            WHERE (rn - 1) % ? = 0
            ORDER BY time_created
            """,
            [t_from, t_to, stride],
        ).fetchall()
        return [self._row_to_dict(r, cols) for r in rows]

    def peak_track_range(
        self,
        t_from: dt.datetime,
        t_to: dt.datetime,
        max_rows: int = 2000,
    ) -> list[dict]:
        """Per-row (t, peak_freq, peak_power, snr, center_freq), stride-decimated.

        Computed in DuckDB via list_aggregate and list lookups so we don't ship
        full power arrays back from the server.
        """
        assert self._conn is not None
        total = self._conn.execute(
            "SELECT count(*) FROM spectra WHERE time_created BETWEEN ? AND ?",
            [t_from, t_to],
        ).fetchone()[0]
        if total == 0:
            return []

        stride = max(1, (total + max_rows - 1) // max_rows)

        # We compute peak index, peak power, median power, and the matching frequency
        # on the server. Frequency axis is reconstructed as
        #   peak_freq = center_freq - span/2 + (peak_idx) * span / (n_points - 1)
        rows = self._conn.execute(
            """
            SELECT
                time_created,
                center_freq,
                span,
                n_points,
                list_aggregate(powers, 'max')                AS peak_power,
                list_aggregate(powers, 'median')             AS median_power,
                list_position(powers, list_aggregate(powers, 'max')) - 1 AS peak_idx
            FROM (
                SELECT *,
                       row_number() OVER (ORDER BY time_created) AS rn
                FROM spectra
                WHERE time_created BETWEEN ? AND ?
            )
            WHERE (rn - 1) % ? = 0
            ORDER BY time_created
            """,
            [t_from, t_to, stride],
        ).fetchall()

        out = []
        for t, center, span, n_pts, peak_p, med_p, peak_idx in rows:
            if n_pts is None or n_pts <= 1:
                continue
            peak_freq = center - span / 2 + peak_idx * span / (n_pts - 1)
            out.append({
                "time_created": t,
                "center_freq": center,
                "peak_freq": peak_freq,
                "peak_power": peak_p,
                "snr": peak_p - med_p,
            })
        return out
```

- [ ] **Step 4: Run tests to verify pass.**

Run: `pytest tests/test_db.py -v`
Expected: 10 PASS.

- [ ] **Step 5: Commit.**

```bash
git add app/db.py tests/test_db.py
git commit -m "feat(db): add range_rows and peak_track_range with stride decimation"
```

---

## Task 6: Auth module (`app/auth.py`)

**Files:**
- Create: `app/auth.py`
- Test: `tests/test_auth.py`

HMAC-signed cookie sessions. No JWT library. Cookie format: `<base64-payload>.<base64-signature>`. Payload is JSON `{"exp": <unix_ts>}`.

- [ ] **Step 1: Write the failing test.**

Create `tests/test_auth.py`:

```python
import time

import pytest

from app.auth import (
    SessionInvalidError,
    make_session_cookie,
    verify_session_cookie,
    verify_password,
)


SECRET = "x" * 32


def test_make_and_verify_session():
    cookie = make_session_cookie(SECRET, ttl_sec=3600)
    payload = verify_session_cookie(SECRET, cookie)
    assert "exp" in payload
    assert payload["exp"] > int(time.time())


def test_verify_session_rejects_tampered():
    cookie = make_session_cookie(SECRET, ttl_sec=3600)
    head, sig = cookie.split(".")
    # mutate one char of the signature
    bad = head + "." + ("A" if sig[0] != "A" else "B") + sig[1:]
    with pytest.raises(SessionInvalidError):
        verify_session_cookie(SECRET, bad)


def test_verify_session_rejects_expired():
    cookie = make_session_cookie(SECRET, ttl_sec=-10)
    with pytest.raises(SessionInvalidError, match="expired"):
        verify_session_cookie(SECRET, cookie)


def test_verify_session_rejects_garbage():
    with pytest.raises(SessionInvalidError):
        verify_session_cookie(SECRET, "garbage")
    with pytest.raises(SessionInvalidError):
        verify_session_cookie(SECRET, "")


def test_verify_session_rejects_wrong_secret():
    cookie = make_session_cookie(SECRET, ttl_sec=3600)
    with pytest.raises(SessionInvalidError):
        verify_session_cookie("y" * 32, cookie)


def test_verify_password_constant_time():
    assert verify_password("hunter2", "hunter2") is True
    assert verify_password("hunter2", "wrong") is False
    assert verify_password("hunter2", "") is False
```

- [ ] **Step 2: Run test to verify failure.**

Run: `pytest tests/test_auth.py -v`
Expected: FAIL with "No module named 'app.auth'".

- [ ] **Step 3: Implement `app/auth.py`.**

```python
"""HMAC-signed cookie sessions.

Cookie format: <base64-payload>.<base64-signature>
Payload (JSON): {"exp": <unix_ts>}
Signature: HMAC-SHA256(secret, payload).hex
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Optional

from fastapi import Cookie, HTTPException, Request, status


class SessionInvalidError(Exception):
    pass


def _b64url_encode(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def _sign(secret: str, payload_b64: str) -> str:
    sig = hmac.new(
        secret.encode("utf-8"),
        payload_b64.encode("ascii"),
        hashlib.sha256,
    ).hexdigest()
    return sig


def make_session_cookie(secret: str, ttl_sec: int) -> str:
    payload = {"exp": int(time.time()) + ttl_sec}
    payload_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    payload_b64 = _b64url_encode(payload_bytes)
    sig = _sign(secret, payload_b64)
    return f"{payload_b64}.{sig}"


def verify_session_cookie(secret: str, cookie: Optional[str]) -> dict:
    if not cookie or "." not in cookie:
        raise SessionInvalidError("malformed cookie")
    payload_b64, sig = cookie.rsplit(".", 1)
    expected = _sign(secret, payload_b64)
    if not hmac.compare_digest(sig, expected):
        raise SessionInvalidError("bad signature")
    try:
        payload_bytes = _b64url_decode(payload_b64)
        payload = json.loads(payload_bytes.decode("utf-8"))
    except (ValueError, json.JSONDecodeError):
        raise SessionInvalidError("malformed payload")
    if "exp" not in payload or int(payload["exp"]) < int(time.time()):
        raise SessionInvalidError("expired")
    return payload


def verify_password(expected: str, given: str) -> bool:
    return hmac.compare_digest(expected.encode("utf-8"), given.encode("utf-8"))


# ----------------------------------------------------------------------
# FastAPI dependency
# ----------------------------------------------------------------------

def require_session_factory(secret: str, cookie_name: str = "yig_session"):
    """Return a FastAPI dependency that enforces a valid session cookie."""

    def dependency(request: Request) -> dict:
        cookie = request.cookies.get(cookie_name)
        try:
            return verify_session_cookie(secret, cookie)
        except SessionInvalidError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=str(e),
                headers={"WWW-Authenticate": 'Cookie realm="yig"'},
            )

    return dependency
```

- [ ] **Step 4: Run tests to verify pass.**

Run: `pytest tests/test_auth.py -v`
Expected: 6 PASS.

- [ ] **Step 5: Commit.**

```bash
git add app/auth.py tests/test_auth.py
git commit -m "feat(auth): HMAC-signed cookie sessions and password verify"
```

---

## Task 7: Analytics module (`app/analytics.py`)

**Files:**
- Create: `app/analytics.py`
- Test: `tests/test_analytics.py`

Pure-Python helpers used by `/api/stats` and the watcher: drift rate, time since last retune, current SNR.

- [ ] **Step 1: Write the failing test.**

Create `tests/test_analytics.py`:

```python
import datetime as dt

from app.analytics import (
    compute_drift_rate_hz_per_hr,
    seconds_since_last_retune,
)


def test_drift_rate_zero_for_constant():
    times = [dt.datetime(2026, 4, 27, 12, 0, i) for i in range(10)]
    peaks = [6.46e9 for _ in range(10)]
    rate = compute_drift_rate_hz_per_hr(times, peaks)
    assert abs(rate) < 1e-3


def test_drift_rate_positive_for_upward_drift():
    times = [dt.datetime(2026, 4, 27, 12, 0, i) for i in range(10)]
    # +1 kHz/sec → 3.6 MHz/hour
    peaks = [6.46e9 + 1e3 * i for i in range(10)]
    rate = compute_drift_rate_hz_per_hr(times, peaks)
    assert 3.5e6 < rate < 3.7e6


def test_drift_rate_handles_short_series():
    assert compute_drift_rate_hz_per_hr([], []) == 0.0
    one = [dt.datetime(2026, 4, 27, 12, 0, 0)]
    assert compute_drift_rate_hz_per_hr(one, [6.46e9]) == 0.0


def test_seconds_since_last_retune_no_retune():
    times = [dt.datetime(2026, 4, 27, 12, 0, i) for i in range(10)]
    centers = [6.46e9] * 10
    now = dt.datetime(2026, 4, 27, 12, 0, 9)
    s = seconds_since_last_retune(times, centers, now=now)
    # No retune ever → return age of first row
    assert s == 9.0


def test_seconds_since_last_retune_finds_jump():
    times = [dt.datetime(2026, 4, 27, 12, 0, i) for i in range(10)]
    centers = [6.46e9] * 5 + [6.47e9] * 5
    now = dt.datetime(2026, 4, 27, 12, 0, 9)
    s = seconds_since_last_retune(times, centers, now=now)
    # Retune at i=5 (12:00:05). now=12:00:09 → 4s
    assert s == 4.0
```

- [ ] **Step 2: Run test to verify failure.**

Run: `pytest tests/test_analytics.py -v`
Expected: FAIL with "No module named 'app.analytics'".

- [ ] **Step 3: Implement `app/analytics.py`.**

```python
"""Pure helpers for derived metrics."""
from __future__ import annotations

import datetime as dt
import math
from typing import Iterable


def compute_drift_rate_hz_per_hr(
    times: list[dt.datetime],
    peak_freqs_hz: list[float],
) -> float:
    """Linear least-squares fit of peak frequency vs time, returned as Hz/hr.

    Returns 0.0 if fewer than two points or if all timestamps coincide.
    """
    n = len(times)
    if n < 2 or n != len(peak_freqs_hz):
        return 0.0

    t0 = times[0]
    xs = [(t - t0).total_seconds() for t in times]
    ys = peak_freqs_hz

    if max(xs) == 0:
        return 0.0

    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((xs[i] - mx) * (ys[i] - my) for i in range(n))
    den = sum((xs[i] - mx) ** 2 for i in range(n))
    if den == 0:
        return 0.0
    slope_hz_per_sec = num / den
    return slope_hz_per_sec * 3600.0


def seconds_since_last_retune(
    times: list[dt.datetime],
    centers: list[float],
    now: dt.datetime,
    eps_hz: float = 1.0,
) -> float:
    """Seconds between the last center_freq change and `now`.

    If no retune is observed in the window, returns the time between
    the earliest sample and `now` (i.e., 'at least this long').
    """
    if not times or len(times) != len(centers):
        return 0.0
    last_change = times[0]
    for i in range(1, len(times)):
        if abs(centers[i] - centers[i - 1]) > eps_hz:
            last_change = times[i]
    return (now - last_change).total_seconds()
```

- [ ] **Step 4: Run tests to verify pass.**

Run: `pytest tests/test_analytics.py -v`
Expected: 5 PASS.

- [ ] **Step 5: Commit.**

```bash
git add app/analytics.py tests/test_analytics.py
git commit -m "feat(analytics): drift rate + last-retune helpers"
```

---

## Task 8: WebSocket connection manager (`app/ws_manager.py`)

**Files:**
- Create: `app/ws_manager.py`
- Test: `tests/test_ws_manager.py`

Holds the set of connected clients and broadcasts JSON payloads to all of them with `asyncio.gather(..., return_exceptions=True)`.

- [ ] **Step 1: Write the failing test.**

Create `tests/test_ws_manager.py`:

```python
import asyncio

import pytest

from app.ws_manager import ConnectionManager


class FakeWS:
    def __init__(self, fail: bool = False):
        self.sent: list = []
        self.fail = fail
        self.closed = False

    async def send_json(self, data):
        if self.fail:
            raise RuntimeError("fake disconnect")
        self.sent.append(data)


@pytest.mark.asyncio
async def test_connect_disconnect_count():
    mgr = ConnectionManager()
    a = FakeWS()
    b = FakeWS()
    mgr.add(a)
    mgr.add(b)
    assert mgr.count() == 2
    mgr.remove(a)
    assert mgr.count() == 1


@pytest.mark.asyncio
async def test_broadcast_sends_to_all():
    mgr = ConnectionManager()
    a = FakeWS()
    b = FakeWS()
    mgr.add(a)
    mgr.add(b)
    await mgr.broadcast({"type": "trace", "data": {"x": 1}})
    assert a.sent == [{"type": "trace", "data": {"x": 1}}]
    assert b.sent == [{"type": "trace", "data": {"x": 1}}]


@pytest.mark.asyncio
async def test_broadcast_prunes_failed_clients():
    mgr = ConnectionManager()
    good = FakeWS()
    bad = FakeWS(fail=True)
    mgr.add(good)
    mgr.add(bad)
    await mgr.broadcast({"type": "ping"})
    assert good.sent == [{"type": "ping"}]
    # The failing client should have been removed
    assert mgr.count() == 1
```

- [ ] **Step 2: Run test to verify failure.**

Run: `pytest tests/test_ws_manager.py -v`
Expected: FAIL with "No module named 'app.ws_manager'".

- [ ] **Step 3: Implement `app/ws_manager.py`.**

```python
"""WebSocket connection set and broadcaster."""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Protocol

logger = logging.getLogger("yig.ws")


class _Sendable(Protocol):
    async def send_json(self, data: Any) -> None: ...


class ConnectionManager:
    def __init__(self) -> None:
        self._clients: set[_Sendable] = set()
        self._lock = asyncio.Lock()

    def add(self, ws: _Sendable) -> None:
        self._clients.add(ws)

    def remove(self, ws: _Sendable) -> None:
        self._clients.discard(ws)

    def count(self) -> int:
        return len(self._clients)

    async def broadcast(self, payload: Any) -> None:
        if not self._clients:
            return
        clients = list(self._clients)

        async def _safe_send(ws: _Sendable) -> _Sendable | None:
            try:
                await ws.send_json(payload)
                return None
            except Exception as e:  # noqa: BLE001 — any exception removes the client
                logger.warning("WS send failed (%s); pruning", e)
                return ws

        results = await asyncio.gather(
            *(_safe_send(c) for c in clients),
            return_exceptions=False,
        )
        for dead in results:
            if dead is not None:
                self.remove(dead)
```

- [ ] **Step 4: Run tests to verify pass.**

Run: `pytest tests/test_ws_manager.py -v`
Expected: 3 PASS.

- [ ] **Step 5: Commit.**

```bash
git add app/ws_manager.py tests/test_ws_manager.py
git commit -m "feat(ws): connection manager with broadcast and dead-client pruning"
```

---

## Task 9: Polling watcher (`app/watcher.py`)

**Files:**
- Create: `app/watcher.py`
- Test: `tests/test_watcher.py`

Background task: every cadence, polls `db.rows_after(last_seen)` and forwards new rows through the connection manager.

- [ ] **Step 1: Write the failing test.**

Create `tests/test_watcher.py`:

```python
import asyncio
import datetime as dt

import duckdb
import numpy as np
import pytest

from app.db import Database
from app.watcher import PollingWatcher
from app.ws_manager import ConnectionManager


class CapturingWS:
    def __init__(self):
        self.sent = []

    async def send_json(self, data):
        self.sent.append(data)


def _append_row(path, t, center=6.46e9, span=5e6, n_points=51):
    conn = duckdb.connect(str(path))
    powers = np.linspace(-80, -30, n_points).astype(np.float32)
    conn.execute(
        "INSERT INTO spectra VALUES (?, ?, ?, ?, ?, ?)",
        [t, center, span, 30e3, n_points, powers.tolist()],
    )
    conn.close()


@pytest.mark.asyncio
async def test_watcher_broadcasts_new_rows(writable_db_path):
    db = Database(writable_db_path)
    db.connect()
    mgr = ConnectionManager()
    ws = CapturingWS()
    mgr.add(ws)

    # latest age before
    last = db.latest_row()
    last_t = last["time_created"]

    watcher = PollingWatcher(db=db, manager=mgr, cadence_sec=0.05)
    task = asyncio.create_task(watcher.run())
    try:
        # let the watcher settle (one tick)
        await asyncio.sleep(0.1)
        assert ws.sent == []  # nothing new yet

        # insert a new row strictly after last_t
        _append_row(writable_db_path, last_t + dt.timedelta(seconds=1))

        # wait for next tick
        await asyncio.sleep(0.2)
    finally:
        watcher.stop()
        await asyncio.wait_for(task, timeout=1.0)
        db.close()

    assert len(ws.sent) >= 1
    msg = ws.sent[-1]
    assert msg["type"] == "trace"
    assert "data" in msg
    assert "powers" in msg["data"]
    assert "center_freq" in msg["data"]


@pytest.mark.asyncio
async def test_watcher_survives_db_error(writable_db_path):
    """If a poll raises, watcher logs and continues."""
    db = Database(writable_db_path)
    db.connect()

    # Patch rows_after to raise once, then behave
    calls = {"n": 0}
    real = db.rows_after

    def flaky(after, limit=200):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("boom")
        return real(after, limit=limit)

    db.rows_after = flaky  # type: ignore[method-assign]

    mgr = ConnectionManager()
    watcher = PollingWatcher(db=db, manager=mgr, cadence_sec=0.05)
    task = asyncio.create_task(watcher.run())
    try:
        await asyncio.sleep(0.2)
    finally:
        watcher.stop()
        await asyncio.wait_for(task, timeout=1.0)
        db.close()

    # We should see at least 2 calls — proof the watcher kept ticking after the error
    assert calls["n"] >= 2
```

- [ ] **Step 2: Run test to verify failure.**

Run: `pytest tests/test_watcher.py -v`
Expected: FAIL with "No module named 'app.watcher'".

- [ ] **Step 3: Implement `app/watcher.py`.**

```python
"""Background polling watcher.

Lives as a long-running asyncio task started in FastAPI's `lifespan`. Polls
`db.rows_after(last_seen)` at `cadence_sec`, broadcasts new rows to all
connected WebSocket clients, and never tears down on a single error.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import logging
from typing import Optional

from app.db import Database
from app.ws_manager import ConnectionManager

logger = logging.getLogger("yig.watcher")


def _row_to_payload(row: dict) -> dict:
    """Convert a DB row (with datetime) into a JSON-serialisable trace payload."""
    return {
        "type": "trace",
        "data": {
            "t": row["time_created"].isoformat(),
            "center_freq": float(row["center_freq"]),
            "span": float(row["span"]),
            "rbw": float(row["rbw"]),
            "n_points": int(row["n_points"]),
            "powers": [float(x) for x in row["powers"]],
        },
    }


class PollingWatcher:
    def __init__(
        self,
        db: Database,
        manager: ConnectionManager,
        cadence_sec: float,
        batch_size: int = 200,
    ):
        self.db = db
        self.manager = manager
        self.cadence_sec = max(0.01, float(cadence_sec))
        self.batch_size = batch_size
        self._stop = asyncio.Event()
        self._last_seen: Optional[dt.datetime] = None
        self.running = False

    def stop(self) -> None:
        self._stop.set()

    async def run(self) -> None:
        self.running = True
        # Initialise last_seen to the current latest row, so we don't replay history.
        try:
            latest = self.db.latest_row()
            if latest is not None:
                self._last_seen = latest["time_created"]
        except Exception as e:  # noqa: BLE001
            logger.warning("watcher init failed (%s); starting from epoch", e)
            self._last_seen = dt.datetime(1970, 1, 1)

        if self._last_seen is None:
            self._last_seen = dt.datetime(1970, 1, 1)

        try:
            while not self._stop.is_set():
                try:
                    rows = self.db.rows_after(self._last_seen, limit=self.batch_size)
                except Exception as e:  # noqa: BLE001
                    logger.warning("watcher poll failed (%s); will retry", e)
                    rows = []

                for row in rows:
                    self._last_seen = row["time_created"]
                    try:
                        await self.manager.broadcast(_row_to_payload(row))
                    except Exception as e:  # noqa: BLE001
                        logger.warning("broadcast failed (%s)", e)

                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=self.cadence_sec)
                except asyncio.TimeoutError:
                    pass
        finally:
            self.running = False
```

- [ ] **Step 4: Run tests to verify pass.**

Run: `pytest tests/test_watcher.py -v`
Expected: 2 PASS.

- [ ] **Step 5: Commit.**

```bash
git add app/watcher.py tests/test_watcher.py
git commit -m "feat(watcher): polling background task with error survival"
```

---

## Task 10: FastAPI app shell + auth/health routes (`app/main.py`, `app/routes/auth.py`, `app/routes/health.py`)

**Files:**
- Create: `app/main.py`
- Create: `app/routes/health.py`
- Create: `app/routes/auth.py`
- Test: `tests/test_routes_health.py`
- Test: `tests/test_routes_auth.py`

Wires the app together with a `lifespan` that opens the DB and starts the watcher. Adds `/healthz`, `/login`, `/logout`.

- [ ] **Step 1: Write the failing health test.**

Create `tests/test_routes_health.py`:

```python
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

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        async with app.router.lifespan_context(app):
            r = await c.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["db_path"].endswith("synth.duckdb")
    assert "last_row_age_seconds" in body
    assert "ws_clients" in body
    assert "watcher_running" in body
    assert "stale" in body
```

- [ ] **Step 2: Write the failing auth test.**

Create `tests/test_routes_auth.py`:

```python
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
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        async with app.router.lifespan_context(app):
            r = await c.post("/login", json={"password": "wrong"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_login_right_password_sets_cookie(app_env):
    app = app_env
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        async with app.router.lifespan_context(app):
            r = await c.post("/login", json={"password": "hunter2"})
    assert r.status_code == 200
    set_cookie = r.headers.get("set-cookie", "")
    assert "yig_session=" in set_cookie


@pytest.mark.asyncio
async def test_logout_clears_cookie(app_env):
    app = app_env
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        async with app.router.lifespan_context(app):
            await c.post("/login", json={"password": "hunter2"})
            r = await c.post("/logout")
    assert r.status_code == 200
    set_cookie = r.headers.get("set-cookie", "")
    # FastAPI sends Max-Age=0 on delete_cookie
    assert "yig_session=" in set_cookie and "Max-Age=0" in set_cookie
```

- [ ] **Step 3: Run tests to verify failure.**

Run: `pytest tests/test_routes_health.py tests/test_routes_auth.py -v`
Expected: FAIL with "No module named 'app.main'".

- [ ] **Step 4: Implement `app/routes/health.py`.**

```python
"""Public liveness endpoint."""
from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/healthz")
async def healthz(request: Request):
    state = request.app.state
    settings = state.settings
    db = state.db
    manager = state.manager
    watcher = state.watcher

    age = None
    try:
        age = db.latest_row_age_seconds()
    except Exception:
        age = None

    cadence = settings.cadence_sec
    stale = age is not None and age > 2 * cadence

    return {
        "ok": True,
        "db_path": str(settings.db_path),
        "last_row_age_seconds": age,
        "ws_clients": manager.count(),
        "watcher_running": bool(getattr(watcher, "running", False)),
        "stale": stale,
        "cadence_sec": cadence,
    }
```

- [ ] **Step 5: Implement `app/routes/auth.py`.**

```python
"""Login/logout endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel

from app.auth import make_session_cookie, verify_password

router = APIRouter()


class LoginIn(BaseModel):
    password: str


@router.post("/login")
async def login(body: LoginIn, request: Request, response: Response):
    settings = request.app.state.settings
    if not verify_password(settings.password, body.password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="bad password")

    cookie_value = make_session_cookie(settings.secret, ttl_sec=settings.cookie_max_age_sec)
    response.set_cookie(
        key=settings.cookie_name,
        value=cookie_value,
        max_age=settings.cookie_max_age_sec,
        httponly=True,
        secure=not settings.dev_mode,
        samesite="lax",
        path="/",
    )
    return {"ok": True}


@router.post("/logout")
async def logout(request: Request, response: Response):
    settings = request.app.state.settings
    response.delete_cookie(
        key=settings.cookie_name,
        path="/",
        httponly=True,
        secure=not settings.dev_mode,
        samesite="lax",
    )
    return {"ok": True}
```

- [ ] **Step 6: Implement `app/main.py`.**

```python
"""FastAPI app factory + lifespan."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from app.config import Settings
from app.db import Database
from app.routes import auth as auth_routes
from app.routes import health as health_routes
from app.watcher import PollingWatcher
from app.ws_manager import ConnectionManager


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def build_app() -> FastAPI:
    settings = Settings.from_env()
    _configure_logging(settings.log_level)
    logger = logging.getLogger("yig.main")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logger.info("opening DB at %s", settings.db_path)
        db = Database(settings.db_path)
        db.connect(max_wait_sec=settings.db_connect_max_wait_sec)
        manager = ConnectionManager()
        watcher = PollingWatcher(
            db=db, manager=manager, cadence_sec=settings.cadence_sec
        )
        import asyncio
        watcher_task = asyncio.create_task(watcher.run())

        app.state.settings = settings
        app.state.db = db
        app.state.manager = manager
        app.state.watcher = watcher

        try:
            yield
        finally:
            logger.info("shutting down watcher and DB")
            watcher.stop()
            try:
                await asyncio.wait_for(watcher_task, timeout=2.0)
            except asyncio.TimeoutError:
                watcher_task.cancel()
            db.close()

    app = FastAPI(title="YIG Streaming Dashboard", lifespan=lifespan)
    app.include_router(health_routes.router)
    app.include_router(auth_routes.router)
    return app


app = build_app()
```

- [ ] **Step 7: Run tests to verify pass.**

Run: `pytest tests/test_routes_health.py tests/test_routes_auth.py -v`
Expected: 4 PASS.

- [ ] **Step 8: Manual smoke run.**

```bash
cp .env.example .env
# Edit .env: set YIG_DASHBOARD_PASSWORD, YIG_DASHBOARD_SECRET, YIG_DEV_MODE=1
# YIG_DB_PATH must point at an existing DuckDB with a `spectra` table.
# For smoke testing without lab data, you can copy the synth fixture path.
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In another terminal:
```bash
curl http://127.0.0.1:8000/healthz
```
Expected: JSON with `"ok": true`. Stop the server.

- [ ] **Step 9: Commit.**

```bash
git add app/main.py app/routes/health.py app/routes/auth.py tests/test_routes_health.py tests/test_routes_auth.py
git commit -m "feat(app): FastAPI shell with lifespan, health, login/logout"
```

---

## Task 11: REST API routes (`app/routes/api.py`)

**Files:**
- Create: `app/routes/api.py`
- Modify: `app/main.py` (include the router)
- Test: `tests/test_routes_api.py`

Implements `/api/snapshot`, `/api/range`, `/api/peak-track`, `/api/stats`. All require a session cookie.

- [ ] **Step 1: Write the failing test.**

Create `tests/test_routes_api.py`:

```python
import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
async def app_with_session(monkeypatch, synth_db_path):
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
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        async with app.router.lifespan_context(app):
            r = await c.get("/api/snapshot")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_snapshot_with_session(app_with_session):
    app = app_with_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        async with app.router.lifespan_context(app):
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
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        async with app.router.lifespan_context(app):
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
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        async with app.router.lifespan_context(app):
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
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        async with app.router.lifespan_context(app):
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
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        async with app.router.lifespan_context(app):
            await c.post("/login", json={"password": "pw"})
            r = await c.get("/api/stats", params={"window": "1h"})
    assert r.status_code == 200
    body = r.json()
    assert "drift_rate_hz_per_hr" in body
    assert "seconds_since_last_retune" in body
    assert "traces_in_window" in body
    assert "current_snr_db" in body
```

- [ ] **Step 2: Run tests to verify failure.**

Run: `pytest tests/test_routes_api.py -v`
Expected: FAIL with "Not Found" (no `/api` routes).

- [ ] **Step 3: Implement `app/routes/api.py`.**

```python
"""Authenticated REST endpoints for the dashboard frontend."""
from __future__ import annotations

import datetime as dt
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.analytics import (
    compute_drift_rate_hz_per_hr,
    seconds_since_last_retune,
)
from app.auth import require_session_factory

router = APIRouter(prefix="/api")


_WINDOW_RE = re.compile(r"^(\d+)([smhd])$")


def _parse_window(s: str) -> dt.timedelta:
    m = _WINDOW_RE.match(s)
    if not m:
        raise HTTPException(status_code=400, detail="bad window; expected e.g. 1h, 30m, 7d")
    n, unit = int(m.group(1)), m.group(2)
    return dt.timedelta(**{
        "s": "seconds", "m": "minutes", "h": "hours", "d": "days",
    }[unit]: n} if False else None) or {  # unreachable; see below
        "s": dt.timedelta(seconds=n),
        "m": dt.timedelta(minutes=n),
        "h": dt.timedelta(hours=n),
        "d": dt.timedelta(days=n),
    }[unit]


def _row_to_trace(row: dict) -> dict:
    return {
        "t": row["time_created"].isoformat(),
        "center_freq": float(row["center_freq"]),
        "span": float(row["span"]),
        "rbw": float(row["rbw"]),
        "n_points": int(row["n_points"]),
        "powers": [float(x) for x in row["powers"]],
    }


def _peak_to_dict(p: dict) -> dict:
    return {
        "t": p["time_created"].isoformat(),
        "center_freq": float(p["center_freq"]),
        "peak_freq": float(p["peak_freq"]),
        "peak_power": float(p["peak_power"]),
        "snr": float(p["snr"]),
    }


def _require_session(request: Request):
    settings = request.app.state.settings
    return require_session_factory(settings.secret, settings.cookie_name)(request)


@router.get("/snapshot")
async def snapshot(request: Request, session=Depends(_require_session)):
    db = request.app.state.db
    row = db.latest_row()
    if row is None:
        return {"data": None}
    return {"data": _row_to_trace(row)}


@router.get("/range")
async def range_endpoint(
    request: Request,
    t_from: dt.datetime = Query(..., alias="from"),
    t_to: dt.datetime = Query(..., alias="to"),
    max_rows: int = Query(2000, ge=1),
    session=Depends(_require_session),
):
    settings = request.app.state.settings
    if t_to <= t_from:
        raise HTTPException(status_code=400, detail="to must be > from")
    if (t_to - t_from) > dt.timedelta(days=settings.range_max_days):
        raise HTTPException(
            status_code=400,
            detail=f"window exceeds max {settings.range_max_days} days",
        )
    if max_rows > settings.api_max_rows_hard_cap:
        max_rows = settings.api_max_rows_hard_cap
    db = request.app.state.db
    rows = db.range_rows(t_from, t_to, max_rows=max_rows)
    return {"rows": [_row_to_trace(r) for r in rows]}


@router.get("/peak-track")
async def peak_track(
    request: Request,
    t_from: dt.datetime = Query(..., alias="from"),
    t_to: dt.datetime = Query(..., alias="to"),
    max_rows: int = Query(2000, ge=1),
    session=Depends(_require_session),
):
    settings = request.app.state.settings
    if t_to <= t_from:
        raise HTTPException(status_code=400, detail="to must be > from")
    if (t_to - t_from) > dt.timedelta(days=settings.range_max_days):
        raise HTTPException(status_code=400, detail="window too wide")
    if max_rows > settings.api_max_rows_hard_cap:
        max_rows = settings.api_max_rows_hard_cap
    db = request.app.state.db
    pts = db.peak_track_range(t_from, t_to, max_rows=max_rows)
    return {"rows": [_peak_to_dict(p) for p in pts]}


@router.get("/stats")
async def stats(
    request: Request,
    window: str = Query("1h"),
    session=Depends(_require_session),
):
    db = request.app.state.db
    delta = _parse_window(window)
    latest = db.latest_row()
    if latest is None:
        return {
            "drift_rate_hz_per_hr": 0.0,
            "seconds_since_last_retune": 0.0,
            "traces_in_window": 0,
            "current_snr_db": 0.0,
            "window": window,
        }
    now_t = latest["time_created"]
    t_from = now_t - delta

    # Use peak_track_range with a generous max so drift fit is reasonable
    pts = db.peak_track_range(t_from, now_t, max_rows=2000)
    times = [p["time_created"] for p in pts]
    peaks = [p["peak_freq"] for p in pts]
    centers = [p["center_freq"] for p in pts]

    drift = compute_drift_rate_hz_per_hr(times, peaks)
    s_retune = seconds_since_last_retune(times, centers, now=now_t) if times else 0.0
    current_snr = pts[-1]["snr"] if pts else 0.0

    return {
        "drift_rate_hz_per_hr": drift,
        "seconds_since_last_retune": s_retune,
        "traces_in_window": len(pts),
        "current_snr_db": current_snr,
        "window": window,
    }
```

**NOTE — `_parse_window`**: the dict approach above is correct; the inline branch was a confusing artefact. Replace `_parse_window` with this clean version (use this verbatim — overwrite whatever is shown above):

```python
def _parse_window(s: str) -> dt.timedelta:
    m = _WINDOW_RE.match(s)
    if not m:
        raise HTTPException(status_code=400, detail="bad window; expected e.g. 1h, 30m, 7d")
    n, unit = int(m.group(1)), m.group(2)
    return {
        "s": dt.timedelta(seconds=n),
        "m": dt.timedelta(minutes=n),
        "h": dt.timedelta(hours=n),
        "d": dt.timedelta(days=n),
    }[unit]
```

- [ ] **Step 4: Modify `app/main.py` to include the router.**

In `build_app()`, after the existing `app.include_router(...)` calls:

```python
    from app.routes import api as api_routes
    app.include_router(api_routes.router)
```

- [ ] **Step 5: Run tests to verify pass.**

Run: `pytest tests/test_routes_api.py -v`
Expected: 6 PASS.

- [ ] **Step 6: Run full suite.**

Run: `pytest -v`
Expected: all tests pass.

- [ ] **Step 7: Commit.**

```bash
git add app/routes/api.py app/main.py tests/test_routes_api.py
git commit -m "feat(api): snapshot, range, peak-track, stats endpoints"
```

---

## Task 12: WebSocket route (`app/routes/ws.py`)

**Files:**
- Create: `app/routes/ws.py`
- Modify: `app/main.py` (include router)
- Test: `tests/test_ws.py`

WebSocket endpoint at `/ws`. Verifies session cookie at handshake. Adds client to manager, holds the connection, removes on disconnect. Sends a `ping` every 30 s (configurable) to keep Cloudflare Tunnel from culling idle connections.

- [ ] **Step 1: Write the failing WebSocket test.**

Create `tests/test_ws.py`:

```python
import asyncio

import pytest
from httpx import ASGITransport, AsyncClient
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
    """Starlette's TestClient drives the lifespan synchronously."""
    with TestClient(app_env) as client:
        with pytest.raises(Exception):  # WebSocketDisconnect or 401
            with client.websocket_connect("/ws"):
                pass


def test_ws_accepts_with_cookie(app_env):
    cookie_value = make_session_cookie("s" * 32, ttl_sec=3600)
    with TestClient(app_env) as client:
        with client.websocket_connect(
            "/ws",
            headers={"cookie": f"yig_session={cookie_value}"},
        ) as ws:
            # The connection should accept; the watcher won't have anything
            # new to send since fixture is static, but the client is alive.
            # Send a 'ping'-style noise to confirm the socket exists.
            assert ws is not None
```

- [ ] **Step 2: Run test to verify failure.**

Run: `pytest tests/test_ws.py -v`
Expected: FAIL with 404 (no `/ws` route).

- [ ] **Step 3: Implement `app/routes/ws.py`.**

```python
"""WebSocket endpoint for live trace push."""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from app.auth import SessionInvalidError, verify_session_cookie

logger = logging.getLogger("yig.ws.route")

router = APIRouter()


@router.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    settings = websocket.app.state.settings
    manager = websocket.app.state.manager

    cookie = websocket.cookies.get(settings.cookie_name)
    try:
        verify_session_cookie(settings.secret, cookie)
    except SessionInvalidError:
        # 1008 = policy violation (per spec §7)
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()
    manager.add(websocket)
    logger.info("ws client connected (total=%d)", manager.count())

    ping_interval = settings.ws_ping_interval_sec

    async def _ping_loop():
        try:
            while True:
                await asyncio.sleep(ping_interval)
                try:
                    await websocket.send_json({"type": "ping"})
                except Exception:  # noqa: BLE001
                    return
        except asyncio.CancelledError:
            return

    pinger = asyncio.create_task(_ping_loop())
    try:
        while True:
            # We don't expect client messages, but `receive_text` keeps
            # the connection open and surfaces disconnects cleanly.
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception as e:  # noqa: BLE001
        logger.warning("ws error: %s", e)
    finally:
        pinger.cancel()
        manager.remove(websocket)
        logger.info("ws client disconnected (total=%d)", manager.count())
```

- [ ] **Step 4: Modify `app/main.py` to include the router.**

In `build_app()`, after the API router include:

```python
    from app.routes import ws as ws_routes
    app.include_router(ws_routes.router)
```

- [ ] **Step 5: Run tests to verify pass.**

Run: `pytest tests/test_ws.py -v`
Expected: 2 PASS.

- [ ] **Step 6: Full suite green.**

Run: `pytest -v`
Expected: all tests pass.

- [ ] **Step 7: Commit.**

```bash
git add app/routes/ws.py app/main.py tests/test_ws.py
git commit -m "feat(ws): authenticated WebSocket endpoint with ping loop"
```

---

## Task 13: Static frontend mount + skeleton HTML (`frontend/index.html`, `frontend/login.html`, `frontend/styles.css`)

**Files:**
- Create: `frontend/index.html`
- Create: `frontend/login.html`
- Create: `frontend/styles.css`
- Modify: `app/main.py` (mount static files at `/`)

Mounts the frontend at `/`. Login form posts to `/login`; on 200 redirects to `/`. Index page is the dashboard shell.

- [ ] **Step 1: Create `frontend/styles.css` with design tokens.**

```css
/* yig dashboard styles — modern data product, dark default */

:root {
  /* Palette */
  --c-bg-0: #0b0d10;
  --c-bg-1: #12161a;
  --c-bg-2: #1a1f25;
  --c-border: #232a31;
  --c-text-0: #e6eaf0;
  --c-text-1: #a4adb7;
  --c-text-2: #6b7480;
  --c-accent: #4ea1ff;
  --c-accent-2: #2c7fe0;
  --c-good: #5dd39e;
  --c-warn: #f5b050;
  --c-bad:  #ef6b73;

  /* Spacing */
  --s-xs: 4px;
  --s-sm: 8px;
  --s-md: 16px;
  --s-lg: 24px;
  --s-xl: 40px;

  /* Typography */
  --font-sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, Roboto, "Helvetica Neue", Arial, sans-serif;
  --font-mono: ui-monospace, "JetBrains Mono", Consolas, "SF Mono", monospace;

  --radius: 8px;
  --transition: 180ms cubic-bezier(.4, 0, .2, 1);
}

:root[data-theme="light"] {
  --c-bg-0: #f8f9fb;
  --c-bg-1: #ffffff;
  --c-bg-2: #eef1f5;
  --c-border: #d8dde3;
  --c-text-0: #15191e;
  --c-text-1: #5a626c;
  --c-text-2: #8a929c;
  --c-accent: #2c7fe0;
}

* { box-sizing: border-box; }

html, body {
  margin: 0;
  padding: 0;
  background: var(--c-bg-0);
  color: var(--c-text-0);
  font-family: var(--font-sans);
  font-size: 14px;
  line-height: 1.5;
  min-height: 100vh;
}

a { color: var(--c-accent); text-decoration: none; }
a:hover { text-decoration: underline; }

input, button {
  font: inherit;
  color: inherit;
}

button {
  background: var(--c-bg-2);
  color: var(--c-text-0);
  border: 1px solid var(--c-border);
  border-radius: var(--radius);
  padding: var(--s-sm) var(--s-md);
  cursor: pointer;
  transition: background var(--transition), border-color var(--transition);
}
button:hover { background: var(--c-border); }
button:focus-visible { outline: 2px solid var(--c-accent); outline-offset: 2px; }

input[type="password"], input[type="text"] {
  background: var(--c-bg-1);
  border: 1px solid var(--c-border);
  border-radius: var(--radius);
  padding: var(--s-sm) var(--s-md);
  color: var(--c-text-0);
  width: 100%;
}

/* dashboard layout */
yig-app { display: block; min-height: 100vh; }

.dash-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  grid-template-rows: auto auto auto;
  gap: var(--s-md);
  padding: var(--s-md);
  max-width: 1600px;
  margin: 0 auto;
}

.panel {
  background: var(--c-bg-1);
  border: 1px solid var(--c-border);
  border-radius: var(--radius);
  padding: var(--s-md);
  min-height: 220px;
}

.panel h2 {
  margin: 0 0 var(--s-sm);
  font-size: 13px;
  font-weight: 600;
  color: var(--c-text-1);
  text-transform: uppercase;
  letter-spacing: .04em;
}

.panel--wide { grid-column: 1 / -1; }

/* header */
.hdr {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--s-md) var(--s-lg);
  border-bottom: 1px solid var(--c-border);
  background: var(--c-bg-1);
}
.hdr__title { font-weight: 600; letter-spacing: .02em; }
.hdr__title small { color: var(--c-text-2); font-weight: 400; margin-left: var(--s-sm); }
.hdr__right { display: flex; align-items: center; gap: var(--s-md); }

/* health LED */
.led {
  display: inline-flex;
  align-items: center;
  gap: var(--s-xs);
  font-size: 12px;
  color: var(--c-text-1);
}
.led__dot {
  width: 10px; height: 10px;
  border-radius: 50%;
  background: var(--c-text-2);
  transition: background var(--transition);
}
.led__dot--ok    { background: var(--c-good);  box-shadow: 0 0 6px rgba(93, 211, 158, 0.6); }
.led__dot--warn  { background: var(--c-warn); }
.led__dot--bad   { background: var(--c-bad);  }

/* login page */
.login-wrap {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
}
.login-card {
  width: min(360px, 90vw);
  background: var(--c-bg-1);
  border: 1px solid var(--c-border);
  border-radius: var(--radius);
  padding: var(--s-xl);
}
.login-card h1 {
  margin: 0 0 var(--s-md);
  font-size: 18px;
}
.login-card .row { margin-top: var(--s-md); }
.login-card .err {
  color: var(--c-bad);
  margin-top: var(--s-sm);
  min-height: 1em;
  font-size: 13px;
}

.muted { color: var(--c-text-2); }
.value-big {
  font-family: var(--font-mono);
  font-size: 28px;
  font-weight: 500;
  letter-spacing: .02em;
}
.value-label {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: .06em;
  color: var(--c-text-2);
}

/* range selector / history slider */
.range-controls {
  display: flex;
  gap: var(--s-sm);
}
.range-btn {
  background: transparent;
  border: 1px solid var(--c-border);
  padding: var(--s-xs) var(--s-md);
  font-size: 12px;
}
.range-btn[data-active="1"] {
  background: var(--c-accent);
  border-color: var(--c-accent);
  color: #fff;
}
```

- [ ] **Step 2: Create `frontend/login.html`.**

```html
<!doctype html>
<html lang="en" data-theme="dark">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>YIG Dashboard — Login</title>
  <link rel="stylesheet" href="/static/styles.css" />
</head>
<body>
  <div class="login-wrap">
    <form class="login-card" id="login-form">
      <h1>YIG Dashboard</h1>
      <p class="muted">Enter the lab password to continue.</p>
      <div class="row">
        <input type="password" id="pw" name="password" autofocus required />
      </div>
      <div class="row">
        <button type="submit">Sign in</button>
      </div>
      <div class="err" id="err"></div>
    </form>
  </div>
  <script>
    document.getElementById("login-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const pw = document.getElementById("pw").value;
      const err = document.getElementById("err");
      err.textContent = "";
      try {
        const r = await fetch("/login", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ password: pw }),
          credentials: "same-origin",
        });
        if (r.ok) {
          window.location.href = "/";
          return;
        }
        if (r.status === 401) {
          err.textContent = "Wrong password.";
        } else {
          err.textContent = `Login failed (${r.status}).`;
        }
      } catch (ex) {
        err.textContent = "Network error.";
      }
    });
  </script>
</body>
</html>
```

- [ ] **Step 3: Create `frontend/index.html`.**

```html
<!doctype html>
<html lang="en" data-theme="dark">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>YIG Dashboard</title>
  <link rel="stylesheet" href="/static/styles.css" />

  <script src="https://cdn.plot.ly/plotly-2.35.2.min.js" charset="utf-8"></script>
  <script type="importmap">
    {
      "imports": {
        "lit": "https://esm.sh/lit@3.1.4",
        "lit/decorators.js": "https://esm.sh/lit@3.1.4/decorators.js"
      }
    }
  </script>
</head>
<body>
  <yig-app></yig-app>

  <script type="module">
    import "/static/lib/store.js";
    import "/static/lib/api.js";
    import "/static/lib/ws-client.js";
    import "/static/lib/plotly-theme.js";
    import "/static/components/yig-app.js";
    import "/static/components/yig-header.js";
    import "/static/components/yig-live-trace.js";
    import "/static/components/yig-spectrogram.js";
    import "/static/components/yig-peak-track.js";
    import "/static/components/yig-peak-power.js";
    import "/static/components/yig-stats.js";
    import "/static/components/yig-history-browser.js";
  </script>
</body>
</html>
```

- [ ] **Step 4: Modify `app/main.py` to mount static files and serve HTML.**

Add to `build_app()` after router includes:

```python
    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import FileResponse, RedirectResponse
    from app.auth import SessionInvalidError, verify_session_cookie

    frontend_dir = Path(__file__).resolve().parent.parent / "frontend"

    app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

    @app.get("/login", include_in_schema=False)
    async def login_page():
        return FileResponse(frontend_dir / "login.html")

    @app.get("/", include_in_schema=False)
    async def root(request):
        cookie = request.cookies.get(settings.cookie_name)
        try:
            verify_session_cookie(settings.secret, cookie)
        except SessionInvalidError:
            return RedirectResponse(url="/login", status_code=303)
        return FileResponse(frontend_dir / "index.html")
```

Also add `from fastapi import Request` import at the top if not present and update the function signature: `async def root(request: Request)`.

- [ ] **Step 5: Smoke test.**

```bash
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In a browser, visit `http://127.0.0.1:8000/`. Expected: redirected to `/login`. Enter the password. Expected: redirected to `/` showing an empty `<yig-app>` shell (custom elements not yet defined → empty page is fine until Task 14). Stop the server.

- [ ] **Step 6: Commit.**

```bash
git add frontend/index.html frontend/login.html frontend/styles.css app/main.py
git commit -m "feat(frontend): static mount + login page + dashboard shell"
```

---

## Task 14: Frontend lib — store, api, ws-client, plotly-theme

**Files:**
- Create: `frontend/lib/store.js`
- Create: `frontend/lib/api.js`
- Create: `frontend/lib/ws-client.js`
- Create: `frontend/lib/plotly-theme.js`

These are foundational helpers used by every component.

- [ ] **Step 1: Create `frontend/lib/store.js`.**

```javascript
// Minimal reactive store. Keys are arbitrary strings; subscribers receive new values.

class Store {
  constructor(initial = {}) {
    this._state = { ...initial };
    this._subs = new Map(); // key -> Set<callback>
  }

  get(key) {
    return this._state[key];
  }

  set(key, value) {
    this._state[key] = value;
    const subs = this._subs.get(key);
    if (subs) subs.forEach((cb) => {
      try { cb(value); } catch (e) { console.error(e); }
    });
  }

  subscribe(key, cb) {
    if (!this._subs.has(key)) this._subs.set(key, new Set());
    this._subs.get(key).add(cb);
    // Fire immediately if a value already exists
    if (key in this._state) cb(this._state[key]);
    return () => this._subs.get(key)?.delete(cb);
  }
}

const DEFAULT_RANGE_MS = 5 * 60 * 1000; // last 5 minutes
const now = Date.now();

export const store = new Store({
  range: { from: new Date(now - DEFAULT_RANGE_MS), to: new Date(now), live: true },
  latestRow: null,
  theme: localStorage.getItem("yig-theme") || "dark",
  wsConnected: false,
  lastRowTs: null,
});

window.__yigStore = store; // dev convenience
```

- [ ] **Step 2: Create `frontend/lib/api.js`.**

```javascript
// REST helpers. On 401, redirect to /login.

async function _fetch(path, opts = {}) {
  const r = await fetch(path, { credentials: "same-origin", ...opts });
  if (r.status === 401) {
    window.location.href = "/login";
    throw new Error("unauthorized");
  }
  return r;
}

export async function getJSON(path) {
  const r = await _fetch(path);
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
  return r.json();
}

export async function getSnapshot() {
  return getJSON("/api/snapshot");
}

export async function getRange(from, to, max_rows = 2000) {
  const qs = new URLSearchParams({
    from: from.toISOString().replace("Z", ""),
    to:   to.toISOString().replace("Z", ""),
    max_rows: String(max_rows),
  });
  return getJSON(`/api/range?${qs}`);
}

export async function getPeakTrack(from, to, max_rows = 2000) {
  const qs = new URLSearchParams({
    from: from.toISOString().replace("Z", ""),
    to:   to.toISOString().replace("Z", ""),
    max_rows: String(max_rows),
  });
  return getJSON(`/api/peak-track?${qs}`);
}

export async function getStats(window = "1h") {
  const qs = new URLSearchParams({ window });
  return getJSON(`/api/stats?${qs}`);
}

export async function getHealth() {
  return getJSON("/healthz");
}
```

- [ ] **Step 3: Create `frontend/lib/ws-client.js`.**

```javascript
// Singleton WS client with exponential-backoff reconnect.
// Dispatches typed events: 'trace', 'ping', plus connect/disconnect.

import { store } from "/static/lib/store.js";

class WSClient {
  constructor(path = "/ws") {
    this.path = path;
    this.ws = null;
    this.subs = new Map();   // type -> Set<cb>
    this.backoff = 1000;
    this._stopped = false;
    this._connect();
  }

  _connect() {
    if (this._stopped) return;
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    const url = `${proto}//${location.host}${this.path}`;
    try {
      this.ws = new WebSocket(url);
    } catch (e) {
      this._scheduleReconnect();
      return;
    }
    this.ws.addEventListener("open", () => {
      this.backoff = 1000;
      store.set("wsConnected", true);
    });
    this.ws.addEventListener("close", (e) => {
      store.set("wsConnected", false);
      // 1008 = policy violation = bad/missing cookie. Redirect to login.
      if (e.code === 1008) {
        window.location.href = "/login";
        return;
      }
      this._scheduleReconnect();
    });
    this.ws.addEventListener("error", () => {
      // close handler will fire too
    });
    this.ws.addEventListener("message", (ev) => {
      let msg;
      try { msg = JSON.parse(ev.data); } catch { return; }
      const subs = this.subs.get(msg.type);
      if (subs) subs.forEach((cb) => {
        try { cb(msg.data); } catch (e) { console.error(e); }
      });
      if (msg.type === "trace" && msg.data) {
        store.set("latestRow", msg.data);
        store.set("lastRowTs", new Date(msg.data.t));
      }
    });
  }

  _scheduleReconnect() {
    setTimeout(() => this._connect(), this.backoff);
    this.backoff = Math.min(this.backoff * 2, 30000);
  }

  subscribe(type, cb) {
    if (!this.subs.has(type)) this.subs.set(type, new Set());
    this.subs.get(type).add(cb);
    return () => this.subs.get(type)?.delete(cb);
  }

  stop() {
    this._stopped = true;
    if (this.ws) this.ws.close();
  }
}

export const ws = new WSClient("/ws");
window.__yigWS = ws;
```

- [ ] **Step 4: Create `frontend/lib/plotly-theme.js`.**

```javascript
// Convert CSS custom properties into Plotly layout overrides.
// Components call applyTheme(layout) before rendering.

function _v(name, fallback = "") {
  return getComputedStyle(document.documentElement)
    .getPropertyValue(name)
    .trim() || fallback;
}

export function plotlyLayout(extra = {}) {
  const text = _v("--c-text-1", "#a4adb7");
  const grid = _v("--c-border", "#232a31");
  const bg0  = _v("--c-bg-1",   "#12161a");
  const accent = _v("--c-accent", "#4ea1ff");

  const base = {
    paper_bgcolor: bg0,
    plot_bgcolor: bg0,
    font: { family: "Inter, system-ui, sans-serif", color: text, size: 12 },
    margin: { l: 56, r: 28, t: 24, b: 40 },
    xaxis: {
      gridcolor: grid,
      zerolinecolor: grid,
      linecolor: grid,
      tickcolor: grid,
      color: text,
    },
    yaxis: {
      gridcolor: grid,
      zerolinecolor: grid,
      linecolor: grid,
      tickcolor: grid,
      color: text,
    },
    colorway: [accent],
    showlegend: false,
  };

  return _deepMerge(base, extra);
}

export const plotlyConfig = {
  displaylogo: false,
  responsive: true,
  modeBarButtonsToRemove: ["lasso2d", "select2d"],
};

function _deepMerge(a, b) {
  const out = { ...a };
  for (const k of Object.keys(b || {})) {
    if (b[k] && typeof b[k] === "object" && !Array.isArray(b[k]) && a[k] && typeof a[k] === "object") {
      out[k] = _deepMerge(a[k], b[k]);
    } else {
      out[k] = b[k];
    }
  }
  return out;
}
```

- [ ] **Step 5: Smoke test.**

Restart `uvicorn`, reload the page, open the browser DevTools console. Expected: no module-not-found errors. `__yigStore` and `__yigWS` exist on `window`. Visit `/healthz` directly and confirm `ws_clients` increments after the page loads (the WS client connects on import).

- [ ] **Step 6: Commit.**

```bash
git add frontend/lib/
git commit -m "feat(frontend): store/api/ws-client/plotly-theme libs"
```

---

## Task 15: yig-app + yig-header components

**Files:**
- Create: `frontend/components/yig-app.js`
- Create: `frontend/components/yig-header.js`

`yig-app` is the layout shell. `yig-header` shows title, theme toggle, range selector, and a health LED.

- [ ] **Step 1: Create `frontend/components/yig-app.js`.**

```javascript
import { LitElement, html, css } from "lit";

export class YigApp extends LitElement {
  // Use light DOM so the global stylesheet applies.
  createRenderRoot() { return this; }

  render() {
    return html`
      <yig-header></yig-header>
      <main class="dash-grid">
        <section class="panel panel--wide">
          <h2>Live trace</h2>
          <yig-live-trace></yig-live-trace>
        </section>
        <section class="panel panel--wide">
          <h2>Spectrogram</h2>
          <yig-spectrogram></yig-spectrogram>
        </section>
        <section class="panel">
          <h2>Peak frequency</h2>
          <yig-peak-track></yig-peak-track>
        </section>
        <section class="panel">
          <h2>Peak power & SNR</h2>
          <yig-peak-power></yig-peak-power>
        </section>
        <section class="panel panel--wide">
          <h2>Stats</h2>
          <yig-stats></yig-stats>
        </section>
        <section class="panel panel--wide">
          <h2>History (7 days)</h2>
          <yig-history-browser></yig-history-browser>
        </section>
      </main>
    `;
  }
}

customElements.define("yig-app", YigApp);
```

- [ ] **Step 2: Create `frontend/components/yig-header.js`.**

```javascript
import { LitElement, html } from "lit";
import { store } from "/static/lib/store.js";

const RANGES = [
  { id: "5m",  ms: 5 * 60 * 1000 },
  { id: "30m", ms: 30 * 60 * 1000 },
  { id: "1h",  ms: 60 * 60 * 1000 },
  { id: "6h",  ms: 6 * 60 * 60 * 1000 },
  { id: "24h", ms: 24 * 60 * 60 * 1000 },
  { id: "7d",  ms: 7 * 24 * 60 * 60 * 1000 },
];

export class YigHeader extends LitElement {
  createRenderRoot() { return this; }

  static properties = {
    activeRange: { state: true },
    ledClass: { state: true },
    ledLabel: { state: true },
    theme: { state: true },
  };

  constructor() {
    super();
    this.activeRange = "5m";
    this.theme = store.get("theme") || "dark";
    this.ledClass = "led__dot--bad";
    this.ledLabel = "offline";
    this._setRange("5m");
    document.documentElement.dataset.theme = this.theme;

    setInterval(() => this._refreshLed(), 1000);
    store.subscribe("wsConnected", () => this._refreshLed());
    store.subscribe("lastRowTs", () => this._refreshLed());
  }

  _refreshLed() {
    const wsOk = !!store.get("wsConnected");
    const lastTs = store.get("lastRowTs");
    if (!wsOk) {
      this.ledClass = "led__dot--bad";
      this.ledLabel = "disconnected";
      return;
    }
    if (!lastTs) {
      this.ledClass = "led__dot--warn";
      this.ledLabel = "no data yet";
      return;
    }
    const ageSec = (Date.now() - lastTs.getTime()) / 1000;
    if (ageSec < 5) {
      this.ledClass = "led__dot--ok";
      this.ledLabel = "live";
    } else if (ageSec < 30) {
      this.ledClass = "led__dot--warn";
      this.ledLabel = `stale (${ageSec.toFixed(0)}s)`;
    } else {
      this.ledClass = "led__dot--bad";
      this.ledLabel = `stale (${ageSec.toFixed(0)}s)`;
    }
  }

  _setRange(id) {
    this.activeRange = id;
    const cfg = RANGES.find((r) => r.id === id);
    const to = new Date();
    const from = new Date(to.getTime() - cfg.ms);
    store.set("range", { from, to, live: true, key: id });
  }

  _toggleTheme() {
    this.theme = this.theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = this.theme;
    localStorage.setItem("yig-theme", this.theme);
    store.set("theme", this.theme);
  }

  async _logout() {
    await fetch("/logout", { method: "POST", credentials: "same-origin" });
    window.location.href = "/login";
  }

  render() {
    return html`
      <header class="hdr">
        <div class="hdr__title">
          YIG Dashboard
          <small>spectrum_data_ovn</small>
        </div>
        <div class="hdr__right">
          <div class="range-controls">
            ${RANGES.map((r) => html`
              <button class="range-btn"
                data-active=${this.activeRange === r.id ? "1" : "0"}
                @click=${() => this._setRange(r.id)}>${r.id}</button>
            `)}
          </div>
          <span class="led">
            <span class="led__dot ${this.ledClass}"></span>${this.ledLabel}
          </span>
          <button @click=${this._toggleTheme} title="Toggle theme">
            ${this.theme === "dark" ? "☀" : "☾"}
          </button>
          <button @click=${this._logout}>Logout</button>
        </div>
      </header>
    `;
  }
}

customElements.define("yig-header", YigHeader);
```

- [ ] **Step 3: Create stub component files** so the imports in `index.html` don't 404. Each file just registers an empty element for now; later tasks fill them in.

`frontend/components/yig-live-trace.js`:
```javascript
import { LitElement, html } from "lit";
class YigLiveTrace extends LitElement {
  createRenderRoot() { return this; }
  render() { return html`<div class="muted">live trace pending…</div>`; }
}
customElements.define("yig-live-trace", YigLiveTrace);
```

`frontend/components/yig-spectrogram.js`:
```javascript
import { LitElement, html } from "lit";
class YigSpectrogram extends LitElement {
  createRenderRoot() { return this; }
  render() { return html`<div class="muted">spectrogram pending…</div>`; }
}
customElements.define("yig-spectrogram", YigSpectrogram);
```

`frontend/components/yig-peak-track.js`:
```javascript
import { LitElement, html } from "lit";
class YigPeakTrack extends LitElement {
  createRenderRoot() { return this; }
  render() { return html`<div class="muted">peak track pending…</div>`; }
}
customElements.define("yig-peak-track", YigPeakTrack);
```

`frontend/components/yig-peak-power.js`:
```javascript
import { LitElement, html } from "lit";
class YigPeakPower extends LitElement {
  createRenderRoot() { return this; }
  render() { return html`<div class="muted">peak power pending…</div>`; }
}
customElements.define("yig-peak-power", YigPeakPower);
```

`frontend/components/yig-stats.js`:
```javascript
import { LitElement, html } from "lit";
class YigStats extends LitElement {
  createRenderRoot() { return this; }
  render() { return html`<div class="muted">stats pending…</div>`; }
}
customElements.define("yig-stats", YigStats);
```

`frontend/components/yig-history-browser.js`:
```javascript
import { LitElement, html } from "lit";
class YigHistoryBrowser extends LitElement {
  createRenderRoot() { return this; }
  render() { return html`<div class="muted">history browser pending…</div>`; }
}
customElements.define("yig-history-browser", YigHistoryBrowser);
```

- [ ] **Step 4: Smoke test.**

Restart server, reload the dashboard. Expected:
- Header with title, range buttons, LED, theme toggle, logout button.
- Six panels with "pending…" placeholders.
- LED is amber/red (no data yet), turns green if WS is connected and a row arrives.

- [ ] **Step 5: Commit.**

```bash
git add frontend/components/
git commit -m "feat(frontend): yig-app shell + yig-header + component stubs"
```

---

## Task 16: yig-live-trace component

**Files:**
- Modify: `frontend/components/yig-live-trace.js`

Fetches `/api/snapshot`, subscribes to WS `trace` events, calls `Plotly.react` per new trace.

- [ ] **Step 1: Replace contents of `frontend/components/yig-live-trace.js`.**

```javascript
import { LitElement, html } from "lit";
import { getSnapshot } from "/static/lib/api.js";
import { ws } from "/static/lib/ws-client.js";
import { plotlyLayout, plotlyConfig } from "/static/lib/plotly-theme.js";

const PLOT_HEIGHT = 280;

export class YigLiveTrace extends LitElement {
  createRenderRoot() { return this; }

  static properties = {
    _err: { state: true },
  };

  constructor() {
    super();
    this._unsub = null;
    this._plotEl = null;
    this._lastTrace = null;
    this._err = null;
  }

  connectedCallback() {
    super.connectedCallback();
    this._unsub = ws.subscribe("trace", (data) => this._onTrace(data));
    this._init();
  }

  disconnectedCallback() {
    super.disconnectedCallback();
    if (this._unsub) this._unsub();
  }

  async _init() {
    try {
      const r = await getSnapshot();
      if (r.data) this._draw(r.data);
    } catch (e) {
      this._err = String(e);
    }
  }

  _freqAxis(trace) {
    const { center_freq, span, n_points } = trace;
    const f0 = center_freq - span / 2;
    const out = new Array(n_points);
    for (let i = 0; i < n_points; i++) {
      out[i] = (f0 + (i * span) / (n_points - 1)) / 1e9;
    }
    return out;
  }

  _draw(trace) {
    this._lastTrace = trace;
    const x = this._freqAxis(trace);
    const data = [{
      x,
      y: trace.powers,
      mode: "lines",
      line: { width: 1.2 },
      hovertemplate: "%{x:.6f} GHz<br>%{y:.2f} dBm<extra></extra>",
    }];
    const layout = plotlyLayout({
      height: PLOT_HEIGHT,
      xaxis: { title: { text: "Frequency (GHz)" } },
      yaxis: { title: { text: "Power (dBm)" } },
    });
    if (!this._plotEl) {
      this._plotEl = this.querySelector("#live-plot");
    }
    Plotly.react(this._plotEl, data, layout, plotlyConfig);
  }

  _onTrace(data) {
    if (!data) return;
    this._draw(data);
  }

  render() {
    return html`
      ${this._err ? html`<div class="muted">${this._err}</div>` : null}
      <div id="live-plot" style="width:100%;height:${PLOT_HEIGHT}px"></div>
    `;
  }
}

customElements.define("yig-live-trace", YigLiveTrace);
```

- [ ] **Step 2: Smoke test.**

Restart server. Visit dashboard. Expected: live trace plot renders with the latest snapshot. If the tracker is running (or you insert rows manually into the DB), updates animate in real time.

To simulate liveness without the real tracker, in another shell:
```bash
uv run python -c "
import duckdb, datetime as dt, numpy as np, time
conn = duckdb.connect('spectrum_data_ovn.duckdb')
for i in range(60):
    powers = (-60 + 30*np.exp(-((np.linspace(-1,1,501))**2)/0.05)).astype(np.float32)
    conn.execute('INSERT INTO spectra VALUES (?, ?, ?, ?, ?, ?)', [dt.datetime.now(), 6.46e9, 5e6, 30e3, 501, powers.tolist()])
    time.sleep(1)
"
```
Expected: trace updates ~once a second.

- [ ] **Step 3: Commit.**

```bash
git add frontend/components/yig-live-trace.js
git commit -m "feat(frontend): live trace plot wired to snapshot + WS"
```

---

## Task 17: yig-spectrogram component

**Files:**
- Modify: `frontend/components/yig-spectrogram.js`

Fetches `/api/range`, builds a global frequency grid with NaN padding (mirrors `plot_spectrogram.py` `build_grid` + `grid_traces`), renders a Plotly heatmap.

- [ ] **Step 1: Replace contents of `frontend/components/yig-spectrogram.js`.**

```javascript
import { LitElement, html } from "lit";
import { getRange } from "/static/lib/api.js";
import { ws } from "/static/lib/ws-client.js";
import { store } from "/static/lib/store.js";
import { plotlyLayout, plotlyConfig } from "/static/lib/plotly-theme.js";

const PLOT_HEIGHT = 360;
const MAX_ROWS = 1500;

function freqAxis(trace) {
  const { center_freq, span, n_points } = trace;
  const f0 = center_freq - span / 2;
  const out = new Array(n_points);
  for (let i = 0; i < n_points; i++) {
    out[i] = f0 + (i * span) / (n_points - 1);
  }
  return out;
}

// Median spacing across rows (same as plot_spectrogram.build_grid default).
function buildGrid(rows) {
  if (rows.length === 0) return { grid: [], binHz: 0, fMin: 0 };
  let fMin = Infinity, fMax = -Infinity;
  const spacings = [];
  for (const r of rows) {
    const f = freqAxis(r);
    if (f[0] < fMin) fMin = f[0];
    if (f[f.length - 1] > fMax) fMax = f[f.length - 1];
    if (f.length > 1) spacings.push((f[f.length - 1] - f[0]) / (f.length - 1));
  }
  spacings.sort((a, b) => a - b);
  const binHz = spacings[Math.floor(spacings.length / 2)] || 1e4;
  const nBins = Math.ceil((fMax - fMin) / binHz) + 1;
  const grid = new Array(nBins);
  for (let i = 0; i < nBins; i++) grid[i] = fMin + i * binHz;
  return { grid, binHz, fMin };
}

// Linear interpolation; NaN outside [xs[0], xs[xs.length-1]].
function interp(xq, xs, ys) {
  if (xq < xs[0] || xq > xs[xs.length - 1]) return NaN;
  // binary search
  let lo = 0, hi = xs.length - 1;
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if (xs[mid] <= xq) lo = mid; else hi = mid;
  }
  const x0 = xs[lo], x1 = xs[hi];
  const y0 = ys[lo], y1 = ys[hi];
  if (x0 === x1) return y0;
  return y0 + ((xq - x0) / (x1 - x0)) * (y1 - y0);
}

function gridTraces(rows, grid) {
  const nT = rows.length;
  const nF = grid.length;
  // Z is row-major: Z[t][f]
  const Z = new Array(nT);
  for (let i = 0; i < nT; i++) {
    const f = freqAxis(rows[i]);
    const p = rows[i].powers;
    const z = new Array(nF);
    // Find the index range where the grid lies inside [f[0], f[-1]]
    const left = lowerBound(grid, f[0]);
    const right = upperBound(grid, f[f.length - 1]);
    for (let k = 0; k < left; k++) z[k] = null;
    for (let k = right; k < nF; k++) z[k] = null;
    for (let k = left; k < right; k++) {
      const v = interp(grid[k], f, p);
      z[k] = Number.isFinite(v) ? v : null;
    }
    Z[i] = z;
  }
  return Z;
}

function lowerBound(arr, target) {
  let lo = 0, hi = arr.length;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (arr[mid] < target) lo = mid + 1; else hi = mid;
  }
  return lo;
}
function upperBound(arr, target) {
  let lo = 0, hi = arr.length;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (arr[mid] <= target) lo = mid + 1; else hi = mid;
  }
  return lo;
}

export class YigSpectrogram extends LitElement {
  createRenderRoot() { return this; }

  static properties = {
    _err: { state: true },
    _empty: { state: true },
  };

  constructor() {
    super();
    this._unsubRange = null;
    this._unsubTrace = null;
    this._rows = [];
    this._plotEl = null;
    this._err = null;
    this._empty = false;
  }

  connectedCallback() {
    super.connectedCallback();
    this._unsubRange = store.subscribe("range", () => this._reload());
    this._unsubTrace = ws.subscribe("trace", (data) => this._onLiveTrace(data));
  }

  disconnectedCallback() {
    super.disconnectedCallback();
    if (this._unsubRange) this._unsubRange();
    if (this._unsubTrace) this._unsubTrace();
  }

  async _reload() {
    const range = store.get("range");
    if (!range) return;
    try {
      const r = await getRange(range.from, range.to, MAX_ROWS);
      this._rows = r.rows || [];
      this._empty = this._rows.length === 0;
      this._draw();
    } catch (e) {
      this._err = String(e);
    }
  }

  _onLiveTrace(data) {
    const range = store.get("range");
    if (!range || !range.live) return;
    this._rows.push(data);
    if (this._rows.length > MAX_ROWS) this._rows.shift();
    this._draw();
  }

  _draw() {
    if (!this._plotEl) this._plotEl = this.querySelector("#sg-plot");
    if (this._rows.length === 0) {
      Plotly.purge(this._plotEl);
      return;
    }
    const { grid } = buildGrid(this._rows);
    const Z = gridTraces(this._rows, grid);
    const xTimes = this._rows.map((r) => new Date(r.t));
    const yFreqGHz = grid.map((f) => f / 1e9);

    const data = [{
      type: "heatmap",
      x: xTimes,
      y: yFreqGHz,
      z: transpose(Z),  // plotly wants z[y_index][x_index]
      colorscale: "Viridis",
      hoverongaps: false,
      hovertemplate: "%{x}<br>%{y:.6f} GHz<br>%{z:.2f} dBm<extra></extra>",
      colorbar: { title: { text: "dBm" } },
    }];
    const layout = plotlyLayout({
      height: PLOT_HEIGHT,
      xaxis: { type: "date" },
      yaxis: { title: { text: "Frequency (GHz)" } },
    });
    Plotly.react(this._plotEl, data, layout, plotlyConfig);
  }

  render() {
    return html`
      ${this._err ? html`<div class="muted">${this._err}</div>` : null}
      ${this._empty ? html`<div class="muted">no data in window</div>` : null}
      <div id="sg-plot" style="width:100%;height:${PLOT_HEIGHT}px"></div>
    `;
  }
}

function transpose(Z) {
  if (Z.length === 0) return [];
  const nT = Z.length;
  const nF = Z[0].length;
  const out = new Array(nF);
  for (let f = 0; f < nF; f++) {
    const row = new Array(nT);
    for (let t = 0; t < nT; t++) row[t] = Z[t][f];
    out[f] = row;
  }
  return out;
}

customElements.define("yig-spectrogram", YigSpectrogram);
```

- [ ] **Step 2: Smoke test.**

Reload the page. Expected: spectrogram heatmap renders with viridis colormap. Click range buttons in the header — heatmap re-fetches and redraws. NaN cells render as background (the staircase pattern in `plot_spectrogram.py`).

- [ ] **Step 3: Commit.**

```bash
git add frontend/components/yig-spectrogram.js
git commit -m "feat(frontend): spectrogram with global grid + NaN padding"
```

---

## Task 18: yig-peak-track + yig-peak-power components

**Files:**
- Modify: `frontend/components/yig-peak-track.js`
- Modify: `frontend/components/yig-peak-power.js`

Both fetch `/api/peak-track` and append on live trace events. They share most of the logic — but per DRY *and* plan-readability, each file is fully self-contained.

- [ ] **Step 1: Replace contents of `frontend/components/yig-peak-track.js`.**

```javascript
import { LitElement, html } from "lit";
import { getPeakTrack } from "/static/lib/api.js";
import { ws } from "/static/lib/ws-client.js";
import { store } from "/static/lib/store.js";
import { plotlyLayout, plotlyConfig } from "/static/lib/plotly-theme.js";

const PLOT_HEIGHT = 220;
const MAX_PTS = 2000;

// Compute peak from a raw trace payload (matches server-side computation).
function peakOf(trace) {
  let pi = 0;
  for (let i = 1; i < trace.powers.length; i++) {
    if (trace.powers[i] > trace.powers[pi]) pi = i;
  }
  const f0 = trace.center_freq - trace.span / 2;
  const peakFreq = f0 + (pi * trace.span) / (trace.n_points - 1);
  return peakFreq;
}

export class YigPeakTrack extends LitElement {
  createRenderRoot() { return this; }
  static properties = { _err: { state: true } };

  constructor() {
    super();
    this._unsubRange = null;
    this._unsubTrace = null;
    this._x = []; this._y = [];
    this._plotEl = null;
    this._err = null;
  }

  connectedCallback() {
    super.connectedCallback();
    this._unsubRange = store.subscribe("range", () => this._reload());
    this._unsubTrace = ws.subscribe("trace", (data) => this._onLive(data));
  }
  disconnectedCallback() {
    super.disconnectedCallback();
    this._unsubRange?.();
    this._unsubTrace?.();
  }

  async _reload() {
    const r = store.get("range");
    if (!r) return;
    try {
      const resp = await getPeakTrack(r.from, r.to, MAX_PTS);
      this._x = resp.rows.map((p) => new Date(p.t));
      this._y = resp.rows.map((p) => p.peak_freq / 1e9);
      this._draw();
    } catch (e) { this._err = String(e); }
  }

  _onLive(data) {
    const r = store.get("range");
    if (!r || !r.live) return;
    this._x.push(new Date(data.t));
    this._y.push(peakOf(data) / 1e9);
    while (this._x.length > MAX_PTS) { this._x.shift(); this._y.shift(); }
    this._draw();
  }

  _draw() {
    if (!this._plotEl) this._plotEl = this.querySelector("#pt-plot");
    const data = [{
      x: this._x, y: this._y, mode: "lines",
      line: { width: 1.2 },
      hovertemplate: "%{x}<br>%{y:.6f} GHz<extra></extra>",
    }];
    const layout = plotlyLayout({
      height: PLOT_HEIGHT,
      xaxis: { type: "date" },
      yaxis: { title: { text: "Peak frequency (GHz)" }, tickformat: ".6f" },
    });
    Plotly.react(this._plotEl, data, layout, plotlyConfig);
  }

  render() {
    return html`
      ${this._err ? html`<div class="muted">${this._err}</div>` : null}
      <div id="pt-plot" style="width:100%;height:${PLOT_HEIGHT}px"></div>
    `;
  }
}

customElements.define("yig-peak-track", YigPeakTrack);
```

- [ ] **Step 2: Replace contents of `frontend/components/yig-peak-power.js`.**

```javascript
import { LitElement, html } from "lit";
import { getPeakTrack } from "/static/lib/api.js";
import { ws } from "/static/lib/ws-client.js";
import { store } from "/static/lib/store.js";
import { plotlyLayout, plotlyConfig } from "/static/lib/plotly-theme.js";

const PLOT_HEIGHT = 220;
const MAX_PTS = 2000;

function median(arr) {
  if (arr.length === 0) return 0;
  const s = [...arr].sort((a, b) => a - b);
  return s[Math.floor(s.length / 2)];
}

function peakAndSnrOf(trace) {
  let pi = 0;
  for (let i = 1; i < trace.powers.length; i++) {
    if (trace.powers[i] > trace.powers[pi]) pi = i;
  }
  const peak = trace.powers[pi];
  const med = median(trace.powers);
  return { peak, snr: peak - med };
}

export class YigPeakPower extends LitElement {
  createRenderRoot() { return this; }
  static properties = { _err: { state: true } };

  constructor() {
    super();
    this._unsubRange = null;
    this._unsubTrace = null;
    this._x = []; this._yPeak = []; this._ySnr = [];
    this._plotEl = null;
    this._err = null;
  }

  connectedCallback() {
    super.connectedCallback();
    this._unsubRange = store.subscribe("range", () => this._reload());
    this._unsubTrace = ws.subscribe("trace", (data) => this._onLive(data));
  }
  disconnectedCallback() {
    super.disconnectedCallback();
    this._unsubRange?.();
    this._unsubTrace?.();
  }

  async _reload() {
    const r = store.get("range");
    if (!r) return;
    try {
      const resp = await getPeakTrack(r.from, r.to, MAX_PTS);
      this._x = resp.rows.map((p) => new Date(p.t));
      this._yPeak = resp.rows.map((p) => p.peak_power);
      this._ySnr = resp.rows.map((p) => p.snr);
      this._draw();
    } catch (e) { this._err = String(e); }
  }

  _onLive(data) {
    const r = store.get("range");
    if (!r || !r.live) return;
    const { peak, snr } = peakAndSnrOf(data);
    this._x.push(new Date(data.t));
    this._yPeak.push(peak);
    this._ySnr.push(snr);
    while (this._x.length > MAX_PTS) {
      this._x.shift(); this._yPeak.shift(); this._ySnr.shift();
    }
    this._draw();
  }

  _draw() {
    if (!this._plotEl) this._plotEl = this.querySelector("#pp-plot");
    const data = [
      { x: this._x, y: this._yPeak, mode: "lines",
        name: "Peak power (dBm)", line: { width: 1.2 } },
      { x: this._x, y: this._ySnr, mode: "lines",
        name: "SNR (dB)", line: { width: 1.2, dash: "dot" }, yaxis: "y2" },
    ];
    const layout = plotlyLayout({
      height: PLOT_HEIGHT,
      showlegend: true,
      legend: { orientation: "h", y: 1.15 },
      xaxis: { type: "date" },
      yaxis: { title: { text: "Power (dBm)" } },
      yaxis2: {
        title: { text: "SNR (dB)" },
        overlaying: "y", side: "right",
      },
    });
    Plotly.react(this._plotEl, data, layout, plotlyConfig);
  }

  render() {
    return html`
      ${this._err ? html`<div class="muted">${this._err}</div>` : null}
      <div id="pp-plot" style="width:100%;height:${PLOT_HEIGHT}px"></div>
    `;
  }
}

customElements.define("yig-peak-power", YigPeakPower);
```

- [ ] **Step 3: Smoke test.**

Reload. Expected: both peak panels show traces with proper axis units. Live updates animate.

- [ ] **Step 4: Commit.**

```bash
git add frontend/components/yig-peak-track.js frontend/components/yig-peak-power.js
git commit -m "feat(frontend): peak-track + peak-power plots"
```

---

## Task 19: yig-stats component

**Files:**
- Modify: `frontend/components/yig-stats.js`

Polls `/api/stats?window=1h` every 30 s. Renders four key numbers in a clean grid.

- [ ] **Step 1: Replace contents of `frontend/components/yig-stats.js`.**

```javascript
import { LitElement, html } from "lit";
import { getStats } from "/static/lib/api.js";

const POLL_MS = 30 * 1000;

function fmtFreqRate(hzPerHr) {
  const abs = Math.abs(hzPerHr);
  if (abs >= 1e6) return `${(hzPerHr / 1e6).toFixed(2)} MHz/hr`;
  if (abs >= 1e3) return `${(hzPerHr / 1e3).toFixed(2)} kHz/hr`;
  return `${hzPerHr.toFixed(2)} Hz/hr`;
}

function fmtDuration(seconds) {
  if (seconds < 60) return `${seconds.toFixed(0)} s`;
  if (seconds < 3600) return `${(seconds / 60).toFixed(1)} min`;
  if (seconds < 86400) return `${(seconds / 3600).toFixed(2)} hr`;
  return `${(seconds / 86400).toFixed(2)} d`;
}

export class YigStats extends LitElement {
  createRenderRoot() { return this; }
  static properties = {
    _data: { state: true },
    _err: { state: true },
  };

  constructor() {
    super();
    this._data = null;
    this._err = null;
    this._interval = null;
  }

  connectedCallback() {
    super.connectedCallback();
    this._refresh();
    this._interval = setInterval(() => this._refresh(), POLL_MS);
  }

  disconnectedCallback() {
    super.disconnectedCallback();
    if (this._interval) clearInterval(this._interval);
  }

  async _refresh() {
    try {
      this._data = await getStats("1h");
    } catch (e) {
      this._err = String(e);
    }
  }

  render() {
    if (this._err) return html`<div class="muted">${this._err}</div>`;
    if (!this._data) return html`<div class="muted">loading…</div>`;
    const d = this._data;
    return html`
      <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:var(--s-md);">
        <div>
          <div class="value-label">Drift rate (1h)</div>
          <div class="value-big">${fmtFreqRate(d.drift_rate_hz_per_hr)}</div>
        </div>
        <div>
          <div class="value-label">Since last retune</div>
          <div class="value-big">${fmtDuration(d.seconds_since_last_retune)}</div>
        </div>
        <div>
          <div class="value-label">Traces in window</div>
          <div class="value-big">${d.traces_in_window}</div>
        </div>
        <div>
          <div class="value-label">Current SNR</div>
          <div class="value-big">${d.current_snr_db.toFixed(1)} dB</div>
        </div>
      </div>
    `;
  }
}

customElements.define("yig-stats", YigStats);
```

- [ ] **Step 2: Smoke test.**

Reload. Expected: four big numbers populate within 1 second. Numbers update every 30 s.

- [ ] **Step 3: Commit.**

```bash
git add frontend/components/yig-stats.js
git commit -m "feat(frontend): stats panel polling /api/stats"
```

---

## Task 20: yig-history-browser component

**Files:**
- Modify: `frontend/components/yig-history-browser.js`

Range slider over the last 7 days. Two handles (`from`, `to`). Writes `range` to the store; toggling handles disables `live` mode.

- [ ] **Step 1: Replace contents of `frontend/components/yig-history-browser.js`.**

```javascript
import { LitElement, html, css } from "lit";
import { store } from "/static/lib/store.js";

const DAYS = 7;
const MS_PER_DAY = 24 * 60 * 60 * 1000;

function fmt(d) {
  return d.toLocaleString([], {
    year: "numeric", month: "short", day: "numeric",
    hour: "2-digit", minute: "2-digit",
  });
}

export class YigHistoryBrowser extends LitElement {
  createRenderRoot() { return this; }

  static properties = {
    _from: { state: true },
    _to: { state: true },
    _now: { state: true },
  };

  constructor() {
    super();
    this._now = new Date();
    this._from = new Date(this._now.getTime() - 5 * 60 * 1000);
    this._to = new Date(this._now.getTime());
    // Refresh "now" periodically so the slider's right edge always tracks real time
    this._tickInterval = null;
  }

  connectedCallback() {
    super.connectedCallback();
    this._tickInterval = setInterval(() => {
      this._now = new Date();
      this.requestUpdate();
    }, 60_000);
  }
  disconnectedCallback() {
    super.disconnectedCallback();
    if (this._tickInterval) clearInterval(this._tickInterval);
  }

  _earliest() {
    return new Date(this._now.getTime() - DAYS * MS_PER_DAY);
  }

  _onFrom(e) {
    const ms = Number(e.target.value);
    this._from = new Date(this._earliest().getTime() + ms);
    if (this._from >= this._to) {
      this._from = new Date(this._to.getTime() - 60_000);
    }
    this._commit();
  }

  _onTo(e) {
    const ms = Number(e.target.value);
    this._to = new Date(this._earliest().getTime() + ms);
    if (this._to <= this._from) {
      this._to = new Date(this._from.getTime() + 60_000);
    }
    this._commit();
  }

  _liveTail() {
    this._to = new Date();
    if (this._to <= this._from) {
      this._from = new Date(this._to.getTime() - 5 * 60_000);
    }
    this._commit({ live: true });
  }

  _commit(extra = {}) {
    const live = extra.live === true;
    store.set("range", { from: this._from, to: this._to, live, key: "custom" });
  }

  render() {
    const earliestMs = this._earliest().getTime();
    const totalMs = this._now.getTime() - earliestMs;
    const fromVal = this._from.getTime() - earliestMs;
    const toVal = this._to.getTime() - earliestMs;
    return html`
      <div style="display:grid;grid-template-columns:auto 1fr;gap:var(--s-md);align-items:center;">
        <div class="value-label">From</div>
        <input type="range" min="0" max=${totalMs} step="1000" .value=${fromVal}
               @input=${this._onFrom} style="width:100%">
        <div class="value-label">To</div>
        <input type="range" min="0" max=${totalMs} step="1000" .value=${toVal}
               @input=${this._onTo} style="width:100%">
      </div>
      <div style="display:flex;justify-content:space-between;margin-top:var(--s-sm);">
        <div class="muted">${fmt(this._from)} → ${fmt(this._to)}</div>
        <button class="range-btn" @click=${this._liveTail}>Live tail</button>
      </div>
    `;
  }
}

customElements.define("yig-history-browser", YigHistoryBrowser);
```

- [ ] **Step 2: Smoke test.**

Reload. Drag the sliders. Expected: spectrogram, peak track, peak power all redraw to the chosen range. Click "Live tail" — `to` jumps to now and tracks new rows again.

- [ ] **Step 3: Commit.**

```bash
git add frontend/components/yig-history-browser.js
git commit -m "feat(frontend): history browser with dual-range slider"
```

---

## Task 21: Cleanup script + Cloudflared config example

**Files:**
- Create: `scripts/__init__.py` (empty)
- Create: `scripts/cleanup_old_data.py`
- Create: `cloudflared/config.yml.example`

Deletes data older than 7 days. Designed to run from Windows Task Scheduler. Cloudflared config is a template the operator fills in.

- [ ] **Step 1: Create `scripts/cleanup_old_data.py`.**

```python
"""Daily cleanup: delete spectra older than 7 days.

Run via Windows Task Scheduler. Independent of the API. Opens its own
*write* connection — only safe to run when the tracker is paused, OR
DuckDB will queue the writer behind the tracker (single-writer constraint).

In practice: schedule this for a time when the tracker is briefly stopped,
OR accept that it may block until the tracker releases the file.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

import duckdb
from dotenv import load_dotenv


def main() -> int:
    load_dotenv()
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=os.environ.get("YIG_DB_PATH", "spectrum_data_ovn.duckdb"))
    p.add_argument("--retention-days", type=int, default=7)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    log = logging.getLogger("cleanup")

    if not Path(args.db).exists():
        log.error("DB not found: %s", args.db)
        return 1

    conn = duckdb.connect(args.db)
    try:
        cutoff = conn.execute(
            f"SELECT now() - INTERVAL {args.retention_days} DAY"
        ).fetchone()[0]
        n_before = conn.execute("SELECT count(*) FROM spectra").fetchone()[0]
        n_to_delete = conn.execute(
            "SELECT count(*) FROM spectra WHERE time_created < ?",
            [cutoff],
        ).fetchone()[0]
        log.info("DB has %d rows; %d older than %s", n_before, n_to_delete, cutoff)

        if args.dry_run:
            log.info("--dry-run: not deleting")
            return 0

        conn.execute("DELETE FROM spectra WHERE time_created < ?", [cutoff])
        n_after = conn.execute("SELECT count(*) FROM spectra").fetchone()[0]
        log.info("deleted %d rows; now %d", n_before - n_after, n_after)
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Create `cloudflared/config.yml.example`.**

```yaml
# Cloudflare Tunnel config (example).
#
# Setup steps (one-time, on the lab PC):
#   1. cloudflared tunnel login
#   2. cloudflared tunnel create yig-dashboard
#      (this writes credentials to ~/.cloudflared/<UUID>.json)
#   3. cloudflared tunnel route dns yig-dashboard yig.yourdomain.com
#   4. Copy this file to ~/.cloudflared/config.yml and fill in <UUID> + hostname.
#   5. Run as a Windows service:
#      cloudflared service install
#
# Verify with:
#   cloudflared tunnel info yig-dashboard

tunnel: <UUID-FROM-STEP-2>
credentials-file: C:\Users\<you>\.cloudflared\<UUID-FROM-STEP-2>.json

ingress:
  - hostname: yig.yourdomain.com
    service: http://127.0.0.1:8000
  - service: http_status:404
```

- [ ] **Step 3: Smoke test cleanup script (dry-run).**

```bash
uv run python scripts/cleanup_old_data.py --db spectrum_data_ovn.duckdb --dry-run
```
Expected: prints row counts, no rows deleted. (If the DB doesn't exist on the dev machine, this is fine — you'll run it on the lab PC.)

- [ ] **Step 4: Commit.**

```bash
git add scripts/ cloudflared/
git commit -m "feat(ops): cleanup script + cloudflared config template"
```

---

## Task 22: README + CLAUDE.md

**Files:**
- Create: `README.md`
- Create: `CLAUDE.md`

User-facing setup guide and project orientation for future Claude sessions.

- [ ] **Step 1: Create `README.md`.**

```markdown
# YIG Streaming Dashboard

Live web dashboard for the lab's YIG-based oscillator. The tracker process
captures spectrum-analyzer traces 24/7 into a DuckDB file; this FastAPI app
serves a Lit + Plotly frontend that visualises the live trace, spectrogram,
peak frequency drift, peak power & SNR, and derived stats — over the last
7 days of history.

## Prerequisites

- Python 3.11+
- `uv` (or `pip` + `venv`)
- The acquisition tracker (`tracker/duck_db_tracker.py`) running and writing to a DuckDB file.
- For external access: `cloudflared` installed (Cloudflare Tunnel).

## Quickstart (local dev)

1. **Install deps**
   ```bash
   uv sync --all-extras
   ```

2. **Configure env**
   ```bash
   cp .env.example .env
   # Edit .env:
   #   YIG_DASHBOARD_PASSWORD=<pick a password>
   #   YIG_DASHBOARD_SECRET=<32+ random hex chars; e.g. python -c "import secrets;print(secrets.token_hex(32))">
   #   YIG_DB_PATH=spectrum_data_ovn.duckdb
   #   YIG_COLLECTION_CADENCE_SEC=1.0
   #   YIG_DEV_MODE=1   # so cookies work over plain http://
   ```

3. **Make sure a DuckDB file exists.** If the tracker has never run, you can seed
   one with a few synthetic rows:
   ```bash
   uv run python -c "
   import duckdb, datetime as dt, numpy as np
   conn = duckdb.connect('spectrum_data_ovn.duckdb')
   conn.execute('''CREATE TABLE IF NOT EXISTS spectra (
       time_created TIMESTAMP, center_freq DOUBLE, span DOUBLE, rbw DOUBLE,
       n_points INTEGER, powers FLOAT[]
   )''')
   for i in range(60):
       powers = (-60 + 30*np.exp(-((np.linspace(-1,1,501))**2)/0.05)).astype(np.float32).tolist()
       conn.execute('INSERT INTO spectra VALUES (?, ?, ?, ?, ?, ?)',
           [dt.datetime.now() - dt.timedelta(seconds=60-i), 6.46e9, 5e6, 30e3, 501, powers])
   conn.close()
   "
   ```

4. **Run the API**
   ```bash
   uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
   ```

5. **Open the dashboard**
   - Navigate to `http://127.0.0.1:8000/`
   - Log in with the password you set above
   - You should see the live trace, spectrogram, peak track, peak power, stats, and history browser.

## Tests

```bash
uv run pytest -v
```

## Production layout (lab PC)

Three independent processes:

| Process | Run as | Notes |
|---------|--------|-------|
| `tracker/duck_db_tracker.py` | Existing setup (PowerShell window or NSSM service) | Owns the SignalHound. Sole writer. |
| `uvicorn app.main:app --host 127.0.0.1 --port 8000` | Windows service via NSSM | Read-only DB connection. Auto-restart. |
| `cloudflared` | Windows service (`cloudflared service install`) | Forwards `https://yig.yourdomain.com` → `127.0.0.1:8000`. |

Set up the tunnel using `cloudflared/config.yml.example` as a template.

## Scheduled cleanup

Run daily via Windows Task Scheduler:
```
uv run python scripts/cleanup_old_data.py
```
This deletes spectra older than 7 days. Tracker should be briefly stopped or the
script will block until the writer connection releases.

## Backups

The DuckDB file is the only state. Stopping the tracker briefly and copying the
file is a complete backup.

## Architecture

See `docs/superpowers/specs/2026-04-27-yig-streaming-dashboard-design.md` for
the full design spec; `docs/future-ideas.md` for the deferred-features backlog.
```

- [ ] **Step 2: Create `CLAUDE.md`.**

```markdown
# YIG Streaming Dashboard — Claude orientation

This is a single-host streaming dashboard for a lab YIG oscillator.

## What you should know first

- **Two processes, one host.** `tracker/duck_db_tracker.py` is the sole *writer* to `spectrum_data_ovn.duckdb`. The FastAPI app (`app/`) is *read-only*. They share the file directly — no IPC.
- **Read-only DB connection in the API.** All `Database` reads pass through `app/db.py` which uses `duckdb.connect(..., read_only=True)`. Don't add writes.
- **Schema is fixed.** `spectra(time_created, center_freq, span, rbw, n_points, powers)`. No `frequencies` column — the axis is reconstructed as `linspace(center − span/2, center + span/2, n_points)`. The older `plot_spectrogram.py` references a different schema and is kept only as the canonical reference for the spectrogram rendering algorithm.
- **REST + WebSocket transport.** REST handles snapshots and ranges. WebSocket is push-only — the polling watcher (`app/watcher.py`) discovers new rows and broadcasts via `app/ws_manager.py`. Range queries never go over WS.
- **No bundler.** The frontend is Lit + Plotly via `<script type="importmap">`. Static files served directly by FastAPI from `frontend/`.
- **Auth is a single password.** HMAC-signed session cookie. No JWT library. See `app/auth.py`.
- **Spectrogram rendering** mirrors `plot_spectrogram.py`'s `build_grid` + `grid_traces` (NaN-padded global frequency grid + np.interp). Implemented in `frontend/components/yig-spectrogram.js`.

## Layout

```
app/
  config.py     — env-var settings
  db.py         — read-only DuckDB layer + range_rows + peak_track_range
  auth.py       — HMAC cookie sessions + verify_password + dependency factory
  watcher.py    — polling background task; broadcasts new rows
  ws_manager.py — connection set + broadcast (asyncio.gather + prune)
  analytics.py  — drift rate + last-retune helpers
  routes/       — health, auth, api, ws routers
  main.py       — FastAPI app factory + lifespan + static mount

tracker/
  duck_db_tracker.py — existing acquisition; not modified

frontend/
  index.html, login.html, styles.css
  lib/{store, api, ws-client, plotly-theme}.js
  components/yig-{app, header, live-trace, spectrogram, peak-track,
                   peak-power, stats, history-browser}.js

scripts/
  cleanup_old_data.py — daily 7-day retention

cloudflared/
  config.yml.example  — tunnel template

tests/
  conftest.py     — synthetic DuckDB fixture (drift + retunes + noise)
  test_*.py       — unit + integration coverage
```

## Run / test

```bash
uv sync --all-extras
cp .env.example .env  # then edit
uv run pytest -v
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

## What NOT to do

- Don't add a write connection on the API side. Tracker owns writes.
- Don't multiplex range queries onto the WebSocket; REST owns that.
- Don't decode powers on the server for `/api/peak-track` — keep it server-side aggregate (`list_aggregate`, peak idx) so the wire payload is small.
- Don't introduce CORS at v1 — same origin only.
- Don't add a build step to the frontend. The "no node_modules" property matters for ops.
```

- [ ] **Step 3: Commit.**

```bash
git add README.md CLAUDE.md
git commit -m "docs: README + CLAUDE.md orientation"
```

---

## Task 23: Final verification

**Files:** none

End-to-end verification that the system works.

- [ ] **Step 1: Run the full test suite.**

```bash
uv run pytest -v
```
Expected: all tests pass, zero warnings about deprecation that we caused.

- [ ] **Step 2: Run the app, populate live data, and watch the dashboard.**

In one shell:
```bash
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In a second shell:
```bash
uv run python -c "
import duckdb, datetime as dt, numpy as np, time
conn = duckdb.connect('spectrum_data_ovn.duckdb')
conn.execute('''CREATE TABLE IF NOT EXISTS spectra (
    time_created TIMESTAMP, center_freq DOUBLE, span DOUBLE, rbw DOUBLE,
    n_points INTEGER, powers FLOAT[]
)''')
center = 6.46e9
for i in range(120):
    drift = 30 * i  # Hz
    if i == 60: center = 6.461e9  # synthetic retune
    freqs = np.linspace(center - 2.5e6, center + 2.5e6, 501)
    peak_freq = center + drift if i < 60 else center
    powers = (-80 + 50*np.exp(-((freqs - peak_freq)**2)/(2*80e3**2))).astype(np.float32) + np.random.normal(0, 1.5, 501)
    conn.execute('INSERT INTO spectra VALUES (?, ?, ?, ?, ?, ?)',
        [dt.datetime.now(), float(center), 5e6, 30e3, 501, powers.tolist()])
    time.sleep(1)
conn.close()
"
```

In a browser, watch `http://127.0.0.1:8000/`. Expected:
- LED green
- Live trace updates every second
- Spectrogram fills in left-to-right with a viridis heatmap
- Peak frequency plot drifts upward then jumps at the synthetic retune
- Stats panel updates within 30 s

- [ ] **Step 3: Final commit (if any drift).**

```bash
git status   # should be clean
```

---

## Self-review notes

- Spec coverage: §1–§15 all map to tasks above. Auth (§7) → Task 6+10. WebSocket (§6.2) → Tasks 8, 9, 12. Polling (§4) → Task 9. Spectrogram (§5 & §8.3) → Task 17. Stats (§6.1) → Tasks 7, 11, 19. History (§8.2) → Task 20. Ops (§10) → Tasks 21, 22. Tests (§12) → present in Tasks 2–12.
- No placeholders. Every code step is complete.
- Type consistency: `Database` methods, `ConnectionManager` API, store keys, and component event names match across all tasks.
