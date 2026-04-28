import { LitElement, html } from "lit";
import { getStats } from "/static/lib/api.js";

const POLL_MS = 30 * 1000;

function fmtFreqRate(hzPerHr) {
  const abs = Math.abs(hzPerHr);
  if (abs >= 1e6) return `${(hzPerHr / 1e6).toFixed(2)} MHz/hr`;
  if (abs >= 1e3) return `${(hzPerHr / 1e3).toFixed(2)} kHz/hr`;
  return `${hzPerHr.toFixed(2)} Hz/hr`;
}

function fmtDuration(seconds) {
  if (seconds < 60) return `${seconds.toFixed(0)} s`;
  if (seconds < 3600) return `${(seconds / 60).toFixed(1)} min`;
  if (seconds < 86400) return `${(seconds / 3600).toFixed(2)} hr`;
  return `${(seconds / 86400).toFixed(2)} d`;
}

export class YigStats extends LitElement {
  createRenderRoot() { return this; }
  static properties = {
    _data: { state: true },
    _err: { state: true },
  };

  constructor() {
    super();
    this._data = null;
    this._err = null;
    this._interval = null;
  }

  connectedCallback() {
    super.connectedCallback();
    this._refresh();
    this._interval = setInterval(() => this._refresh(), POLL_MS);
  }

  disconnectedCallback() {
    super.disconnectedCallback();
    if (this._interval) clearInterval(this._interval);
  }

  async _refresh() {
    try {
      this._data = await getStats("1h");
    } catch (e) {
      this._err = String(e);
    }
  }

  render() {
    if (this._err) return html`<div class="muted">${this._err}</div>`;
    if (!this._data) return html`<div class="muted">loading...</div>`;
    const d = this._data;
    return html`
      <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:var(--s-md);">
        <div>
          <div class="value-label">Drift rate (1h)</div>
          <div class="value-big">${fmtFreqRate(d.drift_rate_hz_per_hr)}</div>
        </div>
        <div>
          <div class="value-label">Since last retune</div>
          <div class="value-big">${fmtDuration(d.seconds_since_last_retune)}</div>
        </div>
        <div>
          <div class="value-label">Traces in window</div>
          <div class="value-big">${d.traces_in_window}</div>
        </div>
        <div>
          <div class="value-label">Current SNR</div>
          <div class="value-big">${d.current_snr_db.toFixed(1)} dB</div>
        </div>
      </div>
    `;
  }
}

customElements.define("yig-stats", YigStats);
