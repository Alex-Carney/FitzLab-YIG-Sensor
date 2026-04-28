import { LitElement, html } from "lit";
import { store } from "/static/lib/store.js";

const DAYS = 7;
const MS_PER_DAY = 24 * 60 * 60 * 1000;

function fmt(d) {
  return d.toLocaleString([], {
    year: "numeric", month: "short", day: "numeric",
    hour: "2-digit", minute: "2-digit",
  });
}

export class YigHistoryBrowser extends LitElement {
  createRenderRoot() { return this; }

  static properties = {
    _from: { state: true },
    _to: { state: true },
    _now: { state: true },
  };

  constructor() {
    super();
    this._now = new Date();
    this._from = new Date(this._now.getTime() - 5 * 60 * 1000);
    this._to = new Date(this._now.getTime());
    this._tickInterval = null;
  }

  connectedCallback() {
    super.connectedCallback();
    this._tickInterval = setInterval(() => {
      this._now = new Date();
      this.requestUpdate();
    }, 60_000);
  }
  disconnectedCallback() {
    super.disconnectedCallback();
    if (this._tickInterval) clearInterval(this._tickInterval);
  }

  _earliest() {
    return new Date(this._now.getTime() - DAYS * MS_PER_DAY);
  }

  _onFrom(e) {
    const ms = Number(e.target.value);
    this._from = new Date(this._earliest().getTime() + ms);
    if (this._from >= this._to) {
      this._from = new Date(this._to.getTime() - 60_000);
    }
    this._commit();
  }

  _onTo(e) {
    const ms = Number(e.target.value);
    this._to = new Date(this._earliest().getTime() + ms);
    if (this._to <= this._from) {
      this._to = new Date(this._from.getTime() + 60_000);
    }
    this._commit();
  }

  _liveTail() {
    this._to = new Date();
    if (this._to <= this._from) {
      this._from = new Date(this._to.getTime() - 5 * 60_000);
    }
    this._commit({ live: true });
  }

  _commit(extra = {}) {
    const live = extra.live === true;
    store.set("range", { from: this._from, to: this._to, live, key: "custom" });
  }

  render() {
    const earliestMs = this._earliest().getTime();
    const totalMs = this._now.getTime() - earliestMs;
    const fromVal = this._from.getTime() - earliestMs;
    const toVal = this._to.getTime() - earliestMs;
    return html`
      <div style="display:grid;grid-template-columns:auto 1fr;gap:var(--s-md);align-items:center;">
        <div class="value-label">From</div>
        <input type="range" min="0" max=${totalMs} step="1000" .value=${fromVal}
               @input=${this._onFrom} style="width:100%">
        <div class="value-label">To</div>
        <input type="range" min="0" max=${totalMs} step="1000" .value=${toVal}
               @input=${this._onTo} style="width:100%">
      </div>
      <div style="display:flex;justify-content:space-between;margin-top:var(--s-sm);">
        <div class="muted">${fmt(this._from)} → ${fmt(this._to)}</div>
        <button class="range-btn" @click=${this._liveTail}>Live tail</button>
      </div>
    `;
  }
}

customElements.define("yig-history-browser", YigHistoryBrowser);
