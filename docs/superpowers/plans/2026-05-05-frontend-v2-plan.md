# YIG Frontend v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the YIG dashboard frontend per the v2 spec — spectrogram-first layout with peak-frequency overlay, auto-zoom-to-peak with manual zoom lock, theme propagation that actually works, server-side frequency clipping for fast 24h ranges, and range-overflow banner.

**Architecture:** Single-branch rewrite (`frontend-v2`). Backend gains `freq_min_hz`/`freq_max_hz` query params on `/api/range` and an `actual_from`/`actual_to` response envelope; everything else is frontend. New Lit components (`yig-kpi-tile`, `yig-banner`, `yig-sidebar`); refactored components (`yig-spectrogram`, `yig-live-trace`, `yig-header`, `yig-app`); deleted components (`yig-stats`, `yig-history-browser`, `yig-peak-track`, `yig-peak-power`).

**Tech Stack:** FastAPI + SQLite (read-only) + WebSocket (push-only) + Lit 3 + Plotly 2.35.2 (no bundler, ESM via importmap).

**Reference spec:** `docs/superpowers/specs/2026-05-05-frontend-v2-design.md`. Read it first.

---

## File map

### Backend
| Path | Action | Purpose |
|---|---|---|
| `app/db.py` | modify | New `earliest_time()`. `range_rows` accepts `freq_min_hz`/`freq_max_hz`. |
| `app/routes/api.py` | modify | `/api/range` accepts/returns new fields; default `max_rows` lowered from 2000 → 600. |
| `tests/test_db.py` | modify | New tests for `earliest_time`, freq clipping. |
| `tests/test_routes_api.py` | modify | New tests for `/api/range` envelope + freq params. |

**Test-fixture conventions (used throughout Phase A):**
- `tests/test_db.py` tests take the `synth_db_path` fixture (a `pathlib.Path`) from `conftest.py`, instantiate `Database(synth_db_path)`, call `.connect()`, run assertions, call `.close()`. The fixture has 600 synthetic rows at 1 Hz starting `2026-04-27T12:00:00` with `center_freq = 6.46335e9`, `span = 5e6`, `n_points = 201`.
- `tests/test_routes_api.py` tests take the `app_with_session` fixture, build the app via `build_app()`, drive it with `httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://t")`, and authenticate by `await c.post("/login", json={"password": "pw"})`. All route tests are `@pytest.mark.asyncio`.

### Frontend libraries
| Path | Action | Purpose |
|---|---|---|
| `frontend/lib/plotly-theme.js` | modify | Add `themeColors()` and `applyTheme(plotEl)`. |
| `frontend/lib/api.js` | modify | `getRange()` accepts optional `freq_min_hz`/`freq_max_hz`. |
| `frontend/lib/auto-zoom.js` | create | Pure function `computeAutoFreqRange(peaks, snrs, latestRow)`. |
| `frontend/lib/store.js` | modify | Initialize `banner: null`, `autoFreqRange: null`, `theme` already present. |

### Frontend components
| Path | Action | Purpose |
|---|---|---|
| `frontend/components/yig-kpi-tile.js` | create | Reusable tile (label/value/unit). |
| `frontend/components/yig-banner.js` | create | Inline notice driven by `store.banner`. |
| `frontend/components/yig-sidebar.js` | create | Owns 4 KPI tiles, subscribes to `latestRow` + `/api/stats`. |
| `frontend/components/yig-spectrogram.js` | rewrite | Heatmap + overlay line + auto-zoom + manual lock + theme refresh. |
| `frontend/components/yig-live-trace.js` | rewrite | Auto-zoom-x + manual lock + theme refresh. |
| `frontend/components/yig-header.js` | modify | Bigger pills, drop subtitle clutter. |
| `frontend/components/yig-app.js` | rewrite | New CSS grid layout, banner slot. |
| `frontend/components/yig-stats.js` | delete | Removed. |
| `frontend/components/yig-history-browser.js` | delete | Removed. |
| `frontend/components/yig-peak-track.js` | delete | Subsumed into spectrogram overlay. |
| `frontend/components/yig-peak-power.js` | delete | Subsumed into KPI tiles. |

### Static
| Path | Action | Purpose |
|---|---|---|
| `frontend/index.html` | modify | Drop deleted component imports. Add new ones. |
| `frontend/styles.css` | modify | New grid class, KPI/banner styles, typography, light-mode tuning. |

---

## Phase A — Backend changes (TDD)

### Task A1: `Database.earliest_time()`

**Files:**
- Modify: `app/db.py`
- Test: `tests/test_db.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_db.py`:

```python
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
```

(`import datetime as dt` and `from app.db import Database` are already at the top of `tests/test_db.py`.)

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_db.py::test_earliest_time_empty_db tests/test_db.py::test_earliest_time_with_rows -v`

Expected: FAIL with `AttributeError: 'Database' object has no attribute 'earliest_time'`

- [ ] **Step 3: Implement `earliest_time` on `Database`**

In `app/db.py`, add this method to the `Database` class (place after `count_rows`):

```python
def earliest_time(self) -> Optional[dt.datetime]:
    """Return the earliest time_created in the table, or None if empty."""
    assert self._conn is not None
    row = self._conn.execute(
        "SELECT time_created FROM spectra ORDER BY time_created ASC LIMIT 1"
    ).fetchone()
    return row[0] if row else None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_db.py::test_earliest_time_empty_db tests/test_db.py::test_earliest_time_with_rows -v`

Expected: 2 passed.

- [ ] **Step 5: Commit**

```
git add app/db.py tests/test_db.py
git commit -m "feat(db): add Database.earliest_time() for range overflow banner"
```

---

### Task A2: `Database.range_rows` frequency clipping

**Files:**
- Modify: `app/db.py` (the `range_rows` method)
- Test: `tests/test_db.py`

The function clips each retained row's powers BLOB to the frequency window `[freq_min_hz, freq_max_hz]` and recomputes `n_points`, `center_freq`, `span` for the clipped slice. Rows whose sweep doesn't overlap the window are skipped entirely.

- [ ] **Step 1: Write failing tests**

Append to `tests/test_db.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify failure**

Run: `uv run pytest tests/test_db.py::test_range_rows_no_freq_clipping_unchanged tests/test_db.py::test_range_rows_clips_to_freq_window tests/test_db.py::test_range_rows_skips_rows_outside_freq_window -v`

Expected: First test passes (no behavior change for existing call). Second and third fail with `TypeError: range_rows() got an unexpected keyword argument 'freq_min_hz'`.

- [ ] **Step 3: Implement freq clipping in `range_rows`**

Replace the `range_rows` method body in `app/db.py`. Full new method:

