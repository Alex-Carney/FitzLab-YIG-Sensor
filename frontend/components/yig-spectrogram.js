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
    this._dirty = false;
    this._raf = null;
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
    if (this._raf) cancelAnimationFrame(this._raf);
  }

  async _reload() {
    const range = store.get("range");
    if (!range) return;
    try {
      const r = await getRange(range.from, range.to, MAX_ROWS);
      this._rows = r.rows || [];
      this._empty = this._rows.length === 0;
      this._scheduleDraw();
    } catch (e) {
      this._err = String(e);
    }
  }

  _onLiveTrace(data) {
    const range = store.get("range");
    if (!range || !range.live) return;
    this._rows.push(data);
    if (this._rows.length > MAX_ROWS) this._rows.shift();
    this._scheduleDraw();
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

    const data = [{
      type: "heatmap",
      x: xTimes,
      y: yFreqGHz,
      z: transpose(Z),
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

  updated() {
    if (!this._plotEl) {
      this._plotEl = this.querySelector("#sg-plot");
      if (this._plotEl && this._rows.length > 0) this._draw();
    }
  }
}

customElements.define("yig-spectrogram", YigSpectrogram);
