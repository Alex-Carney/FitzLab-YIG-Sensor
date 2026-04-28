// Singleton WS client with exponential-backoff reconnect.
// Dispatches typed events: 'trace', 'ping'.

import { store } from "/static/lib/store.js";

class WSClient {
  constructor(path = "/ws") {
    this.path = path;
    this.ws = null;
    this.subs = new Map();
    this.backoff = 1000;
    this._stopped = false;
    this._connect();
  }

  _connect() {
    if (this._stopped) return;
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    const url = `${proto}//${location.host}${this.path}`;
    try {
      this.ws = new WebSocket(url);
    } catch (e) {
      this._scheduleReconnect();
      return;
    }
    this.ws.addEventListener("open", () => {
      this.backoff = 1000;
      store.set("wsConnected", true);
    });
    this.ws.addEventListener("close", (e) => {
      store.set("wsConnected", false);
      if (e.code === 1008) {
        window.location.href = "/login";
        return;
      }
      this._scheduleReconnect();
    });
    this.ws.addEventListener("error", () => {
      // close will follow
    });
    this.ws.addEventListener("message", (ev) => {
      let msg;
      try { msg = JSON.parse(ev.data); } catch { return; }
      const subs = this.subs.get(msg.type);
      if (subs) subs.forEach((cb) => {
        try { cb(msg.data); } catch (e) { console.error(e); }
      });
      if (msg.type === "trace" && msg.data) {
        store.set("latestRow", msg.data);
        store.set("lastRowTs", new Date(msg.data.t));
      }
    });
  }

  _scheduleReconnect() {
    setTimeout(() => this._connect(), this.backoff);
    this.backoff = Math.min(this.backoff * 2, 30000);
  }

  subscribe(type, cb) {
    if (!this.subs.has(type)) this.subs.set(type, new Set());
    this.subs.get(type).add(cb);
    return () => this.subs.get(type)?.delete(cb);
  }

  stop() {
    this._stopped = true;
    if (this.ws) this.ws.close();
  }
}

export const ws = new WSClient("/ws");
window.__yigWS = ws;
