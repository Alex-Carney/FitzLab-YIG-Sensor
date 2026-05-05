# YIG Dashboard — Frontend v2 Design

Status: approved 2026-05-05
Branch: `frontend-v2`

## Goals

The v1 dashboard ran for a week and proved the streaming pipeline works. The frontend itself is the bottleneck: ugly, slow on long ranges, broken light mode, and most plot area is wasted noise floor. This v2 fixes that without touching the tracker, the SQLite schema, or the WebSocket protocol envelope.

Specifically:

1. **Spectrogram-first layout.** One dominant heatmap with a peak-frequency line overlaid, a 320 px sidebar of KPI tiles, and a thin live-trace strip.
2. **Auto-zoom-to-peak.** Both the spectrogram (y-axis) and the live trace (x-axis) clip to the actual peak motion range plus a small buffer. Wide sweeps no longer waste 90 % of the plot showing noise floor.
3. **Manual zoom that survives live updates.** Drag-zoom into a region and your view stays put across every WS tick until you pick a new time range or click "Reset zoom".
4. **Theme that actually works.** Light mode flips backgrounds, gridlines, and font colors on existing plots — not just on the next data tick.
5. **Long ranges that don't hang.** Server clips power BLOBs to the visible frequency window before encoding; range queries shrink ~7×.
6. **Range overflow that doesn't bug out.** Asking for 24 h with 5 min of data shows the available 5 min plus an inline banner.
7. **Polish.** Modern data-product aesthetic (Inter Display + JetBrains Mono, generous whitespace, one accent color, large readable numbers).

Out of scope: tracker changes, schema changes, multi-instrument support, export/download features, notification system. The v2 is purely a frontend redesign plus the minimum backend changes the new frontend needs.

## Layout

The page is a CSS grid. Header is sticky on top. Below it, two rows: a main row (spectrogram + sidebar) and a strip row (live trace).

```
┌─ yig-header (sticky) ───────────────────────────────────────┐
│  YIG Dashboard      [5m 30m 1h 6h 24h 7d]   [LED]  ☀ ⏻     │
├──────────────────────────────────────────────┬──────────────┤
│                                              │  KPI tiles   │
│         yig-spectrogram                      │              │
│         (heatmap + peak-freq overlay         │  Peak freq   │
│          + auto-zoom y-axis                  │  Peak power  │
│          + manual zoom lock)                 │  SNR         │
│                                              │  Drift / hr  │
├──────────────────────────────────────────────┴──────────────┤
│  yig-live-trace (frequency × power, x-range matches         │
│                  spectrogram y-range)                        │
└──────────────────────────────────────────────────────────────┘
```

CSS grid spec:

```css
.dash-v2 {
  display: grid;
  grid-template-columns: 1fr 320px;
  grid-template-rows: 1fr 200px;
  gap: var(--s-md);
  padding: var(--s-md);
  height: calc(100vh - var(--header-h));
}
.dash-v2 .sg   { grid-column: 1; grid-row: 1; }
.dash-v2 .side { grid-column: 2; grid-row: 1; }
.dash-v2 .live { grid-column: 1 / -1; grid-row: 2; }
```

Spectrogram plot fills its grid cell (`width:100%; height:100%`); CSS grid sizing replaces the v1 fixed `PLOT_HEIGHT = 360`. Live trace strip is exactly 200 px tall.

A small `yig-banner` slot lives above the spectrogram cell (between header and main row) for the range-overflow notice. Hidden when no banner is active.

## Components

### New

| Component | File | Purpose |
|---|---|---|
| `yig-kpi-tile` | `frontend/components/yig-kpi-tile.js` | One tile: label, big mono value, unit, optional trend chip. Reusable. |
| `yig-banner` | `frontend/components/yig-banner.js` | Inline notice with info/warn variants. Driven by `store.banner`. |
| `yig-sidebar` | `frontend/components/yig-sidebar.js` | Container that owns the four `yig-kpi-tile` instances and their data subscriptions. |

### Modified

