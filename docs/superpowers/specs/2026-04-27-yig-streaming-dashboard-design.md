# YIG Streaming Dashboard — Design Spec

**Date:** 2026-04-27
**Status:** Approved for implementation planning

---

## 1. Overview

A live web dashboard for the lab's YIG-based oscillator. A SignalHound USB-SA124B spectrum analyzer continuously captures power-vs-frequency traces (existing acquisition script, `tracker/duck_db_tracker.py`), writing them to `spectrum_data_ovn.duckdb`. A FastAPI server, running on the same lab PC, exposes that data to a single-page frontend (Lit web components + Plotly) over REST + WebSocket. The dashboard is reachable from outside the lab via a Cloudflare Tunnel and gated by a single shared password. Users can watch live drift, scrub through the last 7 days of history, and read derived stats (drift rate, time since last retune, etc.).

An older `plot_spectrogram.py` exists in the repo and references a different schema (`spectrum_data.duckdb` with a `frequencies` column). It is **not canonical** — the OVN tracker's schema (without `frequencies`, with `n_points` so the axis can be reconstructed) is the v1 source of truth. The plot script is still useful as a reference for rendering algorithms (see §5 and §8.3).

## 2. Goals

- **Live view of YIG drift** — show the current trace and a rolling spectrogram as new data arrives, with sub-2× cadence latency from row insert to browser.
- **History scrubbing over a 7-day rolling window** — drag a range slider, every view re-fetches and updates.
- **Single-host operation** — tracker process and FastAPI process on the same lab PC, sharing one DuckDB file. No remote DB, no separate ingest service.
- **External reach via Cloudflare Tunnel** — collaborators with the URL + password can view from anywhere; no port forwarding, no public IP exposure.
- **Modern, designed look** — neutral palette + one accent, dark default, generous whitespace. Distinct from a stock Grafana panel.
- **Five views**: live trace, spectrogram, peak frequency vs time, peak power & SNR vs time, derived stats panel — plus a 7-day history browser that drives them all.

## 3. Non-goals

- **Multiple instruments / multi-tenant.** v1 is one YIG, one user role.
- **Authoring features (annotations, alerts, replay, sonification, exports).** All parked in `docs/future-ideas.md`.
- **Long-term history / archives beyond 7 days.** Older data is deleted by a daily cleanup script.
- **Real-time control of the instrument from the dashboard.** API is read-only on the data side; the tracker process is the only writer.
- **Strong authentication.** A single shared password is sufficient for v1's threat model (casual access prevention behind a Cloudflare Tunnel).

## 4. Architecture

```
┌────────────────────────────────────────────────────────────────────┐
│ Lab PC                                                             │
│                                                                    │
│  ┌──────────────────────┐         ┌──────────────────────────┐     │
│  │ tracker process      │  WRITE  │  spectrum_data_ovn       │     │
│  │ (duck_db_tracker.py) │────────▶│  .duckdb (file)          │     │
│  │ owns SignalHound SA  │         │  table: spectra          │     │
│  │ runs 24/7            │         └──────────────────────────┘     │
│  └──────────────────────┘                    ▲                     │
│                                              │ READ-ONLY           │
│                                  ┌───────────┴───────────────┐     │
│                                  │ FastAPI + uvicorn         │     │
│                                  │  • REST: range/snapshot   │     │
│                                  │  • WebSocket: live deltas │     │
│                                  │  • Static: Lit frontend   │     │
│                                  │  • Polling watcher (bg)   │     │
│                                  └───────────────────────────┘     │
│                                              ▲                     │
│                                              │  127.0.0.1:8000     │
│                                       ┌──────┴───────┐             │
│                                       │ cloudflared  │             │
│                                       │   tunnel     │             │
│                                       └──────┬───────┘             │
└──────────────────────────────────────────────┼─────────────────────┘
                                               │
                                               ▼
                                  https://<your>.<domain>
                                  password gate → dashboard
```

