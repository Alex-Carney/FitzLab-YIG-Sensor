import { LitElement, html } from "lit";
import { getPeakTrack } from "/static/lib/api.js";
import { ws } from "/static/lib/ws-client.js";
import { store } from "/static/lib/store.js";
import { plotlyLayout, plotlyConfig } from "/static/lib/plotly-theme.js";

const MAX_PTS = 2000;

function median(arr) {
  if (!arr.length) return 0;
  const s = [...arr].sort((a, b) => a - b);
  return s[Math.floor(s.length / 2)];
}

function snrOf(trace) {
  let pmax = trace.powers[0];
  for (let i = 1; i < trace.powers.length; i++) {
    if (trace.powers[i] > pmax) pmax = trace.powers[i];
  }
  return pmax - median(trace.powers);
}

export class YigSnrTrack extends LitElement {
  createRenderRoot() { return this; }
  static properties = { _err: { state: true } };

  constructor() {
    super();
    this._x = []; this._y = [];
    this._plotEl = null;
    this._mode = "auto";
    this._uirev = 0;
    this._err = null;
    this._suppressRelayout = false;
    this._relayoutBound = false;
    this._gen = 0;
  }

  connectedCallback() {
    super.connectedCallback();
    this._unsubRange = store.subscribe("range", () => this._onRangeChange());
    this._unsubTrace = ws.subscribe("trace", (data) => this._onLive(data));
    this._unsubTheme = store.subscribe("theme", () => this._draw());
  }
  disconnectedCallback() {
    super.disconnectedCallback();
    this._unsubRange?.();
    this._unsubTrace?.();
    this._unsubTheme?.();
  }

  async _onRangeChange() {
    this._mode = "auto";
    this._uirev += 1;
    await this._reload();
  }

  async _reload() {
    const r = store.get("range");
    if (!r) return;
    const gen = ++this._gen;
    try {
      const resp = await getPeakTrack(r.from, r.to, MAX_PTS);
      if (gen !== this._gen) return;
      this._x = resp.rows.map((p) => new Date(p.t));
      this._y = resp.rows.map((p) => p.snr);
      this._draw();
    } catch (e) {
      if (gen !== this._gen) return;
      this._err = String(e);
    }
  }

  _onLive(data) {
    const r = store.get("range");
    if (!r || !r.live) return;
    this._x.push(new Date(data.t));
    this._y.push(snrOf(data));
    while (this._x.length > MAX_PTS) { this._x.shift(); this._y.shift(); }
    this._draw();
  }

  _draw() {
    if (!this._plotEl) this._plotEl = this.querySelector("#snr-plot");
    if (!this._plotEl) return;
    const data = [{
      x: this._x, y: this._y, mode: "lines",
      line: { width: 1.5 },
      hovertemplate: "%{x}<br>%{y:.2f} dB<extra></extra>",
    }];
    const layout = plotlyLayout({
      xaxis: { type: "date" },
      yaxis: { title: { text: "SNR (dB)" } },
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
    if (userZoomed && this._mode === "auto") this._mode = "locked";
  }

  render() {
    return html`
      ${this._err ? html`<div class="muted">${this._err}</div>` : null}
      <div id="snr-plot" style="width:100%;height:100%"></div>
    `;
  }

  updated() {
    if (!this._plotEl) {
      this._plotEl = this.querySelector("#snr-plot");
      if (this._plotEl && this._x.length > 0) this._draw();
    }
  }
}

customElements.define("yig-snr-track", YigSnrTrack);