```python
def range_rows(
    self,
    t_from: dt.datetime,
    t_to: dt.datetime,
    max_rows: int = 2000,
    freq_min_hz: Optional[float] = None,
    freq_max_hz: Optional[float] = None,
) -> list[dict]:
    """Full traces between t_from and t_to, stride-decimated to <=max_rows.

    If freq_min_hz/freq_max_hz are both provided, each row's powers BLOB is
    clipped to the [freq_min_hz, freq_max_hz] window and n_points/center_freq/
    span are recomputed for the clipped slice. Rows whose sweep doesn't
    overlap the freq window are skipped.
    """
    assert self._conn is not None

    total = self._conn.execute(
        "SELECT count(*) FROM spectra WHERE time_created BETWEEN ? AND ?",
        (t_from, t_to),
    ).fetchone()[0]
    if total == 0:
        return []

    stride = max(1, (total + max_rows - 1) // max_rows)
    rows = self._conn.execute(
        f"""
        SELECT {", ".join(_TRACE_COLS)} FROM (
            SELECT {", ".join(_TRACE_COLS)},
                   row_number() OVER (ORDER BY time_created) AS rn
            FROM spectra
            WHERE time_created BETWEEN ? AND ?
        )
        WHERE (rn - 1) % ? = 0
        ORDER BY time_created
        """,
        (t_from, t_to, stride),
    ).fetchall()

    out: list[dict] = []
    do_clip = freq_min_hz is not None and freq_max_hz is not None
    for row in rows:
        d = self._row_to_dict(row, _TRACE_COLS)
        if do_clip:
            clipped = self._clip_row_to_freq(d, freq_min_hz, freq_max_hz)
            if clipped is None:
                continue
            out.append(clipped)
        else:
            out.append(d)
    return out


@staticmethod
def _clip_row_to_freq(
    row: dict, freq_min_hz: float, freq_max_hz: float
) -> Optional[dict]:
    """Slice row['powers'] to the [freq_min_hz, freq_max_hz] window and
    recompute n_points/center_freq/span. Returns None if no overlap."""
    n = int(row["n_points"])
    if n <= 1:
        return None
    center = float(row["center_freq"])
    span = float(row["span"])
    f0 = center - span / 2.0
    df = span / (n - 1)
    sweep_lo = f0
    sweep_hi = f0 + (n - 1) * df
    if freq_max_hz < sweep_lo or freq_min_hz > sweep_hi:
        return None
    lo_idx = max(0, int(np.ceil((freq_min_hz - f0) / df)))
    hi_idx = min(n - 1, int(np.floor((freq_max_hz - f0) / df)))
    if hi_idx < lo_idx:
        return None
    powers = row["powers"][lo_idx : hi_idx + 1]
    new_n = hi_idx - lo_idx + 1
    new_f_lo = f0 + lo_idx * df
    new_f_hi = f0 + hi_idx * df
    new_center = (new_f_lo + new_f_hi) / 2.0
    new_span = new_f_hi - new_f_lo
    return {
        "time_created": row["time_created"],
        "center_freq": new_center,
        "span": new_span,
        "rbw": row["rbw"],
        "n_points": new_n,
        "powers": powers,
    }
```

- [ ] **Step 4: Run tests to verify pass**

Run: `uv run pytest tests/test_db.py -v`

Expected: All db tests pass (existing + 3 new).

- [ ] **Step 5: Commit**

```
git add app/db.py tests/test_db.py
git commit -m "feat(db): freq-window clipping in range_rows"
```

---

### Task A3: `/api/range` envelope + freq params

**Files:**
- Modify: `app/routes/api.py`
- Test: `tests/test_routes_api.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_routes_api.py`. The fixture-from-earliest values are hard-coded against the synth fixture (600 rows at 1 Hz from `2026-04-27T12:00:00`, `center_freq = 6.46335e9`, `span = 5e6`):

```python
import datetime as dt  # ensure imported at top of file
import pytest
from httpx import ASGITransport, AsyncClient


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_routes_api.py -v -k "range_endpoint"`

Expected: failures (new fields missing, freq params not accepted).

- [ ] **Step 3: Update the handler**

Replace the `range_endpoint` function in `app/routes/api.py` with:

```python
@router.get("/range")
async def range_endpoint(
    request: Request,
    t_from: dt.datetime = Query(..., alias="from"),
    t_to: dt.datetime = Query(..., alias="to"),
    max_rows: int = Query(600, ge=1),
    freq_min_hz: float | None = Query(None),
    freq_max_hz: float | None = Query(None),
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
    if (freq_min_hz is None) != (freq_max_hz is None):
        raise HTTPException(
            status_code=400,
            detail="freq_min_hz and freq_max_hz must be specified together",
        )
    if freq_min_hz is not None and freq_max_hz is not None and freq_min_hz >= freq_max_hz:
        raise HTTPException(status_code=400, detail="freq_min_hz must be < freq_max_hz")
    if max_rows > settings.api_max_rows_hard_cap:
        max_rows = settings.api_max_rows_hard_cap

    db = request.app.state.db
    rows = db.range_rows(
        t_from, t_to, max_rows=max_rows,
        freq_min_hz=freq_min_hz, freq_max_hz=freq_max_hz,
    )
    earliest = db.earliest_time()
    if earliest is None:
        actual_from_iso = None
    else:
        actual_from_iso = max(t_from, earliest).isoformat()

    return {
        "rows": [_row_to_trace(r) for r in rows],
        "requested_from": t_from.isoformat(),
        "actual_from": actual_from_iso,
        "requested_to": t_to.isoformat(),
        "actual_to": t_to.isoformat(),
    }
```

Note the `max_rows` default dropped from 2000 to 600 per the spec's perf section.

- [ ] **Step 4: Run tests to verify pass**

Run: `uv run pytest tests/test_routes_api.py -v -k "range_endpoint"`

Expected: all 5 tests pass.

- [ ] **Step 5: Run full suite to confirm nothing broke**

Run: `uv run pytest -v`

Expected: all green. If `test_routes_api.py` had other range tests asserting the old envelope shape (e.g., `body == {"rows": [...]}`), update them to be tolerant of the extra keys (use `assert "rows" in body` rather than `assert body == {...}`).

- [ ] **Step 6: Commit**

```
git add app/routes/api.py tests/test_routes_api.py
git commit -m "feat(api): /api/range envelope + freq window clipping"
```

---

## Phase B — Frontend foundations

### Task B1: `plotly-theme.js` — themeColors() + applyTheme()

**Files:**
- Modify: `frontend/lib/plotly-theme.js`

This file has no tests (frontend has no test framework). Verify by toggling theme in browser at the end of Phase D.

- [ ] **Step 1: Replace the file**

