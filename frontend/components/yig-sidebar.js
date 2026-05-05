import { LitElement, html } from "lit";
import { store } from "/static/lib/store.js";
import { getStats } from "/static/lib/api.js";

function median(arr) {
  if (!arr.length) return 0;
  const s = [...arr].sort((a, b) => a - b);
  return s[Math.floor(s.length / 2)];
}

function peakFromTrace(trace) {
  let pi = 0;
  for (let i = 1; i < trace.powers.length; i++) {
    if (trace.powers[i] > trace.powers[pi]) pi = i;
  }
  const f0 = trace.center_freq - trace.span / 2;
  const peakFreq = f0 + (pi * trace.span) / (trace.n_points - 1);
  return {
    peakFreq,
    peakPower: trace.powers[pi],
    snr: trace.powers[pi] - median(trace.powers),
  };
}

function fmtFreqGHz(hz) {
  if (hz == null || !isFinite(hz)) return "—";
  return (hz / 1e9).toFixed(6);
}
function fmtDb(v) { return v == null || !isFinite(v) ? "—" : v.toFixed(1); }
function fmtDriftHz(v) {
  if (v == null || !isFinite(v)) return "—";
  if (Math.abs(v) >= 1e6) return (v / 1e6).toFixed(2);
  if (Math.abs(v) >= 1e3) return (v / 1e3).toFixed(1);
  return v.toFixed(0);
}
function driftUnit(v) {
  if (v == null || !isFinite(v)) return "Hz/h";
  if (Math.abs(v) >= 1e6) return "MHz/h";
  if (Math.abs(v) >= 1e3) return "kHz/h";
  return "Hz/h";
}

export class YigSidebar extends LitElement {
  createRenderRoot() { return this; }

  static properties = {
    _peakFreq:  { state: true },
    _peakPower: { state: true },
    _snr:       { state: true },
    _drift:     { state: true },
  };

  constructor() {
    super();
    this._peakFreq  = null;
    this._peakPower = null;
    this._snr       = null;
    this._drift     = null;
    this._driftTimer = null;
  }

  connectedCallback() {
    super.connectedCallback();
    this._unsubLatest = store.subscribe("latestRow", (row) => this._onLatest(row));
    this._unsubRange  = store.subscribe("range", () => this._refreshDrift());
    this._driftTimer  = setInterval(() => this._refreshDrift(), 30_000);
  }
  disconnectedCallback() {
    super.disconnectedCallback();
    this._unsubLatest?.();
    this._unsubRange?.();
    if (this._driftTimer) clearInterval(this._driftTimer);
  }

  _onLatest(row) {
    if (!row) return;
    const { peakFreq, peakPower, snr } = peakFromTrace(row);
    this._peakFreq  = peakFreq;
    this._peakPower = peakPower;
    this._snr       = snr;
  }

  async _refreshDrift() {
    const range = store.get("range");
    const win = range?.key || "5m";
    if (win === "custom") return;  // /api/stats expects 5m/30m/1h/etc.
    try {
      const r = await getStats(win);
      this._drift = r.drift_rate_hz_per_hr;
    } catch (e) {
      // leave previous value
    }
  }

  render() {
    return html`
      <div class="sidebar">
        <yig-kpi-tile label="Peak frequency"
                      .value=${fmtFreqGHz(this._peakFreq)} unit="GHz"></yig-kpi-tile>
        <yig-kpi-tile label="Peak power"
                      .value=${fmtDb(this._peakPower)} unit="dBm"></yig-kpi-tile>
        <yig-kpi-tile label="SNR"
                      .value=${fmtDb(this._snr)} unit="dB"></yig-kpi-tile>
        <yig-kpi-tile label="Drift / hr"
                      .value=${fmtDriftHz(this._drift)} unit=${driftUnit(this._drift)}></yig-kpi-tile>
      </div>
    `;
  }
}

customElements.define("yig-sidebar", YigSidebar);
