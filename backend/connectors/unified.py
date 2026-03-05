from __future__ import annotations

import asyncio
from typing import Any

import structlog

from connectors.base import BaseConnector
from connectors.kalshi import KalshiConnector
from connectors.polymarket import PolymarketConnector
from connectors.limitless import LimitlessConnector
from connectors.ibkr import IBKRConnector
from models.market import NormalizedMarket, OrderBook, Platform

logger = structlog.get_logger()


class UnifiedConnector:
    """Wraps all platform connectors behind a single interface."""

    def __init__(self) -> None:
        self.connectors: dict[Platform, BaseConnector] = {
            Platform.KALSHI: KalshiConnector(),
            Platform.POLYMARKET: PolymarketConnector(),
            Platform.LIMITLESS: LimitlessConnector(),
            Platform.IBKR: IBKRConnector(),
        }

    async def connect_all(self) -> dict[Platform, bool]:
        """Connect to all platforms concurrently. Returns connection status."""
        results: dict[Platform, bool] = {}
        tasks = []
        for platform, connector in self.connectors.items():
            tasks.append(self._safe_connect(platform, connector))

        statuses = await asyncio.gather(*tasks)
        for platform, ok in statuses:
            results[platform] = ok

        connected = [p.value for p, ok in results.items() if ok]
        failed = [p.value for p, ok in results.items() if not ok]
        logger.info("unified_connect_done", connected=connected, failed=failed)
        return results

    async def _safe_connect(
        self, platform: Platform, connector: BaseConnector
    ) -> tuple[Platform, bool]:
        try:
            await connector.connect()
            return (platform, connector.is_connected())
        except Exception as e:
            logger.error("connector_failed", platform=platform.value, error=str(e))
            return (platform, False)

    async def disconnect_all(self) -> None:
        for connector in self.connectors.values():
            try:
                await connector.disconnect()
            except Exception:
                pass

    def get_connector(self, platform: Platform) -> BaseConnector:
        return self.connectors[platform]

    def get_status(self) -> dict[str, bool]:
        return {p.value: c.is_connected() for p, c in self.connectors.items()}

    async def get_all_markets(
        self, query: str = "", limit: int = 100
    ) -> dict[Platform, list[NormalizedMarket]]:
        """Fetch markets from all connected platforms concurrently."""
        results: dict[Platform, list[NormalizedMarket]] = {}
        tasks = []

        for platform, connector in self.connectors.items():
            if connector.is_connected():
                tasks.append(self._fetch_markets(platform, connector, query, limit))

        fetched = await asyncio.gather(*tasks)
        for platform, markets in fetched:
            results[platform] = markets

        return results

    async def _fetch_markets(
        self,
        platform: Platform,
        connector: BaseConnector,
        query: str,
        limit: int,
    ) -> tuple[Platform, list[NormalizedMarket]]:
        try:
            markets = await connector.get_markets(query, limit)
            return (platform, markets)
        except Exception as e:
            logger.error("fetch_markets_failed", platform=platform.value, error=str(e))
            return (platform, [])

    async def get_orderbook(self, platform: Platform, market_id: str) -> OrderBook:
        connector = self.connectors[platform]
        if not connector.is_connected():
            return OrderBook()
        return await connector.get_orderbook(market_id)

    async def place_order(
        self,
        platform: Platform,
        market_id: str,
        side: str,
        outcome: str,
        price_cents: int,
        quantity: int,
    ) -> dict[str, Any]:
        connector = self.connectors[platform]
        return await connector.place_order(market_id, side, outcome, price_cents, quantity)

    async def get_all_balances(self) -> dict[Platform, int]:
        results: dict[Platform, int] = {}
        for platform, connector in self.connectors.items():
            if connector.is_connected():
                try:
                    results[platform] = await connector.get_balance()
                except Exception:
                    results[platform] = 0
            else:
                results[platform] = 0
        return results
