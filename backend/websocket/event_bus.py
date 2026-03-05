from __future__ import annotations

import asyncio
import json
from typing import Any, Callable, Coroutine

import structlog

logger = structlog.get_logger()


class EventBus:
    """Simple async pub/sub for internal events."""

    def __init__(self) -> None:
        self._subscribers: dict[str, list[Callable]] = {}

    def subscribe(self, event_type: str, callback: Callable) -> None:
        self._subscribers.setdefault(event_type, []).append(callback)

    def unsubscribe(self, event_type: str, callback: Callable) -> None:
        if event_type in self._subscribers:
            self._subscribers[event_type] = [
                cb for cb in self._subscribers[event_type] if cb != callback
            ]

    async def emit(self, event_type: str, data: Any = None) -> None:
        for callback in self._subscribers.get(event_type, []):
            try:
                result = callback(event_type, data)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.error("event_bus_error", event=event_type, error=str(e))


event_bus = EventBus()
