"""Public liveness endpoint."""
from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/healthz")
async def healthz(request: Request):
    state = request.app.state
    settings = state.settings
    db = state.db
    manager = state.manager
    watcher = state.watcher

    age = None
    try:
        age = db.latest_row_age_seconds()
    except Exception:
        age = None

    cadence = settings.cadence_sec
    stale = age is not None and age > 2 * cadence

    return {
        "ok": True,
        "db_path": str(settings.db_path),
        "last_row_age_seconds": age,
        "ws_clients": manager.count(),
        "watcher_running": bool(getattr(watcher, "running", False)),
        "stale": stale,
        "cadence_sec": cadence,
    }
