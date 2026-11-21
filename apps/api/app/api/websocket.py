from __future__ import annotations

import asyncio
from typing import Any
from fastapi import WebSocket

from apps.api.app.core.database import utc_iso, utc_now


class ConnectionManager:
    """Manages /ws/live WebSocket clients and broadcasts structured operational events."""

    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections.add(websocket)

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._connections.discard(websocket)

    async def broadcast(self, event_name: str, data: dict[str, Any]) -> None:
        message = {
            "event": event_name,
            "timestamp": utc_iso(utc_now()),
            "data": data,
        }
        async with self._lock:
            targets = list(self._connections)

        stale: list[WebSocket] = []
        for ws in targets:
            try:
                await ws.send_json(message)
            except Exception:
                stale.append(ws)

        if stale:
            async with self._lock:
                for ws in stale:
                    self._connections.discard(ws)

    def broadcast_sync(self, event_name: str, data: dict[str, Any]) -> None:
        """Schedule a broadcast when called from sync code inside an active event loop."""
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.broadcast(event_name, data))
        except RuntimeError:
            pass