Overwrite `frontend/lib/plotly-theme.js` with:

```js
// Convert CSS custom properties into Plotly layout overrides.
// plotlyLayout(extra) is used for initial draws; themeColors() / applyTheme()
// keep existing figures in sync when the user toggles theme.

function _v(name, fallback = "") {
  return getComputedStyle(document.documentElement)
    .getPropertyValue(name)
    .trim() || fallback;
}

export function themeColors() {
  const text = _v("--c-text-1", "#a4adb7");
  const grid = _v("--c-border", "#232a31");
  const bg1  = _v("--c-bg-1",   "#12161a");
  return {
    paper_bgcolor: bg1,
    plot_bgcolor: bg1,
    "font.color": text,
    "xaxis.gridcolor": grid,
    "xaxis.zerolinecolor": grid,
    "xaxis.linecolor": grid,
    "xaxis.tickcolor": grid,
    "xaxis.color": text,
    "yaxis.gridcolor": grid,
    "yaxis.zerolinecolor": grid,
    "yaxis.linecolor": grid,
    "yaxis.tickcolor": grid,
    "yaxis.color": text,
  };
}

export function applyTheme(plotEl) {
  if (!plotEl || !window.Plotly) return;
  Plotly.relayout(plotEl, themeColors());
}

export function plotlyLayout(extra = {}) {
  const text = _v("--c-text-1", "#a4adb7");
  const grid = _v("--c-border", "#232a31");
  const bg1  = _v("--c-bg-1",   "#12161a");
  const accent = _v("--c-accent", "#4ea1ff");

  const base = {
    paper_bgcolor: bg1,
    plot_bgcolor: bg1,
    font: { family: "Inter, system-ui, sans-serif", color: text, size: 13 },
    margin: { l: 64, r: 28, t: 24, b: 48 },
    xaxis: {
      gridcolor: grid, zerolinecolor: grid, linecolor: grid,
      tickcolor: grid, color: text,
      title: { font: { size: 14 } },
      tickfont: { size: 13 },
    },
    yaxis: {
      gridcolor: grid, zerolinecolor: grid, linecolor: grid,
      tickcolor: grid, color: text,
      title: { font: { size: 14 } },
      tickfont: { size: 13 },
    },
    colorway: [accent],
    showlegend: false,
    uirevision: 0,  // bumped externally to drop user state
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

- [ ] **Step 2: Commit**

```
git add frontend/lib/plotly-theme.js
git commit -m "feat(theme): add themeColors() and applyTheme() helpers"
```

---

### Task B2: `api.js` — getRange signature + new envelope

**Files:**
- Modify: `frontend/lib/api.js`

- [ ] **Step 1: Update `getRange`**

Replace `getRange` in `frontend/lib/api.js` with:

```js
export async function getRange(from, to, max_rows = 600, opts = {}) {
  const params = {
    from: isoLocal(from),
    to: isoLocal(to),
    max_rows: String(max_rows),
  };
  if (opts.freq_min_hz != null && opts.freq_max_hz != null) {
    params.freq_min_hz = String(opts.freq_min_hz);
    params.freq_max_hz = String(opts.freq_max_hz);
  }
  const qs = new URLSearchParams(params);
  return getJSON(`/api/range?${qs}`);
}
```

(Existing callers passing `(from, to, max_rows)` with no opts continue to work.)

- [ ] **Step 2: Commit**

```
git add frontend/lib/api.js
git commit -m "feat(api-client): getRange accepts freq window opts"
```

---

### Task B3: `lib/auto-zoom.js` — auto-zoom math

**Files:**
- Create: `frontend/lib/auto-zoom.js`

This is a pure module, no DOM, no tests, but it exposes a single function the spectrogram and live trace components both use.

- [ ] **Step 1: Create the file**

Write `frontend/lib/auto-zoom.js`:

```js
// Pure auto-zoom math. Caller passes peak data and the latest row's full
// sweep; we return [low, high] in Hz. See spec §"Plot interaction model"
// for derivation.

export const SNR_FLOOR_DB    = 3.0;
export const MIN_BUFFER_HZ   = 2.0e6;   // per-side buffer when peak is stationary
export const BUFFER_FRACTION = 0.2;     // per-side buffer as fraction of motion

/**
 * @param {Array<{peak_freq:number, snr:number}>} peaks
 * @param {{center_freq:number, span:number} | null} latestRow  full-sweep fallback
 * @returns {[number, number] | null}  [low, high] in Hz, or null if no signal
 *          and no fallback.
 */
export function computeAutoFreqRange(peaks, latestRow) {
  const fullSpan = latestRow
    ? [latestRow.center_freq - latestRow.span / 2,
       latestRow.center_freq + latestRow.span / 2]
    : null;

  const good = (peaks || []).filter((p) => p && p.snr >= SNR_FLOOR_DB);
  if (good.length === 0) {
    return fullSpan;
  }

  let fMin = good[0].peak_freq;
  let fMax = good[0].peak_freq;
  for (const p of good) {
    if (p.peak_freq < fMin) fMin = p.peak_freq;
    if (p.peak_freq > fMax) fMax = p.peak_freq;
  }

  const motion = fMax - fMin;
  const buffer = Math.max(MIN_BUFFER_HZ, BUFFER_FRACTION * motion);
  let lo = fMin - buffer;
  let hi = fMax + buffer;
  if (fullSpan) {
    lo = Math.max(lo, fullSpan[0]);
    hi = Math.min(hi, fullSpan[1]);
  }
  return [lo, hi];
}
```

- [ ] **Step 2: Commit**

```
git add frontend/lib/auto-zoom.js
git commit -m "feat(auto-zoom): pure math module for peak-window calculation"
```

---

### Task B4: `store.js` — add banner + autoFreqRange keys

**Files:**
- Modify: `frontend/lib/store.js`

- [ ] **Step 1: Update initial state**

In `frontend/lib/store.js`, find the `export const store = new Store({...})` block and add two keys:

```js
export const store = new Store({
  range: { from: new Date(now - DEFAULT_RANGE_MS), to: new Date(now), live: true, key: "5m" },
  latestRow: null,
  theme: localStorage.getItem("yig-theme") || "dark",
  wsConnected: false,
  lastRowTs: null,
  banner: null,           // { type: "info"|"warn", message: string } | null
  autoFreqRange: null,    // [low, high] in Hz, or null
});
```

- [ ] **Step 2: Commit**

```
git add frontend/lib/store.js
git commit -m "feat(store): banner + autoFreqRange keys"
```

---

## Phase C — New components

### Task C1: `yig-kpi-tile`

**Files:**
- Create: `frontend/components/yig-kpi-tile.js`

- [ ] **Step 1: Create the file**

Write `frontend/components/yig-kpi-tile.js`:

```js
import { LitElement, html } from "lit";

