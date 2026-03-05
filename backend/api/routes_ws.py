from __future__ import annotations

import asyncio
import json

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from websocket.ws_manager import ws_manager

logger = structlog.get_logger()

router = APIRouter(tags=["websocket"])


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    """WebSocket endpoint for real-time updates to frontend."""
    await ws_manager.connect(ws)
    try:
        while True:
            # Keep connection alive; receive any client messages
            data = await ws.receive_text()
            try:
                msg = json.loads(data)
                msg_type = msg.get("type", "")

                if msg_type == "ping":
                    await ws_manager.send_to(ws, "pong", {})
                elif msg_type == "subscribe":
                    # Could track subscriptions per client
                    logger.debug("ws_subscribe", channel=msg.get("channel"))

            except json.JSONDecodeError:
                pass

    except WebSocketDisconnect:
        ws_manager.disconnect(ws)
    except Exception as e:
        logger.error("ws_error", error=str(e))
        ws_manager.disconnect(ws)
