"""Standalone E2E smoke test (not part of pytest).

Verifies a running uvicorn dev server: login + REST endpoints + WS handshake.
Does NOT attempt to write a row from this process - the API holds a read-only
DuckDB connection which on Windows still locks the file against concurrent
writers (matches the production constraint where the tracker owns writes).

Run while uvicorn is already up:
    uv run python tests/e2e_smoke.py
"""
from __future__ import annotations

import asyncio
import os
import sys

import httpx
import websockets

URL = "http://127.0.0.1:8000"
WS_URL = "ws://127.0.0.1:8000/ws"
PASSWORD = os.environ.get("YIG_DASHBOARD_PASSWORD", "labpassword")


async def main() -> int:
    failed = False

    async with httpx.AsyncClient(base_url=URL) as c:
        r = await c.get("/healthz")
        assert r.status_code == 200, f"healthz {r.status_code}"
        h = r.json()
        print(f"  /healthz ok={h['ok']} stale={h['stale']} watcher_running={h['watcher_running']}")

        r = await c.post("/login", json={"password": "wrong"})
        assert r.status_code == 401, f"wrong-password should be 401, got {r.status_code}"
        print("  wrong-password rejected (401)")

        r = await c.post("/login", json={"password": PASSWORD})
        assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
        cookie = r.cookies.get("yig_session")
        assert cookie, "no session cookie returned"
        print("  login ok, session cookie issued")

        r = await c.get("/api/snapshot")
        assert r.status_code == 200
        body = r.json()
        if body["data"] is not None:
            print(f"  /api/snapshot ok: center {body['data']['center_freq']/1e9:.6f} GHz, "
                  f"{body['data']['n_points']} points")
        else:
            print("  /api/snapshot returned null (empty DB)")

        r = await c.get("/api/stats", params={"window": "1h"})
        assert r.status_code == 200
        s = r.json()
        print(f"  /api/stats: {s['traces_in_window']} traces in window, "
              f"current SNR {s['current_snr_db']:.1f} dB")

    # No-cookie WS handshake should be rejected
    try:
        async with websockets.connect(WS_URL, open_timeout=2):
            print("  FAIL: WS connected without cookie")
            failed = True
    except Exception as e:
        print(f"  WS without cookie rejected ({type(e).__name__})")

    # Cookied WS handshake should succeed
    headers = {"cookie": f"yig_session={cookie}"}
    try:
        async with websockets.connect(WS_URL, additional_headers=headers, open_timeout=3) as ws:
            print("  WS with cookie connected")
            # Don't wait for an actual broadcast — that needs the tracker writing.
    except Exception as e:
        print(f"  FAIL: WS with cookie rejected: {e}")
        failed = True

    if failed:
        return 1
    print("PASS: end-to-end smoke")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
