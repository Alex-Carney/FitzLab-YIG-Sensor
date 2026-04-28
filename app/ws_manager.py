"""WebSocket connection set and broadcaster."""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Protocol

logger = logging.getLogger("yig.ws")


class _Sendable(Protocol):
    async def send_json(self, data: Any) -> None: ...


class ConnectionManager:
    def __init__(self) -> None:
        self._clients: set[_Sendable] = set()
        self._lock = asyncio.Lock()

    def add(self, ws: _Sendable) -> None:
        self._clients.add(ws)

    def remove(self, ws: _Sendable) -> None:
        self._clients.discard(ws)

    def count(self) -> int:
        return len(self._clients)

    async def broadcast(self, payload: Any) -> None:
        if not self._clients:
            return
        clients = list(self._clients)

        async def _safe_send(ws: _Sendable):
            try:
                await ws.send_json(payload)
                return None
            except Exception as e:
                logger.warning("WS send failed (%s); pruning", e)
                return ws

        results = await asyncio.gather(
            *(_safe_send(c) for c in clients),
            return_exceptions=False,
        )
        for dead in results:
            if dead is not None:
                self.remove(dead)