export class YigKpiTile extends LitElement {
  createRenderRoot() { return this; }

  static properties = {
    label: { type: String },
    value: { type: String },
    unit:  { type: String },
    state: { type: String }, // "ok" | "warn" | "bad" | ""
  };

  constructor() {
    super();
    this.label = "";
    this.value = "—";
    this.unit  = "";
    this.state = "";
  }

  render() {
    return html`
      <div class="kpi-tile" data-state=${this.state}>
        <div class="kpi-tile__label">${this.label}</div>
        <div class="kpi-tile__row">
          <span class="kpi-tile__value">${this.value}</span>
          ${this.unit ? html`<span class="kpi-tile__unit">${this.unit}</span>` : null}
        </div>
      </div>
    `;
  }
}

customElements.define("yig-kpi-tile", YigKpiTile);
```

- [ ] **Step 2: Commit**

```
git add frontend/components/yig-kpi-tile.js
git commit -m "feat(ui): yig-kpi-tile component"
```

---

### Task C2: `yig-banner`

**Files:**
- Create: `frontend/components/yig-banner.js`

- [ ] **Step 1: Create the file**

Write `frontend/components/yig-banner.js`:

```js
import { LitElement, html } from "lit";
import { store } from "/static/lib/store.js";

export class YigBanner extends LitElement {
  createRenderRoot() { return this; }

  static properties = {
    _banner: { state: true },
  };

  constructor() {
    super();
    this._banner = null;
  }

  connectedCallback() {
    super.connectedCallback();
    this._unsub = store.subscribe("banner", (b) => { this._banner = b; });
  }
  disconnectedCallback() {
    super.disconnectedCallback();
    this._unsub?.();
  }

  render() {
    if (!this._banner) return null;
    const { type = "info", message } = this._banner;
    return html`
      <div class="banner banner--${type}">
        <span class="banner__icon">${type === "warn" ? "!" : "i"}</span>
        <span class="banner__msg">${message}</span>
      </div>
    `;
  }
}

customElements.define("yig-banner", YigBanner);
```

- [ ] **Step 2: Commit**

```
git add frontend/components/yig-banner.js
git commit -m "feat(ui): yig-banner component bound to store.banner"
```

---

### Task C3: `yig-sidebar`

**Files:**
- Create: `frontend/components/yig-sidebar.js`

The sidebar holds 4 KPI tiles. Three (Peak freq, Peak power, SNR) come from `store.latestRow`. One (Drift / hr) comes from `/api/stats?window=<range.key>` polled on range change + 30 s interval while live.

- [ ] **Step 1: Create the file**

Write `frontend/components/yig-sidebar.js`:

```js
import { LitElement, html } from "lit";
import { store } from "/static/lib/store.js";
import { getStats } from "/static/lib/api.js";

function median(arr) {
  if (!arr.length) return 0;
  const s = [...arr].sort((a, b) => a - b);
  return s[Math.floor(s.length / 2)];
}

function peakFromTrace(trace) {
  let pi = 0;
  for (let i = 1; i < trace.powers.length; i++) {
    if (trace.powers[i] > trace.powers[pi]) pi = i;
  }
  const f0 = trace.center_freq - trace.span / 2;
  const peakFreq = f0 + (pi * trace.span) / (trace.n_points - 1);
  return {
    peakFreq,
    peakPower: trace.powers[pi],
    snr: trace.powers[pi] - median(trace.powers),
  };
}

function fmtFreqGHz(hz) {
  if (hz == null || !isFinite(hz)) return "—";
  return (hz / 1e9).toFixed(6);
}
function fmtDb(v) { return v == null || !isFinite(v) ? "—" : v.toFixed(1); }
function fmtDriftHz(v) {
  if (v == null || !isFinite(v)) return "—";
  if (Math.abs(v) >= 1e6) return (v / 1e6).toFixed(2);
  if (Math.abs(v) >= 1e3) return (v / 1e3).toFixed(1);
  return v.toFixed(0);
}
function driftUnit(v) {
  if (v == null || !isFinite(v)) return "Hz/h";
  if (Math.abs(v) >= 1e6) return "MHz/h";
  if (Math.abs(v) >= 1e3) return "kHz/h";
  return "Hz/h";
}

export class YigSidebar extends LitElement {
  createRenderRoot() { return this; }

  static properties = {
    _peakFreq:  { state: true },
    _peakPower: { state: true },
    _snr:       { state: true },
    _drift:     { state: true },
  };

  constructor() {
    super();
    this._peakFreq  = null;
    this._peakPower = null;
    this._snr       = null;
    this._drift     = null;
    this._driftTimer = null;
  }

  connectedCallback() {
    super.connectedCallback();
    this._unsubLatest = store.subscribe("latestRow", (row) => this._onLatest(row));
    this._unsubRange  = store.subscribe("range", () => this._refreshDrift());
    this._driftTimer  = setInterval(() => this._refreshDrift(), 30_000);
  }
  disconnectedCallback() {
    super.disconnectedCallback();
    this._unsubLatest?.();
    this._unsubRange?.();
    if (this._driftTimer) clearInterval(this._driftTimer);
  }

  _onLatest(row) {
    if (!row) return;
    const { peakFreq, peakPower, snr } = peakFromTrace(row);
    this._peakFreq  = peakFreq;
    this._peakPower = peakPower;
    this._snr       = snr;
  }

  async _refreshDrift() {
    const range = store.get("range");
    const win = range?.key || "5m";
    if (win === "custom") return;  // /api/stats expects 5m/30m/1h/etc.
    try {
      const r = await getStats(win);
      this._drift = r.drift_rate_hz_per_hr;
    } catch (e) {
      // leave previous value
    }
  }

  render() {
    return html`
      <div class="sidebar">
        <yig-kpi-tile label="Peak frequency"
                      .value=${fmtFreqGHz(this._peakFreq)} unit="GHz"></yig-kpi-tile>
        <yig-kpi-tile label="Peak power"
                      .value=${fmtDb(this._peakPower)} unit="dBm"></yig-kpi-tile>
        <yig-kpi-tile label="SNR"
                      .value=${fmtDb(this._snr)} unit="dB"></yig-kpi-tile>
        <yig-kpi-tile label="Drift / hr"
                      .value=${fmtDriftHz(this._drift)} unit=${driftUnit(this._drift)}></yig-kpi-tile>
      </div>
    `;
  }
}