**Boundaries:**

- **Single writer.** The tracker is the only process that writes to `spectra`. The API never writes data rows.
- **Read-only API connection.** The FastAPI process opens DuckDB with `read_only=True`. DuckDB enforces this — a second writer connection would fail.
- **Background polling watcher.** Lives inside the FastAPI process as a `lifespan` background task. Polls `SELECT … WHERE time_created > $last_seen LIMIT N` at the collection cadence; broadcasts new rows to all connected WebSocket clients.
- **Cloudflare Tunnel terminates HTTPS publicly.** FastAPI binds to `127.0.0.1:8000` only. The tunnel daemon runs as a separate supervised process. Tunnel configuration is **outside the scope of the application code** — documented in README, not in `app/`.

## 5. Data model

The existing schema is unchanged:

```sql
CREATE TABLE spectra (
  time_created TIMESTAMP,
  center_freq  DOUBLE,
  span         DOUBLE,
  rbw          DOUBLE,
  n_points     INTEGER,
  powers       FLOAT[]
);
```

**Canonical DB file:** `spectrum_data_ovn.duckdb` (or whatever path is set in `YIG_DB_PATH`). The older `spectrum_data.duckdb` referenced by `plot_spectrogram.py` is from a previous schema and is not a v1 input.

**One required addition:** an index on `time_created` for range query performance.

```sql
CREATE INDEX IF NOT EXISTS idx_spectra_time ON spectra(time_created);
```

The frequency axis is not stored. It's reconstructed per row as
`np.linspace(center_freq − span/2, center_freq + span/2, n_points)`. This is verified once at tracker startup against the SA's own `frequency_axis()` output (existing logic in `duck_db_tracker.py`).

**Implication for the spectrogram:** because `center_freq` can change mid-stream when the tracker retunes, rows do not share a global frequency axis. The frontend builds a **global frequency grid** spanning the union of all rendered rows, interpolates each row's powers onto that grid (`np.interp`-equivalent in JS), and leaves NaN where a row did not cover. Plotly renders the NaN cells as the plot background, producing the staircase / white-space pattern the user already likes. This algorithm matches `plot_spectrogram.py`'s `build_grid` + `grid_traces` (lines 66–103) exactly — the v1 frontend reproduces that logic in the browser.

## 6. API surface

All `/api/*` routes require an authenticated session cookie (see §7). `/healthz` and `/login` are public.

