# YIG Streaming Dashboard - Claude orientation

This is a single-host streaming dashboard for a lab YIG oscillator.

## What you should know first

- **Two processes, one host.** `tracker/duck_db_tracker.py` is the sole *writer* to `spectrum_data_ovn.duckdb`. The FastAPI app (`app/`) is *read-only*. They share the file directly - no IPC.
- **Read-only DB connection in the API.** All `Database` reads pass through `app/db.py` which uses `duckdb.connect(..., read_only=True)`. Don't add writes.
- **Schema is fixed.** `spectra(time_created, center_freq, span, rbw, n_points, powers)`. No `frequencies` column - the axis is reconstructed as `linspace(center - span/2, center + span/2, n_points)`. The older `plot_spectrogram.py` references a different schema and is kept only as the canonical reference for the spectrogram rendering algorithm.
- **REST + WebSocket transport.** REST handles snapshots and ranges. WebSocket is push-only - the polling watcher (`app/watcher.py`) discovers new rows and broadcasts via `app/ws_manager.py`. Range queries never go over WS.
- **No bundler.** The frontend is Lit + Plotly via `<script type="importmap">`. Static files served directly by FastAPI from `frontend/`.
- **Auth is a single password.** HMAC-signed session cookie. No JWT library. See `app/auth.py`.
- **Spectrogram rendering** mirrors `plot_spectrogram.py`'s `build_grid` + `grid_traces` (NaN-padded global frequency grid + linear interpolation). Implemented in `frontend/components/yig-spectrogram.js`.
- **Naive timestamps both sides.** Tracker writes `datetime.datetime.now()` (naive local). The frontend `api.js` formats range params with `isoLocal()` (no Z suffix) so server-side comparisons match.

## Layout

```
app/
  config.py     - env-var settings
  db.py         - read-only DuckDB layer + range_rows + peak_track_range
  auth.py       - HMAC cookie sessions + verify_password + dependency factory
  watcher.py    - polling background task; broadcasts new rows
  ws_manager.py - connection set + broadcast (asyncio.gather + prune)
  analytics.py  - drift rate + last-retune helpers
  routes/       - health, auth, api, ws routers
  main.py       - FastAPI app factory + lifespan + static mount

tracker/
  duck_db_tracker.py - existing acquisition; not modified

frontend/
  index.html, login.html, styles.css
  lib/{store, api, ws-client, plotly-theme}.js
  components/yig-{app, header, live-trace, spectrogram, peak-track,
                  peak-power, stats, history-browser}.js

scripts/
  cleanup_old_data.py - daily 7-day retention

cloudflared/
  config.yml.example  - tunnel template

tests/
  conftest.py     - synthetic DuckDB fixture (drift + retunes + noise)
  test_*.py       - 42 unit + integration tests
```

## Run / test

```bash
uv sync --all-extras
cp .env.example .env  # then edit
uv run pytest -v
uv run uvicorn --factory app.main:build_app --host 127.0.0.1 --port 8000
```

Note the `--factory` flag: `build_app` is a function, not a module-level
instance, so env vars can be set before the app is built.

## What NOT to do

- Don't add a write connection on the API side. Tracker owns writes.
- Don't multiplex range queries onto the WebSocket; REST owns that.
- Don't decode powers on the server for `/api/peak-track` - keep it
  server-side aggregate (`list_aggregate`, peak idx) so the wire payload
  is small.
- Don't introduce CORS at v1 - same origin only.
- Don't add a build step to the frontend. The "no node_modules" property
  matters for ops.
- Don't switch to UTC ISO strings for range params from the frontend - the
  DB stores naive local timestamps.
