import { LitElement, html } from "lit";

export class YigApp extends LitElement {
  createRenderRoot() { return this; }

  render() {
    return html`
      <yig-header></yig-header>
      <yig-banner></yig-banner>
      <main class="dash-v2">
        <section class="panel sg">
          <yig-spectrogram></yig-spectrogram>
        </section>
        <section class="panel side">
          <yig-sidebar></yig-sidebar>
        </section>
        <section class="panel live">
          <yig-live-trace></yig-live-trace>
        </section>
        <section class="trends">
          <section class="panel">
            <yig-peak-track></yig-peak-track>
          </section>
          <section class="panel">
            <yig-snr-track></yig-snr-track>
          </section>
        </section>
      </main>
    `;
  }
}

customElements.define("yig-app", YigApp);
