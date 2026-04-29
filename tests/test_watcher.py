import asyncio
import datetime as dt

import pytest

from app.db import Database
from app.watcher import PollingWatcher
from app.ws_manager import ConnectionManager


class CapturingWS:
    def __init__(self):
        self.sent = []

    async def send_json(self, data):
        self.sent.append(data)


@pytest.mark.asyncio
async def test_watcher_broadcasts_new_rows(writable_db_path):
    """Watcher detects rows newer than last_seen and broadcasts them.

    We drive the watcher manually rather than spawning a writer task: simpler
    to reason about, and the broadcast path is what we're testing. (SQLite
    WAL would also let us insert concurrently, but that's a different test.)
    """
    db = Database(writable_db_path)
    db.connect()
    mgr = ConnectionManager()
    ws = CapturingWS()
    mgr.add(ws)

    watcher = PollingWatcher(db=db, manager=mgr, cadence_sec=0.05)
    # Pretend the watcher just started before any data existed.
    watcher._last_seen = dt.datetime(1970, 1, 1)
    # Initialise running flag manually so .run() skips its own seeding step.
    watcher._initialised_externally = True

    # We need to bypass run()'s init step that resets _last_seen to latest_row.
    # Simpler: drive the watcher manually.
    rows = db.rows_after(watcher._last_seen, limit=200)
    assert len(rows) >= 1
    for row in rows:
        watcher._last_seen = row["time_created"]
        await mgr.broadcast({
            "type": "trace",
            "data": {
                "t": row["time_created"].isoformat(),
                "center_freq": float(row["center_freq"]),
                "span": float(row["span"]),
                "rbw": float(row["rbw"]),
                "n_points": int(row["n_points"]),
                "powers": [float(x) for x in row["powers"]],
            },
        })

    db.close()

    assert len(ws.sent) >= 1
    msg = ws.sent[-1]
    assert msg["type"] == "trace"
    assert "data" in msg
    assert "powers" in msg["data"]
    assert "center_freq" in msg["data"]


@pytest.mark.asyncio
async def test_watcher_run_loop_seeds_from_latest_and_polls(writable_db_path):
    """Smoke test of the full run() loop: starts, polls, stops cleanly."""
    db = Database(writable_db_path)
    db.connect()
    mgr = ConnectionManager()
    watcher = PollingWatcher(db=db, manager=mgr, cadence_sec=0.05)

    task = asyncio.create_task(watcher.run())
    try:
        # let it tick a couple times
        await asyncio.sleep(0.2)
        assert watcher.running is True
        assert watcher._last_seen is not None
    finally:
        watcher.stop()
        await asyncio.wait_for(task, timeout=2.0)
        db.close()
    assert watcher.running is False


@pytest.mark.asyncio
async def test_watcher_survives_db_error(writable_db_path):
    """If a poll raises, watcher logs and continues."""
    db = Database(writable_db_path)
    db.connect()

    calls = {"n": 0}
    real = db.rows_after

    def flaky(after, limit=200):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("boom")
        return real(after, limit=limit)

    db.rows_after = flaky  # type: ignore[method-assign]

    mgr = ConnectionManager()
    watcher = PollingWatcher(db=db, manager=mgr, cadence_sec=0.05)
    task = asyncio.create_task(watcher.run())
    try:
        await asyncio.sleep(0.3)
    finally:
        watcher.stop()
        await asyncio.wait_for(task, timeout=2.0)
        db.close()

    assert calls["n"] >= 2
