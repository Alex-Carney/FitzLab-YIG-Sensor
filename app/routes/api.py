"""Authenticated REST endpoints for the dashboard frontend."""
from __future__ import annotations

import datetime as dt
import math
import re

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.analytics import (
    compute_drift_rate_hz_per_hr,
    seconds_since_last_retune,
)
from app.auth import require_session_factory

router = APIRouter(prefix="/api")

_WINDOW_RE = re.compile(r"^(\d+)([smhd])$")


def _parse_window(s: str) -> dt.timedelta:
    m = _WINDOW_RE.match(s)
    if not m:
        raise HTTPException(status_code=400, detail="bad window; expected e.g. 1h, 30m, 7d")
    n, unit = int(m.group(1)), m.group(2)
    return {
        "s": dt.timedelta(seconds=n),
        "m": dt.timedelta(minutes=n),
        "h": dt.timedelta(hours=n),
        "d": dt.timedelta(days=n),
    }[unit]


def _row_to_trace(row: dict) -> dict:
    return {
        "t": row["time_created"].isoformat(),
        "center_freq": float(row["center_freq"]),
        "span": float(row["span"]),
        "rbw": float(row["rbw"]),
        "n_points": int(row["n_points"]),
        "powers": [float(x) for x in row["powers"]],
    }


def _peak_to_dict(p: dict) -> dict:
    return {
        "t": p["time_created"].isoformat(),
        "center_freq": float(p["center_freq"]),
        "peak_freq": float(p["peak_freq"]),
        "peak_power": float(p["peak_power"]),
        "snr": float(p["snr"]),
    }


def _require_session(request: Request):
    settings = request.app.state.settings
    return require_session_factory(settings.secret, settings.cookie_name)(request)


@router.get("/snapshot")
async def snapshot(request: Request, session=Depends(_require_session)):
    db = request.app.state.db
    row = db.latest_row()
    if row is None:
        return {"data": None}
    return {"data": _row_to_trace(row)}


@router.get("/range")
async def range_endpoint(
    request: Request,
    t_from: dt.datetime = Query(..., alias="from"),
    t_to: dt.datetime = Query(..., alias="to"),
    max_rows: int = Query(600, ge=1),
    freq_min_hz: float | None = Query(None),
    freq_max_hz: float | None = Query(None),
    session=Depends(_require_session),
):
    settings = request.app.state.settings
    if t_to <= t_from:
        raise HTTPException(status_code=400, detail="to must be > from")
    if (t_to - t_from) > dt.timedelta(days=settings.range_max_days):
        raise HTTPException(
            status_code=400,
            detail=f"window exceeds max {settings.range_max_days} days",
        )
    if (freq_min_hz is None) != (freq_max_hz is None):
        raise HTTPException(
            status_code=400,
            detail="freq_min_hz and freq_max_hz must be specified together",
        )
    for v, name in ((freq_min_hz, "freq_min_hz"), (freq_max_hz, "freq_max_hz")):
        if v is not None and not math.isfinite(v):
            raise HTTPException(status_code=400, detail=f"{name} must be finite")
    if freq_min_hz is not None and freq_max_hz is not None and freq_min_hz >= freq_max_hz:
        raise HTTPException(status_code=400, detail="freq_min_hz must be < freq_max_hz")
    if max_rows > settings.api_max_rows_hard_cap:
        max_rows = settings.api_max_rows_hard_cap

    db = request.app.state.db
    rows = db.range_rows(
        t_from, t_to, max_rows=max_rows,
        freq_min_hz=freq_min_hz, freq_max_hz=freq_max_hz,
    )
    earliest = db.earliest_time()
    if earliest is None:
        actual_from_iso = None
    else:
        actual_from_iso = max(t_from, earliest).isoformat()

    return {
        "rows": [_row_to_trace(r) for r in rows],
        "requested_from": t_from.isoformat(),
        "actual_from": actual_from_iso,
        "requested_to": t_to.isoformat(),
        "actual_to": t_to.isoformat(),
    }


@router.get("/peak-track")
async def peak_track(
    request: Request,
    t_from: dt.datetime = Query(..., alias="from"),
    t_to: dt.datetime = Query(..., alias="to"),
    max_rows: int = Query(2000, ge=1),
    session=Depends(_require_session),
):
    settings = request.app.state.settings
    if t_to <= t_from:
        raise HTTPException(status_code=400, detail="to must be > from")
    if (t_to - t_from) > dt.timedelta(days=settings.range_max_days):
        raise HTTPException(status_code=400, detail="window too wide")
    if max_rows > settings.api_max_rows_hard_cap:
        max_rows = settings.api_max_rows_hard_cap
    db = request.app.state.db
    pts = db.peak_track_range(t_from, t_to, max_rows=max_rows)
    return {"rows": [_peak_to_dict(p) for p in pts]}


@router.get("/stats")
async def stats(
    request: Request,
    window: str = Query("1h"),
    session=Depends(_require_session),
):
    db = request.app.state.db
    delta = _parse_window(window)
    latest = db.latest_row()
    if latest is None:
        return {
            "drift_rate_hz_per_hr": 0.0,
            "seconds_since_last_retune": 0.0,
            "traces_in_window": 0,
            "current_snr_db": 0.0,
            "window": window,
        }
    now_t = latest["time_created"]
    t_from = now_t - delta

    pts = db.peak_track_range(t_from, now_t, max_rows=2000)
    times = [p["time_created"] for p in pts]
    peaks = [p["peak_freq"] for p in pts]
    centers = [p["center_freq"] for p in pts]

    drift = compute_drift_rate_hz_per_hr(times, peaks)
    s_retune = seconds_since_last_retune(times, centers, now=now_t) if times else 0.0
    current_snr = pts[-1]["snr"] if pts else 0.0

    return {
        "drift_rate_hz_per_hr": drift,
        "seconds_since_last_retune": s_retune,
        "traces_in_window": len(pts),
        "current_snr_db": current_snr,
        "window": window,
    }
