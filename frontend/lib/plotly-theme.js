// Convert CSS custom properties into Plotly layout overrides.
// Components call plotlyLayout(extra) before rendering.

function _v(name, fallback = "") {
  return getComputedStyle(document.documentElement)
    .getPropertyValue(name)
    .trim() || fallback;
}

export function plotlyLayout(extra = {}) {
  const text = _v("--c-text-1", "#a4adb7");
  const grid = _v("--c-border", "#232a31");
  const bg0  = _v("--c-bg-1",   "#12161a");
  const accent = _v("--c-accent", "#4ea1ff");

  const base = {
    paper_bgcolor: bg0,
    plot_bgcolor: bg0,
    font: { family: "Inter, system-ui, sans-serif", color: text, size: 12 },
    margin: { l: 56, r: 28, t: 24, b: 40 },
    xaxis: {
      gridcolor: grid,
      zerolinecolor: grid,
      linecolor: grid,
      tickcolor: grid,
      color: text,
    },
    yaxis: {
      gridcolor: grid,
      zerolinecolor: grid,
      linecolor: grid,
      tickcolor: grid,
      color: text,
    },
    colorway: [accent],
    showlegend: false,
  };

  return _deepMerge(base, extra);
}

export const plotlyConfig = {
  displaylogo: false,
  responsive: true,
  modeBarButtonsToRemove: ["lasso2d", "select2d"],
};

function _deepMerge(a, b) {
  const out = { ...a };
  for (const k of Object.keys(b || {})) {
    if (b[k] && typeof b[k] === "object" && !Array.isArray(b[k]) && a[k] && typeof a[k] === "object") {
      out[k] = _deepMerge(a[k], b[k]);
    } else {
      out[k] = b[k];
    }
  }
  return out;
}
