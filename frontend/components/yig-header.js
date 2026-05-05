import { LitElement, html } from "lit";
import { store } from "/static/lib/store.js";

const RANGES = [
  { id: "5m",  ms: 5 * 60 * 1000 },
  { id: "30m", ms: 30 * 60 * 1000 },
  { id: "1h",  ms: 60 * 60 * 1000 },
  { id: "6h",  ms: 6 * 60 * 60 * 1000 },
  { id: "24h", ms: 24 * 60 * 60 * 1000 },
  { id: "7d",  ms: 7 * 24 * 60 * 60 * 1000 },
];

const COLORSCALES = ["Inferno", "Jet", "Viridis"];

export class YigHeader extends LitElement {
  createRenderRoot() { return this; }

  static properties = {
    activeRange: { state: true },
    ledClass: { state: true },
    ledLabel: { state: true },
    theme: { state: true },
    colorscale: { state: true },
  };

  constructor() {
    super();
    this.activeRange = "5m";
    this.theme = store.get("theme") || "dark";
    this.colorscale = store.get("colorscale") || "Inferno";
    this.ledClass = "led__dot--bad";
    this.ledLabel = "offline";
    this._setRange("5m");
    document.documentElement.dataset.theme = this.theme;

    this._ledInterval = setInterval(() => this._refreshLed(), 1000);
    this._unsubWs = store.subscribe("wsConnected", () => this._refreshLed());
    this._unsubLastRow = store.subscribe("lastRowTs", () => this._refreshLed());
  }

  disconnectedCallback() {
    super.disconnectedCallback();
    if (this._ledInterval) clearInterval(this._ledInterval);
    this._unsubWs?.();
    this._unsubLastRow?.();
  }

  _refreshLed() {
    const wsOk = !!store.get("wsConnected");
    const lastTs = store.get("lastRowTs");
    if (!wsOk) {
      this.ledClass = "led__dot--bad";
      this.ledLabel = "disconnected";
      return;
    }
    if (!lastTs) {
      this.ledClass = "led__dot--warn";
      this.ledLabel = "no data yet";
      return;
    }
    const ageSec = (Date.now() - lastTs.getTime()) / 1000;
    if (ageSec < 5) {
      this.ledClass = "led__dot--ok";
      this.ledLabel = "live";
    } else if (ageSec < 30) {
      this.ledClass = "led__dot--warn";
      this.ledLabel = `stale (${ageSec.toFixed(0)}s)`;
    } else {
      this.ledClass = "led__dot--bad";
      this.ledLabel = `stale (${ageSec.toFixed(0)}s)`;
    }
  }

  _setRange(id) {
    this.activeRange = id;
    const cfg = RANGES.find((r) => r.id === id);
    const to = new Date();
    const from = new Date(to.getTime() - cfg.ms);
    store.set("range", { from, to, live: true, key: id });
  }

  _toggleTheme() {
    this.theme = this.theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = this.theme;
    localStorage.setItem("yig-theme", this.theme);
    store.set("theme", this.theme);
  }

  _setColorscale(name) {
    this.colorscale = name;
    localStorage.setItem("yig-colorscale", name);
    store.set("colorscale", name);
  }

  async _logout() {
    await fetch("/logout", { method: "POST", credentials: "same-origin" });
    window.location.href = "/login";
  }

  render() {
    return html`
      <header class="hdr">
        <div class="hdr__title">YIG Dashboard</div>
        <div class="hdr__right">
          <div class="range-controls">
            ${RANGES.map((r) => html`
              <button class="range-btn"
                data-active=${this.activeRange === r.id ? "1" : "0"}
                @click=${() => this._setRange(r.id)}>${r.id}</button>
            `)}
          </div>
          <div class="range-controls" title="Spectrogram colorscale">
            ${COLORSCALES.map((c) => html`
              <button class="range-btn"
                data-active=${this.colorscale === c ? "1" : "0"}
                @click=${() => this._setColorscale(c)}>${c}</button>
            `)}
          </div>
          <span class="led">
            <span class="led__dot ${this.ledClass}"></span>${this.ledLabel}
          </span>
          <button @click=${this._toggleTheme} title="Toggle theme">
            ${this.theme === "dark" ? "Sun" : "Moon"}
          </button>
          <button @click=${this._logout}>Logout</button>
        </div>
      </header>
    `;
  }
}

customElements.define("yig-header", YigHeader);