### 6.1 REST

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/login` | Body `{password}`. On match, set signed session cookie. Else 401. |
| `POST` | `/logout` | Clear session cookie. |
| `GET`  | `/healthz` | Public. Returns liveness facts (see below). |
| `GET`  | `/api/snapshot` | Latest single trace. Used to initialize the live trace view. |
| `GET`  | `/api/range?from=&to=&max_rows=` | Historical window of full traces, server-side decimated to ≤`max_rows`. Default `max_rows=2000`, hard cap `10000`. Reject if `to − from > 7 days` with 400. |
| `GET`  | `/api/peak-track?from=&to=&max_rows=` | `(t, peak_freq, peak_power, snr, center_freq)` per row, computed server-side. Smaller payload than full traces — drives the peak views. Same `max_rows` semantics. |
| `GET`  | `/api/stats?window=1h` | Derived numbers: drift rate, time since last retune, traces collected in window, current SNR. |

**Server-side decimation strategy** (range queries): when `total_rows_in_window > max_rows`, compute `stride = ceil(total / max_rows)` and select rows where `(row_number() OVER (ORDER BY time_created)) % stride == 1`. Even temporal sampling — preserves spectrogram shape, bounded payloads, no rollup tables needed inside the 7-day window.

### 6.2 WebSocket

| Path | Purpose |
|------|---------|
| `WS /ws` | Auth checked at handshake (cookie). Server pushes `{"type":"trace", "data": {t, center_freq, span, rbw, n_points, powers}}` for each new row. `{"type":"ping"}` every 30 s prevents Cloudflare Tunnel from culling idle connections. |

The WebSocket is **server-push only**. Clients do not send range queries or any other application messages over it. Range/snapshot queries always go through REST.

### 6.3 `/healthz` shape

Public, no auth. Returns:

```json
{
  "ok": true,
  "db_path": "spectrum_data_ovn.duckdb",
  "last_row_age_seconds": 1.2,
  "ws_clients": 3,
  "watcher_running": true,
  "stale": false
}
```

`stale` is `true` when `last_row_age_seconds > 2 × collection_cadence`.

## 7. Auth

Deliberately minimal. Single shared password, no user accounts, no roles, no JWT library.

**Two env vars on the FastAPI process:**

- `YIG_DASHBOARD_PASSWORD` — the password the user enters at `/login`.
- `YIG_DASHBOARD_SECRET` — HMAC key for cookie signing. Independent of the password so they can rotate independently.

**Login flow:**

1. `POST /login` with `{password}`. Server compares with `hmac.compare_digest`.
2. On match, server sets a session cookie. Cookie payload: `{"exp": <unix_ts>}` base64-encoded; signed with HMAC-SHA256 over the payload using `YIG_DASHBOARD_SECRET`. Cookie value is `<payload>.<signature>`.
3. Cookie flags: `HttpOnly`, `Secure`, `SameSite=Lax`. Expiry: 30 days. **Dev-mode caveat:** the `Secure` flag prevents the cookie from being set over plain `http://localhost`. The auth module checks an `YIG_DEV_MODE` env var; when set, `Secure` is omitted so local dev works without HTTPS. Production (behind Cloudflare Tunnel) leaves `YIG_DEV_MODE` unset and `Secure` is on.

**Verification (`require_session` dependency):**

1. Read the cookie. If missing → 401.
2. Verify the HMAC signature. If mismatch → 401.
3. Verify `exp > now`. If expired → 401.
4. Return success; the route handler runs.

**WebSocket handshake:** reuses `require_session` on the `WebSocket` route. On 401, the server raises `WebSocketException(code=1008)` ("policy violation").

**Auth-specific failure handling:**

- Wrong password: 401, no rate limiting at v1. (Behind Cloudflare Tunnel; if abuse becomes real, add `slowapi` middleware on `/login`.)
- Cookie tamper: treated identically to "no cookie" → 401.
- Expired cookie: 401 with `WWW-Authenticate: Cookie realm="yig"` so the frontend can disambiguate "logged out" from "wrong password."

## 8. Frontend

### 8.1 Stack

- **Lit** web components, no build step.
- **Plotly** (vendored or imported via `<script type="importmap">` from `esm.sh`). Each view component owns one Plotly figure and exposes a small explicit API; consumers never touch Plotly directly.
- **No bundler / no `node_modules`.** The frontend ships as static files served by FastAPI's `StaticFiles`.
- **Aesthetic:** "modern data product" — dark default with light/dark toggle, neutral grays + one accent, generous whitespace, subtle motion. Viridis (or magma/cividis) preserved for the spectrogram heatmap. Plotly defaults overridden once in `frontend/lib/plotly-theme.js`.

### 8.2 Component tree

```
yig-app  (layout shell)
├── yig-header       (title, theme toggle, range selector, health LED)
├── yig-live-trace   (current power vs frequency)
├── yig-spectrogram  (time × freq heatmap, live + scrub)
├── yig-peak-track   (peak_freq vs time)
├── yig-peak-power   (peak_power & SNR vs time)
├── yig-stats        (derived numbers panel)
└── yig-history-browser  (range slider over 7 days)
```

### 8.3 Component responsibilities

