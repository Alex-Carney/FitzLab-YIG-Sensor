import numpy as np
import duckdb
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.colors import Normalize

# ============================================================
# CONFIG
# ============================================================
DB_PATH    = "spectrum_data.duckdb"
TABLE_NAME = "spectra"

OUTPUT_PNG = "spectrogram.png"

# Optional time window filter (ISO format strings or None for no filter).
# Example: "2026-04-22 14:00:00"
TIME_START = None
TIME_END   = None

# Color scale. Set to None to auto-range from data.
VMIN_DBM = None    # e.g. -90
VMAX_DBM = None    # e.g. -30

# Frequency binning resolution for the common x-axis grid (Hz).
# None = auto (use the median spacing across traces).
FREQ_BIN_HZ = None
# ============================================================


def load_traces(db_path, table_name, t_start=None, t_end=None):
    conn = duckdb.connect(db_path, read_only=True)

    where = []
    params = []
    if t_start is not None:
        where.append("time_created >= ?")
        params.append(t_start)
    if t_end is not None:
        where.append("time_created <= ?")
        params.append(t_end)
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""

    query = f"""
        SELECT time_created, center_freq, span, rbw, frequencies, powers
        FROM {table_name}
        {where_sql}
        ORDER BY time_created ASC
    """
    rows = conn.execute(query, params).fetchall()
    conn.close()

    if not rows:
        raise RuntimeError(f"No rows found in {table_name}"
                           + (f" for given time window" if where else ""))

    times        = [r[0] for r in rows]
    center_freqs = np.array([r[1] for r in rows])
    spans        = np.array([r[2] for r in rows])
    rbws         = np.array([r[3] for r in rows])
    freq_lists   = [np.asarray(r[4]) for r in rows]
    power_lists  = [np.asarray(r[5]) for r in rows]

    return times, center_freqs, spans, rbws, freq_lists, power_lists


def build_grid(freq_lists, bin_hz=None):
    """Build a common frequency grid spanning the union of all trace ranges."""
    f_min = min(f[0]  for f in freq_lists)
    f_max = max(f[-1] for f in freq_lists)

    if bin_hz is None:
        # Use median spacing of the first trace as the grid resolution
        spacings = [np.median(np.diff(f)) for f in freq_lists]
        bin_hz = float(np.median(spacings))

    n_bins = int(np.ceil((f_max - f_min) / bin_hz)) + 1
    grid   = f_min + np.arange(n_bins) * bin_hz
    return grid, bin_hz


def grid_traces(times, freq_lists, power_lists, grid):
    """
    Place each trace onto the common frequency grid.
    Bins outside a trace's measured range stay NaN (so retune gaps show up).
    """
    n_time = len(times)
    n_freq = len(grid)
    Z = np.full((n_time, n_freq), np.nan, dtype=float)

    for i, (f, p) in enumerate(zip(freq_lists, power_lists)):
        # Left edge of this trace in grid-index space
        i_start = int(np.searchsorted(grid, f[0], side="left"))
        i_end   = i_start + len(f)
        if i_end > n_freq:
            i_end = n_freq
            f = f[: i_end - i_start]
            p = p[: i_end - i_start]
        # Interpolate trace onto the matching slice of the grid
        Z[i, i_start:i_end] = np.interp(
            grid[i_start:i_end], f, p,
            left=np.nan, right=np.nan,
        )
    return Z


def plot_spectrogram(times, grid, Z, output_png,
                     vmin=None, vmax=None):
    t_num = mdates.date2num(times)

    # Edges for pcolormesh (one more edge than cell in each dim).
    # Time edges: midpoints between samples, extrapolated at the ends.
    if len(t_num) > 1:
        t_mid   = (t_num[:-1] + t_num[1:]) / 2
        t_edges = np.concatenate([[t_num[0] - (t_mid[0] - t_num[0])],
                                  t_mid,
                                  [t_num[-1] + (t_num[-1] - t_mid[-1])]])
    else:
        # Single trace — give it a tiny width so pcolormesh doesn't choke
        t_edges = np.array([t_num[0] - 1e-5, t_num[0] + 1e-5])

    df = grid[1] - grid[0]
    f_edges = np.concatenate([grid - df / 2, [grid[-1] + df / 2]])

    # Auto color range from finite data if not specified
    finite = Z[np.isfinite(Z)]
    if vmin is None:
        vmin = np.percentile(finite, 1)
    if vmax is None:
        vmax = np.percentile(finite, 99)

    # Font sizes
    TITLE_FS = 22
    LABEL_FS = 22
    TICK_FS  = 20
    CBAR_FS  = 22

    fig, ax = plt.subplots(figsize=(14, 8))
    mesh = ax.pcolormesh(
        t_edges, f_edges / 1e9, Z.T,
        shading="flat",
        cmap="viridis",
        norm=Normalize(vmin=vmin, vmax=vmax),
    )
    # NaN cells (retune gaps / out-of-range bins) render as the axis background
    mesh.cmap.set_bad(color="white")

    ax.set_ylabel("Frequency (GHz)", fontsize=LABEL_FS)
    ax.set_xlabel("Time", fontsize=LABEL_FS)
    ax.set_title(f"Spectrogram ({len(times)} traces, "
                 f"{times[0].strftime('%Y-%m-%d %H:%M')} → "
                 f"{times[-1].strftime('%Y-%m-%d %H:%M')})",
                 fontsize=TITLE_FS)
    ax.tick_params(axis="both", which="major", labelsize=TICK_FS)
    ax.xaxis_date()
    fig.autofmt_xdate()

    cbar = fig.colorbar(mesh, ax=ax, pad=0.01)
    cbar.set_label("Power (dBm)", fontsize=CBAR_FS)
    cbar.ax.tick_params(labelsize=TICK_FS)

    fig.tight_layout()
    fig.savefig(output_png, dpi=400)
    plt.close(fig)
    print(f"Saved spectrogram to {output_png}")


def main():
    print(f"Loading from {DB_PATH} / {TABLE_NAME}")
    times, center_freqs, spans, rbws, freq_lists, power_lists = load_traces(
        DB_PATH, TABLE_NAME, TIME_START, TIME_END
    )
    print(f"Loaded {len(times)} traces from "
          f"{times[0]} to {times[-1]}")
    print(f"Center freq range: {center_freqs.min()/1e9:.6f} - "
          f"{center_freqs.max()/1e9:.6f} GHz "
          f"({len(np.unique(center_freqs))} unique centers)")

    grid, bin_hz = build_grid(freq_lists, FREQ_BIN_HZ)
    print(f"Built frequency grid: {grid[0]/1e9:.6f} - "
          f"{grid[-1]/1e9:.6f} GHz, {len(grid)} bins, "
          f"{bin_hz/1e3:.2f} kHz resolution")

    Z = grid_traces(times, freq_lists, power_lists, grid)
    filled = np.isfinite(Z).sum() / Z.size
    print(f"Grid fill: {filled*100:.1f}% "
          f"({(1-filled)*100:.1f}% NaN / gaps)")

    plot_spectrogram(times, grid, Z, OUTPUT_PNG,
                     vmin=VMIN_DBM, vmax=VMAX_DBM)


if __name__ == "__main__":
    main()