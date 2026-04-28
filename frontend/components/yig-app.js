import { LitElement, html } from "lit";

export class YigApp extends LitElement {
  createRenderRoot() { return this; }

  render() {
    return html`
      <yig-header></yig-header>
      <main class="dash-grid">
        <section class="panel panel--wide">
          <h2>Live trace</h2>
          <yig-live-trace></yig-live-trace>
        </section>
        <section class="panel panel--wide">
          <h2>Spectrogram</h2>
          <yig-spectrogram></yig-spectrogram>
        </section>
        <section class="panel">
          <h2>Peak frequency</h2>
          <yig-peak-track></yig-peak-track>
        </section>
        <section class="panel">
          <h2>Peak power & SNR</h2>
          <yig-peak-power></yig-peak-power>
        </section>
        <section class="panel panel--wide">
          <h2>Stats</h2>
          <yig-stats></yig-stats>
        </section>
        <section class="panel panel--wide">
          <h2>History (7 days)</h2>
          <yig-history-browser></yig-history-browser>
        </section>
      </main>
    `;
  }
}

customElements.define("yig-app", YigApp);
