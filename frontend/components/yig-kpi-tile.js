import { LitElement, html } from "lit";

export class YigKpiTile extends LitElement {
  createRenderRoot() { return this; }

  static properties = {
    label: { type: String },
    value: { type: String },
    unit:  { type: String },
    state: { type: String }, // "ok" | "warn" | "bad" | ""
  };

  constructor() {
    super();
    this.label = "";
    this.value = "—";
    this.unit  = "";
    this.state = "";
  }

  render() {
    return html`
      <div class="kpi-tile" data-state=${this.state}>
        <div class="kpi-tile__label">${this.label}</div>
        <div class="kpi-tile__row">
          <span class="kpi-tile__value">${this.value}</span>
          ${this.unit ? html`<span class="kpi-tile__unit">${this.unit}</span>` : null}
        </div>
      </div>
    `;
  }
}

customElements.define("yig-kpi-tile", YigKpiTile);
