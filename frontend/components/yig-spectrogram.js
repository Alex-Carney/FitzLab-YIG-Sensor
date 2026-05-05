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
