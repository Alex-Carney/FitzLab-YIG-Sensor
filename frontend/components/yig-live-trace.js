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
      if (r.data) {
        this._lastTrace = r.data;
        // Seed latestRow so sidebar KPI tiles populate even when no live
        // WS ticks are flowing (e.g., tracker not running yet).
        store.set("latestRow", r.data);
        store.set("lastRowTs", new Date(r.data.t));
        this._draw();
      }
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
    Plotly.react(this._plotEl, data, layout, plotlyConfig).finally(() => {
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
