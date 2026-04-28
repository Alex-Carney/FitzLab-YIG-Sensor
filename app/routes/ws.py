"""WebSocket endpoint for live trace push."""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from app.auth import SessionInvalidError, verify_session_cookie

logger = logging.getLogger("yig.ws.route")

router = APIRouter()


@router.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    settings = websocket.app.state.settings
    manager = websocket.app.state.manager

    cookie = websocket.cookies.get(settings.cookie_name)
    try:
        verify_session_cookie(settings.secret, cookie)
    except SessionInvalidError:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()
    manager.add(websocket)
    logger.info("ws client connected (total=%d)", manager.count())

    ping_interval = settings.ws_ping_interval_sec

    async def _ping_loop():
        try:
            while True:
                await asyncio.sleep(ping_interval)
                try:
                    await websocket.send_json({"type": "ping"})
                except Exception:
                    return
        except asyncio.CancelledError:
            return

    pinger = asyncio.create_task(_ping_loop())
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning("ws error: %s", e)
    finally:
        pinger.cancel()
        manager.remove(websocket)
        logger.info("ws client disconnected (total=%d)", manager.count())
