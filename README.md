# YIG Streaming Dashboard

Live web dashboard for the lab's YIG-based oscillator. The tracker process
captures spectrum-analyzer traces 24/7 into a DuckDB file; this FastAPI app
serves a Lit + Plotly frontend that visualises the live trace, spectrogram,
peak frequency drift, peak power & SNR, and derived stats - over the last
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
   #   YIG_DASHBOARD_SECRET=<32+ random hex chars>
   #   YIG_DB_PATH=spectrum_data_ovn.duckdb
   #   YIG_COLLECTION_CADENCE_SEC=1.0
   #   YIG_DEV_MODE=1   # so cookies work over plain http://
   ```

   To generate a secret:
   ```bash
   uv run python -c "import secrets; print(secrets.token_hex(32))"
   ```

3. **Make sure a DuckDB file exists.** If the tracker has never run, you can seed
   one with synthetic data for testing:
   ```bash
   uv run python -c "
   import duckdb, datetime as dt, numpy as np
   conn = duckdb.connect('spectrum_data_ovn.duckdb')
   conn.execute('''CREATE TABLE IF NOT EXISTS spectra (
       time_created TIMESTAMP, center_freq DOUBLE, span DOUBLE, rbw DOUBLE,
       n_points INTEGER, powers FLOAT[]
   )''')
   for i in range(120):
       freqs = np.linspace(6.46e9 - 2.5e6, 6.46e9 + 2.5e6, 201)
       powers = (-80 + 50*np.exp(-((freqs - 6.46e9)**2)/(2*80e3**2))).astype(np.float32).tolist()
       conn.execute('INSERT INTO spectra VALUES (?, ?, ?, ?, ?, ?)',
           [dt.datetime.now() - dt.timedelta(seconds=120-i), 6.46e9, 5e6, 30e3, 201, powers])
   conn.close()
   "
   ```

4. **Run the API**
   ```bash
   uv run uvicorn --factory app.main:build_app --host 127.0.0.1 --port 8000
   ```

5. **Open the dashboard**
   - Navigate to `http://127.0.0.1:8000/`
   - Log in with the password you set above
   - You should see the live trace, spectrogram, peak track, peak power, stats,
     and history browser.

## Tests

```bash
uv run pytest -v
```

42 backend tests covering db, auth, analytics, ws_manager, watcher, all routes,
and the WebSocket handshake.

## Production layout (lab PC)

Three independent processes:

| Process | Run as | Notes |
|---------|--------|-------|
| `tracker/duck_db_tracker.py` | Existing setup (PowerShell window or NSSM service) | Owns the SignalHound. Sole writer. |
| `uvicorn --factory app.main:build_app --host 127.0.0.1 --port 8000` | Windows service via NSSM | Read-only DB connection. Auto-restart. |
| `cloudflared` | Windows service (`cloudflared service install`) | Forwards `https://yig.yourdomain.com` -> `127.0.0.1:8000`. |

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
