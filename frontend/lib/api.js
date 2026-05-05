// REST helpers. On 401, redirect to /login.

async function _fetch(path, opts = {}) {
  const r = await fetch(path, { credentials: "same-origin", ...opts });
  if (r.status === 401) {
    window.location.href = "/login";
    throw new Error("unauthorized");
  }
  return r;
}

export async function getJSON(path) {
  const r = await _fetch(path);
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
  return r.json();
}

function isoLocal(d) {
  // The DB stores naive local timestamps (datetime.datetime.now()). Send
  // local-clock ISO without TZ suffix so server-side comparisons match.
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}` +
         `T${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

export async function getSnapshot() {
  return getJSON("/api/snapshot");
}

export async function getRange(from, to, max_rows = 600, opts = {}) {
  const params = {
    from: isoLocal(from),
    to: isoLocal(to),
    max_rows: String(max_rows),
  };
  if (opts.freq_min_hz != null && opts.freq_max_hz != null) {
    params.freq_min_hz = String(opts.freq_min_hz);
    params.freq_max_hz = String(opts.freq_max_hz);
  }
  const qs = new URLSearchParams(params);
  return getJSON(`/api/range?${qs}`);
}

export async function getPeakTrack(from, to, max_rows = 2000) {
  const qs = new URLSearchParams({
    from: isoLocal(from),
    to: isoLocal(to),
    max_rows: String(max_rows),
  });
  return getJSON(`/api/peak-track?${qs}`);
}

export async function getStats(window = "1h") {
  const qs = new URLSearchParams({ window });
  return getJSON(`/api/stats?${qs}`);
}

export async function getHealth() {
  return getJSON("/healthz");
}
