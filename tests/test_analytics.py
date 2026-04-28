import datetime as dt

from app.analytics import (
    compute_drift_rate_hz_per_hr,
    seconds_since_last_retune,
)


def test_drift_rate_zero_for_constant():
    times = [dt.datetime(2026, 4, 27, 12, 0, i) for i in range(10)]
    peaks = [6.46e9 for _ in range(10)]
    rate = compute_drift_rate_hz_per_hr(times, peaks)
    assert abs(rate) < 1e-3


def test_drift_rate_positive_for_upward_drift():
    times = [dt.datetime(2026, 4, 27, 12, 0, i) for i in range(10)]
    peaks = [6.46e9 + 1e3 * i for i in range(10)]
    rate = compute_drift_rate_hz_per_hr(times, peaks)
    assert 3.5e6 < rate < 3.7e6


def test_drift_rate_handles_short_series():
    assert compute_drift_rate_hz_per_hr([], []) == 0.0
    one = [dt.datetime(2026, 4, 27, 12, 0, 0)]
    assert compute_drift_rate_hz_per_hr(one, [6.46e9]) == 0.0


def test_seconds_since_last_retune_no_retune():
    times = [dt.datetime(2026, 4, 27, 12, 0, i) for i in range(10)]
    centers = [6.46e9] * 10
    now = dt.datetime(2026, 4, 27, 12, 0, 9)
    s = seconds_since_last_retune(times, centers, now=now)
    assert s == 9.0


def test_seconds_since_last_retune_finds_jump():
    times = [dt.datetime(2026, 4, 27, 12, 0, i) for i in range(10)]
    centers = [6.46e9] * 5 + [6.47e9] * 5
    now = dt.datetime(2026, 4, 27, 12, 0, 9)
    s = seconds_since_last_retune(times, centers, now=now)
    # Retune at i=5 (12:00:05). now=12:00:09 -> 4s
    assert s == 4.0