- `yig-app` — composes layout. Owns no application state.
- `yig-header` — health LED, theme toggle, time-range selector. Writes selected `range` to the store; reads `lastRowTs` and `wsConnected` for the LED color (green / amber / red).
- `yig-live-trace` — fetches `/api/snapshot` once on mount; subscribes to `ws-client` `trace` events; calls `Plotly.react()` per new trace. No history rendering.
- `yig-spectrogram` — fetches `/api/range` whenever `store.range` changes; subscribes to `trace` events to append rows when the visible range includes "now"; builds a global frequency grid across visible rows, interpolates each row onto it (NaN-padded outside the row's range), renders one Plotly heatmap with retune gaps showing as plot-background cells. Algorithm mirrors `plot_spectrogram.py`'s `build_grid` + `grid_traces`.
- `yig-peak-track` — fetches `/api/peak-track` whenever range changes; appends from `trace` events.
- `yig-peak-power` — same shape as `yig-peak-track` but plots peak_power and SNR.
- `yig-stats` — polls `/api/stats?window=1h` every 30 s. Pure read of derived numbers.
- `yig-history-browser` — drag-handle slider over the 7-day retention. Writes `range` to the store; all other views react via the store.

### 8.4 Shared infrastructure

- `frontend/lib/api.js` — REST helpers. Handles 401 by redirecting to `/login`.
- `frontend/lib/ws-client.js` — singleton WebSocket connection with exponential-backoff reconnect; event-bus dispatcher (`subscribe('trace', cb)`).
- `frontend/lib/store.js` — minimal reactive store with three properties: `range`, `latestRow`, `theme`. Lit components subscribe via `store.subscribe(prop, cb)`.
- `frontend/lib/plotly-theme.js` — applied once per figure. Sets `font`, `paper_bgcolor`, `plot_bgcolor`, `xaxis.gridcolor`, etc. from the CSS custom properties so themes track correctly.

### 8.5 Pages

- `/` — main dashboard (`index.html` + `<yig-app>`). Requires session cookie; redirects to `/login` on 401.
- `/login` — minimal login form (`login.html`). On success, redirects to `/`.

## 9. Error handling

| Failure | Symptom | Handling |
|---------|---------|----------|
| Tracker process not running | No new rows for >2× cadence | Watcher computes `stale = (now − last_row_ts) > threshold`; `/healthz` reports `stale: true`; frontend header LED goes amber. No exception, no crash. |
| DuckDB file locked at API startup | `IOError` on connect | Retry with exponential backoff (1 s, 2 s, 4 s, capped at 30 s) for up to 5 minutes. Tracker may be mid-write at startup. |
| Read query fails mid-operation | DuckDB exception | Watcher: log WARNING, sleep one cadence, retry. REST: log + return 500. Watcher loop never tears down on a single failure. |
| WebSocket client disconnects | `WebSocketDisconnect` | Remove from broadcast set; do not crash other clients. Broadcast fan-out uses `asyncio.gather(..., return_exceptions=True)`. |
| Cloudflare Tunnel cuts an idle WS | Client receives close | Client auto-reconnects with exponential backoff. Server ping every 30 s prevents this in normal operation. |
| Wrong password / expired cookie | REST: 401. WS: close code 1008. | Frontend intercepts → redirects to `/login`. |
| Range query too wide | `to − from > 7 days` | Reject with 400 *before* the query — the cap is a contract, not a soft limit. |
| Empty range result | No rows in window | Return `{"rows": []}` 200. Views render an empty state. |
| Watcher catches up after FastAPI restart | Bulk of rows in first poll | Broadcast in order, one frame each. New WS clients connecting after the gap get latest via REST snapshot — they don't see the backlog. |

## 10. Operations

**Process layout on the lab PC:**

```
[ tracker ]   [ uvicorn (app.main:app) ]   [ cloudflared ]
     │                  │                         │
     ▼                  ▼                         ▼
spectrum_data_ovn.duckdb    ─────────    https://<your>.<domain>
```

Each process is supervised independently:
- **Tracker:** existing script, ran however the lab currently runs it (PowerShell window, NSSM service, etc.).
- **FastAPI:** `uvicorn app.main:app --host 127.0.0.1 --port 8000`, supervised via Windows Service (NSSM) with auto-restart.
- **Cloudflare Tunnel:** `cloudflared` daemon, configured via `cloudflared/config.yml`, supervised via Windows Service.

**Data cleanup:** `scripts/cleanup_old_data.py` runs daily via Windows Task Scheduler. Executes `DELETE FROM spectra WHERE time_created < now() - INTERVAL 7 DAY`. Independent of the API; does not coordinate with the tracker.

**Secrets:** `.env` file at project root, gitignored. Loaded by `python-dotenv` on app startup. Required vars:
- `YIG_DASHBOARD_PASSWORD`
- `YIG_DASHBOARD_SECRET`
- `YIG_DB_PATH` (path to the `.duckdb` file)
- `YIG_COLLECTION_CADENCE_SEC` (the watcher polls at this rate; matches tracker config)
- `YIG_DEV_MODE` (optional, set in local development to allow non-HTTPS cookies)

**Logging:** structured logs to stdout via `uvicorn` defaults + a small set of `logging.getLogger("yig")` instances.
- INFO: app lifecycle, WS connect/disconnect, watcher tick summaries.
- WARNING: stale data, DB query retries, transient errors.
- ERROR: unhandled exceptions only.
- `LOG_LEVEL` env var gates verbosity.

**No CORS at v1.** Frontend is served by the same FastAPI process (same origin). If a separate dev server is later wanted, allow `http://localhost:3000` in dev only behind an env-var check.

**Backups:** out of scope. The DuckDB file is the only state; copying it is the backup. Documented in README.

## 11. Performance budgets

The design is required to hold the following at v1:

- **WS broadcast latency from row insert:** ≤ 2 × collection cadence (≤ 2 s at 1 Hz).
- **`/api/range` for 1-hour window:** < 100 ms.
- **`/api/range` for 7-day window with stride decimation:** < 1 s.
- **FastAPI process resident memory:** < 200 MB and bounded — does not grow with uptime.
- **Watcher CPU overhead:** < 1% on the lab PC at 1 Hz cadence with 0–10 new rows per poll.

## 12. Testing strategy

- **Framework:** `pytest` + `httpx.AsyncClient` for REST.
- **Synthetic data fixture (`tests/conftest.py`):** generates a temporary DuckDB file populated with realistic YIG-like data — slow drift + occasional retunes + noise — sized to cover all query patterns. Tests run against this fixture, never against the lab DB.
- **Unit tests for `app/db.py`:** each query function against the fixture, including edge cases (empty range, range crossing a retune, oversized range hitting `max_rows`).
- **Auth tests:** valid password → cookie set; wrong password → 401; tampered cookie → 401; expired cookie → 401; valid cookie → access granted.
- **REST endpoint tests:** all `/api/*` paths with `httpx.AsyncClient` against the test app.
- **WebSocket tests:** use `websockets.connect()` against a live `uvicorn` test process bound to an ephemeral port. Cover handshake auth (cookie required), `trace` broadcast, dead-client pruning, and ping cadence.
- **Watcher tests:** insert rows into the fixture DB and assert that the watcher detects them within one cadence and broadcasts to attached WS clients.
- **End-to-end smoke test:** spin up the full app + insert a row + verify it arrives on the WebSocket within 2 × cadence.

## 13. Build sequence

Each phase ends with a green test suite **and** a visibly working artifact.

1. **DuckDB read layer + synthetic fixture.** Move tracker to `tracker/`. Build `app/db.py` and `tests/conftest.py`. Unit tests green. *Visible result:* query functions usable in REPL against synthetic DB.
2. **FastAPI shell + auth + REST.** `app/config.py`, `app/auth.py`, `app/routes/{auth,api,health}.py`, `app/main.py`. *Visible result:* `curl` after login returns real JSON.
3. **WebSocket + polling watcher.** `app/routes/ws.py`, `app/watcher.py`, wired into `lifespan`. *Visible result:* insert a row in the test DB, see it on `wscat`.
4. **Frontend skeleton.** `frontend/index.html`, `login.html`, `styles.css`, `lib/*.js`, `components/{yig-app,yig-header}.js`. FastAPI mounts `frontend/`. *Visible result:* navigate to root, see login → empty dashboard shell with header.
5. **Live trace view (first end-to-end view).** `yig-live-trace`. *Visible result:* updating oscilloscope view in real time. This phase proves the full pipeline.
6. **Spectrogram view.** `yig-spectrogram` — per-row heatmap with retune gaps. *Visible result:* the centerpiece view, live.
7. **Peak views + stats.** `yig-peak-track`, `yig-peak-power`, `yig-stats`. *Visible result:* full v1 dashboard layout.
8. **History browser.** `yig-history-browser` — range slider over 7 days. *Visible result:* scrub back through any past window in retention.
9. **Ops + deploy.** `scripts/cleanup_old_data.py`, `cloudflared/config.yml.example`, `README.md`. *Visible result:* the README walks another machine to a working tunnel.

## 14. Alternatives considered

- **WebSocket-only transport** (one socket, range queries multiplexed onto it). Rejected: harder to debug than REST, harder to test with `curl`. REST + WS hybrid is cleaner.
- **SSE for live updates** instead of WebSocket. Rejected: SSE has occasional buffering surprises through HTTP/1.1 proxies (including some Cloudflare configurations); WebSocket is the better-trodden path here.
- **React/Vue + Vite for the frontend.** Rejected: dashboard is small (≤6 views), Plotly does the visual heavy lifting, and a no-build setup means deploying is "rsync the static folder, restart uvicorn" — which matches the lab-PC operational shape.
- **Server-padded global frequency grid for the spectrogram** (server precomputes `z` matrix and ships it). Rejected: keeps the wire format aligned with storage (per-row), pushes the grid-build/interpolation work to the client where the rendering choices live, and avoids forcing the server to reason about the visible window's union axis. The frontend does the equivalent work in the browser using the algorithm from `plot_spectrogram.py`.
- **Pre-aggregated rollup tables.** Rejected: with a 7-day cap and stride-based decimation, raw `spectra` queries are well under the performance budget.
- **Pub/sub via Redis or named pipe** between tracker and API instead of polling DuckDB. Rejected: polling at 1 Hz on the same disk costs <1 ms/poll; introducing IPC for two co-located processes is unnecessary complexity.
- **Mission-control / lab-instrument / retro-CRT visual directions.** Rejected by user in favor of "modern data product."
- **Multi-instrument schema** (`instrument_id` column, route prefix). Rejected at v1 — only one YIG. Folding in later requires adding a column and renaming routes; not painful.

## 15. Open decisions deferred to implementation

These are intentionally left open for the implementation phase, where the user's hands on the keyboard shape the answer:

- **Synthetic drift model in `conftest.py`** — linear drift? noisy random walk? scheduled retunes at fixed offsets? Affects how realistic every later test feels.
- **Design tokens (palette + accent)** — exact CSS custom properties on `:root`. The choice that makes the dashboard look "designed" rather than generic.
- **Spectrogram grid-bin resolution** — `plot_spectrogram.py` defaults to "median spacing across visible traces." A static value (e.g., RBW) is also reasonable and gives stable cell widths across zoom changes. Both work; the choice affects how the heatmap looks at extreme zoom levels.
- **`drift_rate` definition in `/api/stats`** — kHz/hr from a linear fit over the last hour? Allan deviation at 1 s tau? Total range over the window? Different definitions tell different stories.

These will be resolved during the corresponding build phases (1, 4, 6, 7 respectively), not before.