customElements.define("yig-sidebar", YigSidebar);
```

- [ ] **Step 2: Commit**

```
git add frontend/components/yig-sidebar.js
git commit -m "feat(ui): yig-sidebar with 4 KPI tiles"
```

---

## Phase D — Refactor existing components

### Task D1: `yig-spectrogram` — overlay + auto-zoom + lock + theme

**Files:**
- Rewrite: `frontend/components/yig-spectrogram.js`

This is the biggest single component. Plotly figure has TWO traces: trace 0 is the heatmap; trace 1 is the peak-freq overlay line. Auto-zoom math is owned here (it has the peak-track data + WS subscription); the live trace component reads `store.autoFreqRange` to mirror.

- [ ] **Step 1: Replace the file**

Overwrite `frontend/components/yig-spectrogram.js`:

```js
import { LitElement, html } from "lit";
import { getRange, getPeakTrack } from "/static/lib/api.js";
import { ws } from "/static/lib/ws-client.js";
import { store } from "/static/lib/store.js";
import { plotlyLayout, plotlyConfig } from "/static/lib/plotly-theme.js";
import { computeAutoFreqRange, SNR_FLOOR_DB } from "/static/lib/auto-zoom.js";

const MAX_ROWS = 600;

function freqAxis(trace) {
  const { center_freq, span, n_points } = trace;
  const f0 = center_freq - span / 2;
  const out = new Array(n_points);
  for (let i = 0; i < n_points; i++) {
    out[i] = f0 + (i * span) / (n_points - 1);
  }
  return out;
}

function buildGrid(rows) {
  if (rows.length === 0) return { grid: [], binHz: 0 };
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
  return { grid, binHz };
}

