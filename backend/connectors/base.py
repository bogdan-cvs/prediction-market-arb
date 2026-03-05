from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from models.market import NormalizedMarket, OrderBook, Platform


class BaseConnector(ABC):
    platform: Platform
    connected: bool = False

    @abstractmethod
    async def connect(self) -> None:
        """Initialize connection / authenticate."""

    @abstractmethod
    async def disconnect(self) -> None:
        """Clean up resources."""

    @abstractmethod
    async def get_markets(self, query: str = "", limit: int = 100) -> list[NormalizedMarket]:
        """Fetch available markets, optionally filtered by query."""

    @abstractmethod
    async def get_orderbook(self, market_id: str) -> OrderBook:
        """Fetch current orderbook for a market."""

    @abstractmethod
    async def place_order(
        self,
        market_id: str,
        side: str,
        outcome: str,
        price_cents: int,
        quantity: int,
    ) -> dict[str, Any]:
        """Place an order. Returns platform-specific order info."""

    @abstractmethod
    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an open order."""

    @abstractmethod
    async def get_balance(self) -> int:
        """Get available balance in cents."""

    @abstractmethod
    async def get_positions(self) -> list[dict[str, Any]]:
        """Get open positions."""

    def is_connected(self) -> bool:
        return self.connected
