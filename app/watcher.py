"""Background polling watcher.

Lives as a long-running asyncio task started in FastAPI's `lifespan`. Polls
`db.rows_after(last_seen)` at `cadence_sec`, broadcasts new rows to all
connected WebSocket clients, and never tears down on a single error.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import logging
from typing import Optional

from app.db import Database
from app.ws_manager import ConnectionManager

logger = logging.getLogger("yig.watcher")


def _row_to_payload(row: dict) -> dict:
    """Convert a DB row (with datetime) into a JSON-serialisable trace payload."""
    return {
        "type": "trace",
        "data": {
            "t": row["time_created"].isoformat(),
            "center_freq": float(row["center_freq"]),
            "span": float(row["span"]),
            "rbw": float(row["rbw"]),
            "n_points": int(row["n_points"]),
            "powers": [float(x) for x in row["powers"]],
        },
    }


class PollingWatcher:
    def __init__(
        self,
        db: Database,
        manager: ConnectionManager,
        cadence_sec: float,
        batch_size: int = 200,
    ):
        self.db = db
        self.manager = manager
        self.cadence_sec = max(0.01, float(cadence_sec))
        self.batch_size = batch_size
        self._stop = asyncio.Event()
        self._last_seen: Optional[dt.datetime] = None
        self.running = False

    def stop(self) -> None:
        self._stop.set()

    async def run(self) -> None:
        self.running = True
        try:
            latest = self.db.latest_row()
            if latest is not None:
                self._last_seen = latest["time_created"]
        except Exception as e:
            logger.warning("watcher init failed (%s); starting from epoch", e)
            self._last_seen = dt.datetime(1970, 1, 1)

        if self._last_seen is None:
            self._last_seen = dt.datetime(1970, 1, 1)

        try:
            while not self._stop.is_set():
                try:
                    rows = self.db.rows_after(self._last_seen, limit=self.batch_size)
                except Exception as e:
                    logger.warning("watcher poll failed (%s); will retry", e)
                    rows = []

                for row in rows:
                    self._last_seen = row["time_created"]
                    try:
                        await self.manager.broadcast(_row_to_payload(row))
                    except Exception as e:
                        logger.warning("broadcast failed (%s)", e)

                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=self.cadence_sec)
                except asyncio.TimeoutError:
                    pass
        finally:
            self.running = False