function interp(xq, xs, ys) {
  if (xq < xs[0] || xq > xs[xs.length - 1]) return NaN;
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
function lowerBound(arr, target) {
  let lo = 0, hi = arr.length;
  while (lo < hi) { const m = (lo + hi) >> 1; if (arr[m] < target) lo = m + 1; else hi = m; }
  return lo;
}
function upperBound(arr, target) {
  let lo = 0, hi = arr.length;
  while (lo < hi) { const m = (lo + hi) >> 1; if (arr[m] <= target) lo = m + 1; else hi = m; }
  return lo;
}

function gridTraces(rows, grid) {
  const nT = rows.length;
  const nF = grid.length;
  const Z = new Array(nT);
  for (let i = 0; i < nT; i++) {
    const f = freqAxis(rows[i]);
    const p = rows[i].powers;
    const z = new Array(nF);
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

export class YigSpectrogram extends LitElement {
  createRenderRoot() { return this; }
  static properties = { _err: { state: true }, _empty: { state: true } };

  constructor() {
    super();
    this._rows = [];
    this._peaks = [];        // [{t, peak_freq, peak_power, snr, center_freq}]
    this._plotEl = null;
    this._mode = "auto";     // "auto" | "locked"
    this._uirev = 0;
    this._raf = null;
    this._dirty = false;
    this._err = null;
    this._empty = false;
    this._suppressRelayout = false;  // ignore our own relayout calls
  }

  connectedCallback() {
    super.connectedCallback();
    this._unsubRange = store.subscribe("range", () => this._onRangeChange());
    this._unsubTrace = ws.subscribe("trace", (data) => this._onLiveTrace(data));
    // Theme change: re-draw so line colors (read from --c-accent at draw
    // time) update too, not just background/gridline colors.
    this._unsubTheme = store.subscribe("theme", () => this._draw());
  }
  disconnectedCallback() {
    super.disconnectedCallback();
    this._unsubRange?.();
    this._unsubTrace?.();
    this._unsubTheme?.();
    if (this._raf) cancelAnimationFrame(this._raf);
  }

  async _onRangeChange() {
    // New time range → drop user-locked zoom, re-engage auto, refetch.
    this._mode = "auto";
    this._uirev += 1;
    await this._reload();
  }

  async _reload() {
    const range = store.get("range");
    if (!range) return;
    try {
      // 1. Compute the auto freq window from peak-track first (full-sweep
      //    on first fetch since we don't yet know where to clip).
      const peakResp = await getPeakTrack(range.from, range.to, MAX_ROWS);
      this._peaks = peakResp.rows || [];
      const latest = store.get("latestRow");
      const autoRange = computeAutoFreqRange(this._peaks, latest);
      store.set("autoFreqRange", autoRange);

      // 2. Fetch range with the freq window applied (if we have one).
      const opts = autoRange ? { freq_min_hz: autoRange[0], freq_max_hz: autoRange[1] } : {};
      const rangeResp = await getRange(range.from, range.to, MAX_ROWS, opts);
      this._rows = rangeResp.rows || [];
      this._empty = this._rows.length === 0;
      this._maybeBanner(rangeResp);
      this._scheduleDraw();
    } catch (e) {
      this._err = String(e);
    }
  }

  _maybeBanner(resp) {
    const requested = new Date(resp.requested_from).getTime();
    if (resp.actual_from === null) {
      store.set("banner", { type: "info", message: "No data available yet." });
      return;
    }
    const actual = new Date(resp.actual_from).getTime();
    if (actual - requested > 60_000) {
      const have = Math.round((new Date(resp.actual_to).getTime() - actual) / 1000);
      const want = Math.round((new Date(resp.requested_to).getTime() - requested) / 1000);
      store.set("banner", {
        type: "info",
        message: `Showing ${fmtDur(have)} of ${fmtDur(want)} requested. Earliest sample: ${new Date(resp.actual_from).toLocaleTimeString()}.`,
      });
    } else {
      store.set("banner", null);
    }
  }

  _onLiveTrace(data) {
    const range = store.get("range");
    if (!range || !range.live) return;
    // Append peak entry
    const f0 = data.center_freq - data.span / 2;
    let pi = 0;
    for (let i = 1; i < data.powers.length; i++) {
      if (data.powers[i] > data.powers[pi]) pi = i;
    }
    const peakFreq = f0 + (pi * data.span) / (data.n_points - 1);
    const peakPower = data.powers[pi];
    // SNR via median over the *full* sweep (more stable than over the clipped window)
    const sorted = [...data.powers].sort((a, b) => a - b);
    const med = sorted[Math.floor(sorted.length / 2)];
    const snr = peakPower - med;
    this._peaks.push({
      t: data.t, peak_freq: peakFreq, peak_power: peakPower, snr,
      center_freq: data.center_freq,
    });
    if (this._peaks.length > MAX_ROWS) this._peaks.shift();
    // Append row (clip client-side to the current auto range so the heatmap stays consistent)
    const auto = store.get("autoFreqRange");
    const clipped = auto ? this._clipRowToAuto(data, auto) : data;
    if (clipped) {
      this._rows.push(clipped);
      if (this._rows.length > MAX_ROWS) this._rows.shift();
    }
    // Recompute auto range
    if (this._mode === "auto") {
      const newAuto = computeAutoFreqRange(this._peaks, data);
      store.set("autoFreqRange", newAuto);
    }
    this._scheduleDraw();
  }

  _clipRowToAuto(data, auto) {
    const [lo, hi] = auto;
    const f0 = data.center_freq - data.span / 2;
    const df = data.span / (data.n_points - 1);
    const sweepLo = f0;
    const sweepHi = f0 + (data.n_points - 1) * df;
    if (hi < sweepLo || lo > sweepHi) return null;
    const loIdx = Math.max(0, Math.ceil((lo - f0) / df));
    const hiIdx = Math.min(data.n_points - 1, Math.floor((hi - f0) / df));
    if (hiIdx < loIdx) return null;
    const powers = data.powers.slice(loIdx, hiIdx + 1);
    const newN = hiIdx - loIdx + 1;
    const newFLo = f0 + loIdx * df;
    const newFHi = f0 + hiIdx * df;
    return {
      t: data.t,
      center_freq: (newFLo + newFHi) / 2,
      span: newFHi - newFLo,
      rbw: data.rbw,
      n_points: newN,
      powers,
    };
  }

  _scheduleDraw() {
    this._dirty = true;
    if (this._raf) return;
    this._raf = requestAnimationFrame(() => {
      this._raf = null;
      if (this._dirty) {
        this._dirty = false;
        this._draw();
      }
    });
  }

  _draw() {
    if (!this._plotEl) this._plotEl = this.querySelector("#sg-plot");
    if (!this._plotEl) return;
    if (this._rows.length === 0) {
      Plotly.purge(this._plotEl);
      return;
    }
    const { grid } = buildGrid(this._rows);
    const Z = gridTraces(this._rows, grid);
    const xTimes = this._rows.map((r) => new Date(r.t));
    const yFreqGHz = grid.map((f) => f / 1e9);

    // Overlay: peak_freq line in GHz, null where SNR < floor
    const overlayX = this._peaks.map((p) => new Date(p.t));
    const overlayY = this._peaks.map((p) => p.snr >= SNR_FLOOR_DB ? p.peak_freq / 1e9 : null);

    const accent = getComputedStyle(document.documentElement)
      .getPropertyValue("--c-accent").trim() || "#4ea1ff";

    const data = [
      {
        type: "heatmap",
        x: xTimes, y: yFreqGHz, z: transpose(Z),
        colorscale: "Viridis", hoverongaps: false,
        hovertemplate: "%{x}<br>%{y:.6f} GHz<br>%{z:.2f} dBm<extra></extra>",
        colorbar: { title: { text: "dBm" } },
      },
      {
        type: "scattergl",
        x: overlayX, y: overlayY,
        mode: "lines",
        line: { color: accent, width: 1.5 },
        connectgaps: false,
        hovertemplate: "%{x}<br>peak: %{y:.6f} GHz<extra></extra>",
        showlegend: false,
      },
    ];

    const auto = store.get("autoFreqRange");
    const yRange = (this._mode === "auto" && auto)
      ? [auto[0] / 1e9, auto[1] / 1e9]
      : undefined;

    const layout = plotlyLayout({
      xaxis: { type: "date" },
      yaxis: {
        title: { text: "Frequency (GHz)" },
        range: yRange,
      },
      uirevision: this._uirev,
      autosize: true,
    });

    this._suppressRelayout = true;
    Plotly.react(this._plotEl, data, layout, plotlyConfig).then(() => {
      // Bind manual-zoom detection once after first react
      if (!this._relayoutBound) {
        this._plotEl.on("plotly_relayout", (ev) => this._onRelayout(ev));
        this._relayoutBound = true;
      }
      this._suppressRelayout = false;
    });
  }

  _onRelayout(ev) {
    if (this._suppressRelayout) return;
    // User panned/zoomed if the event includes axis range fields.
    const userZoomed =
      "yaxis.range[0]" in ev || "yaxis.range[1]" in ev ||
      "xaxis.range[0]" in ev || "xaxis.range[1]" in ev;
    if (userZoomed && this._mode === "auto") {
      this._mode = "locked";
    }
  }

  render() {
    return html`
      ${this._err ? html`<div class="muted">${this._err}</div>` : null}
      ${this._empty ? html`<div class="muted">no data in window</div>` : null}
      <div id="sg-plot" style="width:100%;height:100%"></div>
    `;
  }

  updated() {
    if (!this._plotEl) {
      this._plotEl = this.querySelector("#sg-plot");
      if (this._plotEl && this._rows.length > 0) this._draw();
    }
  }
}

function fmtDur(sec) {
  if (sec < 60) return `${sec}s`;
  if (sec < 3600) return `${Math.round(sec/60)}m`;
  if (sec < 86400) return `${Math.round(sec/3600)}h`;
  return `${Math.round(sec/86400)}d`;
}

customElements.define("yig-spectrogram", YigSpectrogram);
```

- [ ] **Step 2: Commit**

```
git add frontend/components/yig-spectrogram.js
git commit -m "feat(spectrogram): peak overlay + auto-zoom + manual lock + theme refresh"
```

---

### Task D2: `yig-live-trace` — auto-zoom-x + lock + theme

**Files:**
- Rewrite: `frontend/components/yig-live-trace.js`

- [ ] **Step 1: Replace the file**

Overwrite `frontend/components/yig-live-trace.js`:

```js
import { LitElement, html } from "lit";
import { getSnapshot } from "/static/lib/api.js";
import { ws } from "/static/lib/ws-client.js";
import { store } from "/static/lib/store.js";
import { plotlyLayout, plotlyConfig } from "/static/lib/plotly-theme.js";

export class YigLiveTrace extends LitElement {
  createRenderRoot() { return this; }
  static properties = { _err: { state: true } };

  constructor() {
    super();
    this._lastTrace = null;
    this._plotEl = null;
    this._mode = "auto";
    this._uirev = 0;
    this._err = null;
    this._suppressRelayout = false;
    this._relayoutBound = false;
  }

  connectedCallback() {
    super.connectedCallback();
    this._unsubTrace = ws.subscribe("trace", (data) => this._onTrace(data));
    this._unsubAuto  = store.subscribe("autoFreqRange", () => this._draw());
    this._unsubRange = store.subscribe("range", () => { this._mode = "auto"; this._uirev += 1; this._draw(); });
    this._unsubTheme = store.subscribe("theme", () => this._draw());
    this._init();
  }
  disconnectedCallback() {
    super.disconnectedCallback();
    this._unsubTrace?.();
    this._unsubAuto?.();
    this._unsubRange?.();
    this._unsubTheme?.();
  }

  async _init() {
    try {
      const r = await getSnapshot();
      if (r.data) { this._lastTrace = r.data; this._draw(); }
    } catch (e) {
      this._err = String(e);
    }
  }

  _onTrace(data) {
    this._lastTrace = data;
    this._draw();
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

  _draw() {
    if (!this._plotEl) this._plotEl = this.querySelector("#live-plot");
    if (!this._plotEl || !this._lastTrace) return;

    const x = this._freqAxis(this._lastTrace);
    const data = [{
      x, y: this._lastTrace.powers,
      mode: "lines", line: { width: 1.5 },
      hovertemplate: "%{x:.6f} GHz<br>%{y:.2f} dBm<extra></extra>",
    }];

    const auto = store.get("autoFreqRange");
    const xRange = (this._mode === "auto" && auto)
      ? [auto[0] / 1e9, auto[1] / 1e9]
      : undefined;

    const layout = plotlyLayout({
      xaxis: { title: { text: "Frequency (GHz)" }, range: xRange },
      yaxis: { title: { text: "Power (dBm)" } },
      uirevision: this._uirev,
      autosize: true,
    });

    this._suppressRelayout = true;
    Plotly.react(this._plotEl, data, layout, plotlyConfig).then(() => {
      if (!this._relayoutBound) {
        this._plotEl.on("plotly_relayout", (ev) => this._onRelayout(ev));
        this._relayoutBound = true;
      }
      this._suppressRelayout = false;
    });
  }

  _onRelayout(ev) {
    if (this._suppressRelayout) return;
    const userZoomed =
      "xaxis.range[0]" in ev || "xaxis.range[1]" in ev ||
      "yaxis.range[0]" in ev || "yaxis.range[1]" in ev;
    if (userZoomed && this._mode === "auto") {
      this._mode = "locked";
    }
  }

  render() {
    return html`
      ${this._err ? html`<div class="muted">${this._err}</div>` : null}
      <div id="live-plot" style="width:100%;height:100%"></div>
    `;
  }

  updated() {
    if (!this._plotEl) {
      this._plotEl = this.querySelector("#live-plot");
      if (this._plotEl && this._lastTrace) this._draw();
    }
  }
}

customElements.define("yig-live-trace", YigLiveTrace);
```

- [ ] **Step 2: Commit**

```
git add frontend/components/yig-live-trace.js
git commit -m "feat(live-trace): auto-zoom-x + manual lock + theme refresh"
```

---

### Task D3: `yig-header` — typography + drop subtitle

**Files:**
- Modify: `frontend/components/yig-header.js`

- [ ] **Step 1: Drop subtitle, keep theme toggle as-is**

In `frontend/components/yig-header.js`, find the `render()` method and replace the title block:

Old:
```js
<div class="hdr__title">
  YIG Dashboard
  <small>spectrum_data_ovn</small>
</div>
```

New:
```js
<div class="hdr__title">YIG Dashboard</div>
```

- [ ] **Step 2: Commit**

```
git add frontend/components/yig-header.js
git commit -m "feat(header): drop subtitle clutter"
```

---

### Task D4: `yig-app` — new CSS grid layout

**Files:**
- Rewrite: `frontend/components/yig-app.js`

- [ ] **Step 1: Replace the file**

Overwrite `frontend/components/yig-app.js`:

```js
import { LitElement, html } from "lit";

export class YigApp extends LitElement {
  createRenderRoot() { return this; }

  render() {
    return html`
      <yig-header></yig-header>
      <yig-banner></yig-banner>
      <main class="dash-v2">
        <section class="panel sg">
          <yig-spectrogram></yig-spectrogram>
        </section>
        <section class="panel side">
          <yig-sidebar></yig-sidebar>
        </section>
        <section class="panel live">
          <yig-live-trace></yig-live-trace>
        </section>
      </main>
    `;
  }
}

customElements.define("yig-app", YigApp);
```

- [ ] **Step 2: Commit**

```
git add frontend/components/yig-app.js
git commit -m "feat(app): v2 grid layout with sidebar and banner"
```

---

### Task D5: `index.html` — drop deleted imports, add new

**Files:**
- Modify: `frontend/index.html`

- [ ] **Step 1: Update the module imports block**

Replace the `<script type="module">` content in `frontend/index.html`:

```html
<script type="module">
  import "/static/lib/store.js";
  import "/static/lib/api.js";
  import "/static/lib/ws-client.js";
  import "/static/lib/plotly-theme.js";
  import "/static/lib/auto-zoom.js";
  import "/static/components/yig-app.js";
  import "/static/components/yig-header.js";
  import "/static/components/yig-banner.js";
  import "/static/components/yig-kpi-tile.js";
  import "/static/components/yig-sidebar.js";
  import "/static/components/yig-live-trace.js";
  import "/static/components/yig-spectrogram.js";
</script>
```

- [ ] **Step 2: Commit**

```
git add frontend/index.html
git commit -m "feat(index): swap to v2 component imports"
```

---

### Task D6: `styles.css` — v2 grid + KPI tile + banner + typography

**Files:**
- Modify: `frontend/styles.css`

- [ ] **Step 1: Append v2 styles and tweak base**

Open `frontend/styles.css`. Make four targeted edits and one append.

Edit 1 — in the default `:root` block, change:
```css
--c-text-0: #e6eaf0;
```
to:
```css
--c-text-0: #e8ecf1;
```

Edit 2 — at the end of the default `:root` block (before the closing `}`), add:
```css
--shadow-1: none;
--header-h: 56px;
```

Edit 3 — at the end of the `:root[data-theme="light"]` block, add:
```css
--shadow-1: 0 1px 2px rgba(15, 19, 24, 0.06);
```

Edit 4 — in the `html, body` block, change `font-size: 14px;` to `font-size: 15px;`.

Then append at the end of the file:

```css
/* v2 layout */
.dash-v2 {
  display: grid;
  grid-template-columns: 1fr 320px;
  grid-template-rows: 1fr 200px;
  gap: var(--s-md);
  padding: var(--s-md);
  height: calc(100vh - var(--header-h));
}
.dash-v2 .panel {
  background: var(--c-bg-1);
  border: 1px solid var(--c-border);
  border-radius: var(--radius);
  padding: var(--s-md);
  box-shadow: var(--shadow-1);
  overflow: hidden;
}
.dash-v2 .sg   { grid-column: 1; grid-row: 1; min-height: 0; }
.dash-v2 .side { grid-column: 2; grid-row: 1; min-height: 0; }
.dash-v2 .live { grid-column: 1 / -1; grid-row: 2; min-height: 0; }

.sidebar {
  display: grid;
  grid-template-rows: repeat(4, 1fr);
  gap: var(--s-md);
  height: 100%;
}

.kpi-tile {
  background: var(--c-bg-2);
  border: 1px solid var(--c-border);
  border-radius: var(--radius);
  padding: var(--s-md);
  display: flex;
  flex-direction: column;
  justify-content: center;
}
.kpi-tile__label {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--c-text-2);
  margin-bottom: var(--s-xs);
}
.kpi-tile__row { display: flex; align-items: baseline; gap: var(--s-sm); }
.kpi-tile__value {
  font-family: var(--font-mono);
  font-size: 32px;
  font-weight: 500;
  letter-spacing: 0.01em;
  color: var(--c-text-0);
  font-feature-settings: "tnum";
}
.kpi-tile__unit {
  font-size: 14px;
  color: var(--c-text-2);
  font-family: var(--font-mono);
}

.banner {
  display: flex;
  align-items: center;
  gap: var(--s-sm);
  padding: var(--s-sm) var(--s-md);
  margin: 0 var(--s-md);
  border-radius: var(--radius);
  border: 1px solid var(--c-border);
  background: var(--c-bg-1);
  font-size: 13px;
  color: var(--c-text-1);
}
.banner--warn { border-color: var(--c-warn); }
.banner__icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: var(--c-bg-2);
  font-family: var(--font-mono);
  font-size: 11px;
}
.banner--warn .banner__icon { background: var(--c-warn); color: #15191e; }

.range-btn { padding: var(--s-sm) var(--s-md); font-size: 13px; }
.hdr { padding: var(--s-md) var(--s-lg); }
.hdr__title { font-size: 15px; font-weight: 600; letter-spacing: 0.02em; }
```

- [ ] **Step 2: Commit**

```
git add frontend/styles.css
git commit -m "feat(styles): v2 grid, KPI tile, banner, typography polish"
```

---

## Phase E — Delete obsolete components

### Task E1: Delete the four obsolete components

**Files:**
- Delete: `frontend/components/yig-stats.js`, `yig-history-browser.js`, `yig-peak-track.js`, `yig-peak-power.js`

- [ ] **Step 1: Remove the files**

Run:
```
git rm frontend/components/yig-stats.js frontend/components/yig-history-browser.js frontend/components/yig-peak-track.js frontend/components/yig-peak-power.js
```

- [ ] **Step 2: Commit**

```
git commit -m "chore(ui): delete v1 components subsumed into v2"
```

---

## Phase F — Verification

### Task F1: Run the full backend test suite

- [ ] **Step 1: Run tests**

Run: `uv run pytest -v`

Expected: all green. If any test fails because it called `range_rows` positionally and we changed the signature: that shouldn't happen because we added the new params with defaults at the end, but check.

If the test suite is dirty, fix and commit before proceeding.

---

### Task F2: Manual browser verification

- [ ] **Step 1: Start the dev server**

Run: `uv run uvicorn --factory app.main:build_app --host 127.0.0.1 --port 8000`

- [ ] **Step 2: Run the manual checklist**

Open `http://127.0.0.1:8000/` and walk through every item. Tick each. If any fail, write a follow-up task and fix.

**Layout & visual**
- [ ] Header is sticky at top with bigger range pills.
- [ ] Spectrogram fills the main area; sidebar is to its right (~320 px wide).
- [ ] Live trace strip is below, full width, ~200 px tall.
- [ ] Four KPI tiles in sidebar in order: Peak frequency, Peak power, SNR, Drift / hr.
- [ ] No "Stats" section. No "History (7 days)" section.

**Theme**
- [ ] Click the theme toggle. Plot backgrounds switch between dark and light immediately (no need for new data tick).
- [ ] Plot text colors / gridline colors update too.
- [ ] Toggle back to dark; confirm everything restores.

**Auto-zoom**
- [ ] After a few seconds of live data, the spectrogram y-axis is clipped near the peak (not showing the full sweep).
- [ ] The peak-frequency line is visible on the spectrogram, riding through the ridge of intensity.
- [ ] The live trace x-axis matches the spectrogram y-axis range.
- [ ] If the YIG signal vanishes (e.g., temporarily kill the SA cable in software), the line breaks and the zoom freezes at last-known-good.

**Manual zoom lock**
- [ ] Drag-zoom into a region of the spectrogram. New WS ticks arrive. The zoom does not reset.
- [ ] Click a different range pill (5m → 30m). The view re-fits and auto-zoom re-engages.
- [ ] Click "Reset zoom" in the modebar. Same behavior.

**Range overflow**
- [ ] Restart the tracker (so DB has only a couple minutes of data). Click "24h". Banner appears: "Showing Xm of 24h requested. Earliest sample: ..."
- [ ] Click "5m". Banner disappears.

**Slowness**
- [ ] On a DB with substantial history, click "24h" with auto-zoom on. Plot loads in under 2 seconds.
- [ ] Click "7d". Plot loads (may be slower but should not hang the browser).

**KPI tiles**
- [ ] Tiles show numeric values, not "—", once data flows.
- [ ] Peak frequency shows 6-decimal GHz value.
- [ ] Drift updates when range changes.

If any item fails, stop and create a follow-up task. Don't paper over.

- [ ] **Step 3: Stop the dev server**

Ctrl-C in the terminal.

---

### Task F3: Final summary commit + open PR

- [ ] **Step 1: Verify git status is clean**

Run: `git status`

Expected: nothing to commit (all changes already in granular commits).

- [ ] **Step 2: Push the branch**

Run: `git push -u origin frontend-v2`

- [ ] **Step 3: Open the PR**

Run:

```
gh pr create --title "Frontend v2: spectrogram-first redesign" --body "$(cat <<'EOF'
## Summary
- New layout: dominant spectrogram + sidebar of 4 KPI tiles + thin live-trace strip
- Peak-frequency line overlaid on spectrogram (single source of truth)
- Auto-zoom-to-peak with SNR-floor noise rejection; manual zoom lock via Plotly uirevision
- Theme toggle now propagates to existing plots (was: only on next data tick)
- /api/range gains optional freq window clipping; payload ~7× smaller for typical auto-zoom views
- /api/range envelope adds actual_from/actual_to for range-overflow banner
- Deleted: yig-stats, yig-history-browser, yig-peak-track, yig-peak-power

## Test plan
- [x] Backend: pytest -v all green (added 8 new tests)
- [x] Manual: walked through verification checklist in the plan doc
- [x] Theme toggle works in both directions on every plot
- [x] Manual zoom survives WS ticks; resets on range-pill change
- [x] Range overflow banner shows correct duration phrasing

Spec: docs/superpowers/specs/2026-05-05-frontend-v2-design.md
Plan: docs/superpowers/plans/2026-05-05-frontend-v2-plan.md

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---
