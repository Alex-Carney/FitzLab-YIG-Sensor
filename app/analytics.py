"""Pure helpers for derived metrics."""
from __future__ import annotations

import datetime as dt


def compute_drift_rate_hz_per_hr(
    times: list[dt.datetime],
    peak_freqs_hz: list[float],
) -> float:
    """Linear least-squares fit of peak frequency vs time, returned as Hz/hr.

    Returns 0.0 if fewer than two points or if all timestamps coincide.
    """
    n = len(times)
    if n < 2 or n != len(peak_freqs_hz):
        return 0.0

    t0 = times[0]
    xs = [(t - t0).total_seconds() for t in times]
    ys = peak_freqs_hz

    if max(xs) == 0:
        return 0.0

    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((xs[i] - mx) * (ys[i] - my) for i in range(n))
    den = sum((xs[i] - mx) ** 2 for i in range(n))
    if den == 0:
        return 0.0
    slope_hz_per_sec = num / den
    return slope_hz_per_sec * 3600.0


def seconds_since_last_retune(
    times: list[dt.datetime],
    centers: list[float],
    now: dt.datetime,
    eps_hz: float = 1.0,
) -> float:
    """Seconds between the last center_freq change and `now`.

    If no retune is observed in the window, returns the time between
    the earliest sample and `now` (i.e., 'at least this long').
    """
    if not times or len(times) != len(centers):
        return 0.0
    last_change = times[0]
    for i in range(1, len(times)):
        if abs(centers[i] - centers[i - 1]) > eps_hz:
            last_change = times[i]
    return (now - last_change).total_seconds()
