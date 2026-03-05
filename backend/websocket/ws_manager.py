from __future__ import annotations

import asyncio
import json
from typing import Any

import structlog
from fastapi import WebSocket

logger = structlog.get_logger()


class WSManager:
    """Manages WebSocket connections to frontend clients."""

    def __init__(self) -> None:
        self._connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.append(ws)
        logger.info("ws_client_connected", total=len(self._connections))

    def disconnect(self, ws: WebSocket) -> None:
        if ws in self._connections:
            self._connections.remove(ws)
        logger.info("ws_client_disconnected", total=len(self._connections))

    async def broadcast(self, event_type: str, data: Any) -> None:
        """Send a message to all connected clients."""
        if not self._connections:
            return

        message = json.dumps({"type": event_type, "data": data}, default=str)
        dead: list[WebSocket] = []

        for ws in self._connections:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)

        for ws in dead:
            self.disconnect(ws)

    async def send_to(self, ws: WebSocket, event_type: str, data: Any) -> None:
        try:
            message = json.dumps({"type": event_type, "data": data}, default=str)
            await ws.send_text(message)
        except Exception:
            self.disconnect(ws)

    @property
    def client_count(self) -> int:
        return len(self._connections)


ws_manager = WSManager()
