// Convert CSS custom properties into Plotly layout overrides.
// plotlyLayout(extra) is used for initial draws; themeColors() / applyTheme()
// keep existing figures in sync when the user toggles theme.

function _v(name, fallback = "") {
  return getComputedStyle(document.documentElement)
    .getPropertyValue(name)
    .trim() || fallback;
}

export function themeColors() {
  const text = _v("--c-text-1", "#a4adb7");
  const grid = _v("--c-border", "#232a31");
  const bg1  = _v("--c-bg-1",   "#12161a");
  return {
    paper_bgcolor: bg1,
    plot_bgcolor: bg1,
    "font.color": text,
    "xaxis.gridcolor": grid,
    "xaxis.zerolinecolor": grid,
    "xaxis.linecolor": grid,
    "xaxis.tickcolor": grid,
    "xaxis.color": text,
    "yaxis.gridcolor": grid,
    "yaxis.zerolinecolor": grid,
    "yaxis.linecolor": grid,
    "yaxis.tickcolor": grid,
    "yaxis.color": text,
  };
}

export function applyTheme(plotEl) {
  if (!plotEl || !window.Plotly) return;
  Plotly.relayout(plotEl, themeColors());
}

export function plotlyLayout(extra = {}) {
  const text = _v("--c-text-1", "#a4adb7");
  const grid = _v("--c-border", "#232a31");
  const bg1  = _v("--c-bg-1",   "#12161a");
  const accent = _v("--c-accent", "#4ea1ff");

  const base = {
    paper_bgcolor: bg1,
    plot_bgcolor: bg1,
    font: { family: "Inter, system-ui, sans-serif", color: text, size: 13 },
    margin: { l: 64, r: 28, t: 24, b: 48 },
    xaxis: {
      gridcolor: grid, zerolinecolor: grid, linecolor: grid,
      tickcolor: grid, color: text,
      title: { font: { size: 14 } },
      tickfont: { size: 13 },
    },
    yaxis: {
      gridcolor: grid, zerolinecolor: grid, linecolor: grid,
      tickcolor: grid, color: text,
      title: { font: { size: 14 } },
      tickfont: { size: 13 },
    },
    colorway: [accent],
    showlegend: false,
    uirevision: 0,  // bumped externally to drop user state
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
