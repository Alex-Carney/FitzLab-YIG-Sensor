import { LitElement, html } from "lit";
import { getPeakTrack } from "/static/lib/api.js";
import { ws } from "/static/lib/ws-client.js";
import { store } from "/static/lib/store.js";
import { plotlyLayout, plotlyConfig } from "/static/lib/plotly-theme.js";

const PLOT_HEIGHT = 220;
const MAX_PTS = 2000;

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
    if (!this._plotEl) return;
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

  updated() {
    if (!this._plotEl) {
      this._plotEl = this.querySelector("#pt-plot");
      if (this._plotEl && this._x.length > 0) this._draw();
    }
  }
}

customElements.define("yig-peak-track", YigPeakTrack);