| Component | File | Changes |
|---|---|---|
| `yig-app` | `frontend/components/yig-app.js` | New CSS grid; emit `--header-h` custom property; render `yig-banner` slot. |
| `yig-header` | `frontend/components/yig-header.js` | Larger range pills, theme toggle publishes `theme` event already (kept), drop `<small>spectrum_data_ovn</small>` clutter. |
| `yig-spectrogram` | `frontend/components/yig-spectrogram.js` | Add peak-freq line overlay (Plotly trace 1 over the heatmap trace 0); add auto-zoom-y; add manual-zoom-lock via `uirevision`; add theme refresh subscription; switch live-tick path from `react()` to `restyle/extendTraces`. |
| `yig-live-trace` | `frontend/components/yig-live-trace.js` | Add auto-zoom-x (range matches spectrogram's y-range); add manual-zoom-lock; add theme refresh subscription; switch live-tick path. |
| `plotly-theme.js` | `frontend/lib/plotly-theme.js` | Add `themeColors()` (returns live colors from CSS vars) and `applyTheme(plotEl)` (calls `Plotly.relayout` with current colors). |
| `styles.css` | `frontend/styles.css` | New v2 grid class, KPI tile styles, banner styles, retuned light-mode palette, larger base font (15 px → 16 px) and larger axis-label sizes. |
| `app/routes/api.py` | `app/routes/api.py` | `/api/range` gains optional `freq_min_hz` and `freq_max_hz` query params; response gains `actual_from`, `actual_to`. |
| `app/db.py` | `app/db.py` | `Database.range_rows` accepts optional `freq_min_hz`, `freq_max_hz`; clips powers BLOB to the freq window in Python. New `Database.earliest_time()` for the banner. |
| `index.html` | `frontend/index.html` | Drop deleted component imports. |

### Deleted

| Component | File | Reason |
|---|---|---|
| `yig-stats` | `frontend/components/yig-stats.js` | Stats panel removed. Drift becomes a KPI tile. |
| `yig-history-browser` | `frontend/components/yig-history-browser.js` | 7-day from/to slider removed; range pills in header are sufficient. |
| `yig-peak-track` | `frontend/components/yig-peak-track.js` | Subsumed into spectrogram peak-freq overlay + KPI tile. |
| `yig-peak-power` | `frontend/components/yig-peak-power.js` | Subsumed into KPI tiles (peak power + SNR). |

`/api/stats` stays alive — drift KPI tile fetches it on range change and every 30 s while live. `/api/peak-track` stays alive — used by spectrogram for the overlay line and by auto-zoom math.

### KPI tile data flow

The four sidebar tiles have different freshness characteristics:

| Tile | Source | Update on |
|---|---|---|
| Peak frequency | `store.latestRow` (latest WS broadcast, regardless of selected range) | every WS tick |
| Peak power | `store.latestRow` (computed client-side: `max(powers)`) | every WS tick |
| SNR | `store.latestRow` (computed client-side: `max(powers) - median(powers)`) | every WS tick |
| Drift / hr | `/api/stats?window=<current range key>` | range change + every 30 s while live |

KPI tiles always reflect the most recent state of the YIG, **even when the user is browsing a historical range**. They are "live status indicators", not "summary of the displayed range". The spectrogram and live trace are scoped to the displayed range; the tiles are not. This is consistent with v1 behavior of the now-deleted `yig-stats` panel (it showed a `current_snr_db` independent of the selected stats window).

Drift is the one tile that is range-scoped: `/api/stats` takes a `window` parameter and the drift tile passes the current range's `key` (`"5m"`, `"30m"`, etc.) so users can see "drift over the last 5 minutes" vs "drift over the last hour".

## Aesthetic

Modern data-product. Concrete styling rules:

- **Type stack.** `Inter Display` 14–18 px for UI text (headers, labels, tile labels). `JetBrains Mono` for all numbers (KPI values, axis ticks where appropriate, hover values). Tabular figures (`font-feature-settings: "tnum"`).
- **KPI value size.** 32 px, `font-weight: 500`, `letter-spacing: 0.01em`. Unit suffix at 14 px in `--c-text-2`.
- **Plot text size.** Axis tick labels 13 px, axis titles 14 px (up from Plotly's 12 px default). Hover tooltips 13 px.
- **Palette (dark, default).** Bg 0 `#0b0d10`, Bg 1 `#12161a`, Bg 2 `#1a1f25`, border `#232a31`, text 0 `#e8ecf1`, text 1 `#a4adb7`, text 2 `#6b7480`, accent `#4ea1ff`. Same as v1 but text 0 bumped one stop brighter for legibility.
- **Palette (light).** Bg 0 `#f8f9fb`, Bg 1 `#ffffff`, Bg 2 `#eef1f5`, border `#d8dde3`, text 0 `#15191e`, text 1 `#5a626c`, text 2 `#8a929c`, accent `#2c7fe0`. Same as v1.
- **Surfaces.** 1 px border, 8 px radius, no shadows in dark mode, subtle 0 1px 2px shadow in light mode.
- **Spectrogram colorscale.** Viridis stays — works in both modes.
- **Peak overlay line.** `--c-accent` (cyan/blue), 1.5 px, no markers. Single solid line, not dashed — overlaid traces should be visually distinct from the heatmap and from any future overlays.
- **Peak overlay missing-data behavior.** Points with SNR below `SNR_FLOOR_DB` (3 dB) emit `y = null` so Plotly breaks the line there. This visually communicates "we lost the peak in noise" rather than drawing a junk trajectory through noise-floor maxima.

## Plot interaction model

### Auto-zoom math

The auto-zoom range is computed **once per data event** and shared between the spectrogram (y-axis) and the live trace (x-axis), so the two plots stay visually aligned. The result lives in `store.autoFreqRange` and updates whenever a `/api/range` fetch completes or a new WS tick is appended in live mode.

```
Inputs:
  peak_freqs    = peak_freq values from /api/peak-track (current range)
                  + peak_freq values from WS ticks since last fetch
                  (WS ticks contribute only when range.live === true)
  snrs          = corresponding SNR values
  full_span     = [center_freq - span/2, center_freq + span/2] from latest row

Filter:
  good = [(f, s) for f, s in zip(peak_freqs, snrs) if s >= SNR_FLOOR_DB]

Compute:
  if good is empty:
    auto_range = full_span  (fall back; "no peak detected")
  else:
    f_min = min(f for f, _ in good)
    f_max = max(f for f, _ in good)
    motion = f_max - f_min
    buffer = max(MIN_BUFFER_HZ, BUFFER_FRACTION * motion)  # per-side buffer
    auto_range = [f_min - buffer, f_max + buffer]
    # clamp to full_span — never zoom outside actual sweep
    auto_range = [max(auto_range[0], full_span[0]),
                  min(auto_range[1], full_span[1])]
```

Constants (tunable, surfaced as JS module-level consts):

```js
const SNR_FLOOR_DB    = 3.0;     // below this, treat row as "no peak"
const MIN_BUFFER_HZ   = 2.0e6;   // 2 MHz minimum *per-side* buffer
                                 // → minimum visible window when peak is stationary is 4 MHz
const BUFFER_FRACTION = 0.2;     // 20% of motion range, per side
```

The 3 dB floor prevents auto-zoom from chasing the noise floor when the signal vanishes. With 3 dB the zoom freezes at last-known-good position. This is configurable; a future enhancement could surface it in the UI.

### Manual zoom lock (uirevision pattern)

Each auto-zooming plot tracks state:

```js
{
  mode: "auto" | "locked",
  uirev: <integer>,          // bumped to force Plotly to drop user state
  manualRange: [low, high],  // captured when user pans/zooms
}
```

Behavior:

- **mode = "auto", new data tick (WS):** call `Plotly.restyle(el, { z: [...] }, [0])` for spectrogram or `Plotly.restyle(el, { y: [...] }, [0])` for live trace, *then* `Plotly.relayout(el, { 'yaxis.range': autoRange, ...themeColors() })`. Axes update with auto-zoom math.
- **mode = "auto", user drags-zooms (`plotly_relayout` event with `'yaxis.range[0]'` present):** transition to `mode = "locked"`. Capture the new range. `uirev` unchanged.
- **mode = "locked", new data tick:** call `Plotly.restyle()` with new data only. *Do not* call `relayout` on axis ranges. Plotly preserves the user's manual range because `uirevision` in the figure layout hasn't changed.
- **mode = "locked", time range pill clicked (5m → 30m):** bump `uirev`, set `mode = "auto"`. Triggers a fresh `/api/range` fetch + `Plotly.react()` with the new `uirevision` token, which causes Plotly to drop the captured user range. Auto-zoom re-engages on first new data.
- **mode = "locked", "Reset zoom" button (modebar custom button):** same as time-range click — bump `uirev`, set `mode = "auto"`.

The `uirevision` value lives in the layout object passed to `Plotly.react()`. As long as it's the same token across two `react` calls, Plotly preserves user state. Bumping it (e.g., `uirev = (uirev || 0) + 1`) tells Plotly "this is a fresh figure, drop user state."

### Live-tick update path

The v1 bug is that every WS tick calls `Plotly.react(el, data, layout, config)` — passing a fresh `layout` object with default axis ranges. Even when `data` keeps the same length, Plotly's diffing eventually applies the new layout and clobbers the user's pan/zoom.

The v2 fix has two layers: `uirevision` (above) preserves user state across `react()` calls; the live-tick path skips `react()` entirely and uses `restyle`/`extendTraces` for data changes plus `relayout` for axis updates. This is faster (no full diff) and side-steps the `react`-clobbers-axes issue when in auto mode.

For the spectrogram specifically, when a new row arrives via WS:

1. Append `(t, clipped_powers)` to in-memory rows. If `len > MAX_ROWS`, shift oldest.
2. Compute new `auto_range` if mode is auto.
3. `Plotly.restyle(el, { z: [transposed_Z] }, [0])` (the heatmap trace).
4. If overlay needs update: `Plotly.restyle(el, { x: [overlayX], y: [overlayY] }, [1])` (the peak-freq line trace).
5. If mode is auto: `Plotly.relayout(el, { 'yaxis.range': autoRange })`.

For the live trace:

1. `Plotly.restyle(el, { x: [newFreqAxis], y: [newPowers] }, [0])`.
2. If mode is auto: `Plotly.relayout(el, { 'xaxis.range': autoRange })`.

## Backend changes

### `/api/range` — frequency window clipping

Current signature: `GET /api/range?from=...&to=...&max_rows=...`.

V2 signature: `GET /api/range?from=...&to=...&max_rows=...&freq_min_hz=...&freq_max_hz=...` (both freq params optional). When `freq_min_hz` and `freq_max_hz` are present, the server decodes each retained row's powers BLOB, slices to the frequency window, and returns only those points along with the clipped `n_points`, `center_freq`, and `span` fields recomputed for the clipped slice (so the frontend can still reconstruct the frequency axis from `linspace(center - span/2, center + span/2, n_points)`).

Handler logic (pseudocode):

```python
@router.get("/range")
async def range_endpoint(... freq_min_hz: float | None = None,
                              freq_max_hz: float | None = None):
    rows = db.range_rows(t_from, t_to, max_rows=max_rows,
                         freq_min_hz=freq_min_hz, freq_max_hz=freq_max_hz)
    earliest = db.earliest_time()  # None if DB is empty
    if earliest is None:
        actual_from = None  # signals "no data exists"
    else:
        actual_from = max(t_from, earliest)
    return {
        "rows": [_row_to_trace(r) for r in rows],
        "requested_from": t_from.isoformat(),
        "actual_from": actual_from.isoformat() if actual_from else None,
        "requested_to": t_to.isoformat(),
        "actual_to": t_to.isoformat(),
    }
```

`Database.range_rows` clips inside its decode loop (server-side, not in handler) so the BLOB is never converted to a Python list of all 201 floats — just the subset inside `[freq_min_hz, freq_max_hz]`.

### `/api/peak-track` — unchanged

Already returns small payloads (peak per row). Used by:

- Spectrogram for the overlay line.
- Auto-zoom math (peak motion range computation).
- KPI tiles read latest values (peak_power, SNR) from this endpoint when not in live mode.

### `/api/stats` — unchanged

Returns `drift_rate_hz_per_hr`, `seconds_since_last_retune`, `traces_in_window`, `current_snr_db`. Drift KPI tile consumes `drift_rate_hz_per_hr` only. Other fields are not surfaced in v2 UI but the endpoint stays for parity / future use.

### `/ws` — unchanged envelope

WS continues to push `{type: "trace", data: {...full row including powers...}}`. The KPI tiles, spectrogram (for the new column), and live trace all consume the same broadcast. No changes to `app/watcher.py` or `app/ws_manager.py`.

## Performance

Two changes, in expected impact order:

1. **Frequency clipping at the server** (biggest win). For a typical 24h window with auto-zoom on, the visible frequency range is e.g. ±2 MHz around peak motion — maybe 30 of 201 bins. That's a ~7× payload shrink and a ~7× drop in Python `float()` casts. Implemented via the new `freq_min_hz`/`freq_max_hz` params.
2. **Lower default `max_rows` from 2000 to 600.** A 1080p browser viewport has roughly 1500 horizontal pixels for the spectrogram; 600 columns is still oversampled, and Plotly's heatmap rendering scales O(nT × nF). Drops typical render cost by ~3×.

Not in scope for v2: msgpack/binary transport, server-side power downsampling beyond freq clipping, indexed views. If the two changes above don't make 24h ranges feel snappy, msgpack lands in v2.1.

## Range overflow handling

When the user requests a window `[t_from, t_to]` and the earliest data is at `t_earliest > t_from`:

1. Server returns rows starting from `t_earliest` (already happens — the SQL `BETWEEN` just returns nothing earlier). Critically, the response now includes `actual_from = t_earliest.isoformat()`.
2. Frontend compares `requested_from` vs `actual_from`. If `(actual_from - requested_from) > 60_000 ms`, set `store.banner = { type: "info", message: "Showing X of Y requested. Earliest sample: Z." }`.
3. `yig-banner` renders that store value.
4. Banner clears automatically when the user picks a smaller range (next `/api/range` response with no gap).

If the database is empty entirely, server returns `actual_from = null`, frontend shows banner: "No data available yet."

## Theme system

Two helpers added to `frontend/lib/plotly-theme.js`:

```js
export function themeColors() {
  // reads CSS custom properties live and returns Plotly-shaped object
  return {
    paper_bgcolor: cssVar("--c-bg-1"),
    plot_bgcolor: cssVar("--c-bg-1"),
    "font.color": cssVar("--c-text-1"),
    "xaxis.gridcolor": cssVar("--c-border"),
    "xaxis.linecolor": cssVar("--c-border"),
    "xaxis.tickcolor": cssVar("--c-border"),
    "xaxis.color": cssVar("--c-text-1"),
    "yaxis.gridcolor": cssVar("--c-border"),
    "yaxis.linecolor": cssVar("--c-border"),
    "yaxis.tickcolor": cssVar("--c-border"),
    "yaxis.color": cssVar("--c-text-1"),
  };
}

export function applyTheme(plotEl) {
  if (!plotEl) return;
  Plotly.relayout(plotEl, themeColors());
}
```

Each plot component subscribes to `store.theme` in its `connectedCallback()`. The handler calls `this._draw()` (a full re-render) rather than `applyTheme()` because trace-level colors (peak-overlay line, default colorway) are read at draw time from CSS variables and won't refresh from a `Plotly.relayout` alone. `applyTheme()` is exported anyway as the lighter-weight primitive — it correctly handles the layout-only refresh and is the right tool for any future component whose traces don't depend on theme variables. The header's existing `_toggleTheme()` already calls `store.set("theme", …)` — no change needed there.

`plotlyLayout()` continues to bake colors into the initial layout for the first `react()` call. The theme subscription handles every subsequent toggle.

## Testing

### New backend tests (`tests/test_routes_api.py` additions)

- `/api/range` with `freq_min_hz` and `freq_max_hz` returns rows with `n_points`, `center_freq`, `span` recomputed for the clipped window, and `len(powers)` matches the new `n_points`.
- `/api/range` with only `freq_min_hz` (no `freq_max_hz`) returns 422 (must specify both or neither).
- `/api/range` with `freq_min_hz > freq_max_hz` returns 400.
- `/api/range` response includes `actual_from`, `actual_to` keys.
- `/api/range` with `from` earlier than earliest data returns `actual_from = earliest_in_db.isoformat()`.
- `/api/range` against empty DB returns `rows: [], actual_from: null`.

### New DB tests (`tests/test_db.py` additions)

- `range_rows` with `freq_min_hz`/`freq_max_hz` clips powers and recomputes header fields correctly.
- `range_rows` with a freq window that doesn't intersect a row's sweep skips that row entirely (rather than returning it with `n_points = 0`). Decision rationale: the spectrogram heatmap renders cleaner without empty rows; missing rows show as gaps on the time axis, which is the correct visual signal that the operator retuned to a different center.
- `earliest_time()` returns the earliest `time_created` in the DB or `None` when empty.

### Frontend tests

The codebase has no frontend tests today (per `CLAUDE.md`: "no node_modules"). v2 keeps that property — no test framework added. Manual verification checklist in the implementation plan.

### Existing tests

- `test_watcher.py`, `test_db.py`, `test_routes_health.py`, `test_routes_auth.py`, `test_ws_manager.py` — should pass unchanged after v2 (no schema changes, no WS protocol changes).
- Any test that constructs a `Database.range_rows` call may need to add the optional new parameters as defaults.

## Migration

The v2 work happens on the `frontend-v2` branch. When ready:

1. All tests pass (`uv run pytest -v`).
2. Manual verification checklist completed (in plan doc).
3. Squash-merge to `master`.

The `spectrum_data_ovn.sqlite` file is unchanged. The tracker is unchanged. No data migration needed.

## Open questions resolved during brainstorming

- **3 dB SNR floor** chosen as the cutoff for "this row has a real peak" in auto-zoom math. Tunable via JS module constant; future enhancement could surface it in the UI.
- **`uirevision`** chosen over manual range save/restore for manual-zoom-lock — it's the canonical Plotly mechanism and avoids reinventing axis state tracking.
- **Drift / hr** stays as a sidebar tile (not removed with the rest of the stats panel) because it's the most actionable single-number summary of YIG behavior over a window.
- **Sidebar as a component** (`yig-sidebar`) rather than CSS-only, for clean data-subscription scoping.
- **WebSocket payload unchanged** — full powers per tick. Optimizing WS is deferred; the freq-clipping perf win is enough for v2.
