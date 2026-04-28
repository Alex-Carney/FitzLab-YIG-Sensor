import { LitElement, html } from "lit";
import { getSnapshot } from "/static/lib/api.js";
import { ws } from "/static/lib/ws-client.js";
import { plotlyLayout, plotlyConfig } from "/static/lib/plotly-theme.js";

const PLOT_HEIGHT = 280;

export class YigLiveTrace extends LitElement {
  createRenderRoot() { return this; }

  static properties = { _err: { state: true } };

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
    if (this._plotEl) {
      Plotly.react(this._plotEl, data, layout, plotlyConfig);
    }
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

  updated() {
    if (!this._plotEl) {
      this._plotEl = this.querySelector("#live-plot");
      if (this._plotEl && this._lastTrace) this._draw(this._lastTrace);
    }
  }
}

customElements.define("yig-live-trace", YigLiveTrace);
