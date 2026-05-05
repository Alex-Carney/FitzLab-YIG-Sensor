import { LitElement, html } from "lit";
import { store } from "/static/lib/store.js";

export class YigBanner extends LitElement {
  createRenderRoot() { return this; }

  static properties = {
    _banner: { state: true },
  };

  constructor() {
    super();
    this._banner = null;
  }

  connectedCallback() {
    super.connectedCallback();
    this._unsub = store.subscribe("banner", (b) => { this._banner = b; });
  }
  disconnectedCallback() {
    super.disconnectedCallback();
    this._unsub?.();
  }

  render() {
    if (!this._banner) return null;
    const { type = "info", message } = this._banner;
    return html`
      <div class="banner banner--${type}">
        <span class="banner__icon">${type === "warn" ? "!" : "i"}</span>
        <span class="banner__msg">${message}</span>
      </div>
    `;
  }
}

customElements.define("yig-banner", YigBanner);
