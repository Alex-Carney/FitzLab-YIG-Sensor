// Minimal reactive store. Keys are arbitrary strings; subscribers receive new values.

class Store {
  constructor(initial = {}) {
    this._state = { ...initial };
    this._subs = new Map();
  }

  get(key) {
    return this._state[key];
  }

  set(key, value) {
    this._state[key] = value;
    const subs = this._subs.get(key);
    if (subs) subs.forEach((cb) => {
      try { cb(value); } catch (e) { console.error(e); }
    });
  }

  subscribe(key, cb) {
    if (!this._subs.has(key)) this._subs.set(key, new Set());
    this._subs.get(key).add(cb);
    if (key in this._state) cb(this._state[key]);
    return () => this._subs.get(key)?.delete(cb);
  }
}

const DEFAULT_RANGE_MS = 5 * 60 * 1000;
const now = Date.now();

export const store = new Store({
  range: { from: new Date(now - DEFAULT_RANGE_MS), to: new Date(now), live: true, key: "5m" },
  latestRow: null,
  theme: localStorage.getItem("yig-theme") || "dark",
  wsConnected: false,
  lastRowTs: null,
});

window.__yigStore = store;
