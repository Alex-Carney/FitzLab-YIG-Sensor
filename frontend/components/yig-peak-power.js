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
    if (!this._plotEl) return;
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

  updated() {
    if (!this._plotEl) {
      this._plotEl = this.querySelector("#pp-plot");
      if (this._plotEl && this._x.length > 0) this._draw();
    }
  }
}

customElements.define("yig-peak-power", YigPeakPower);
