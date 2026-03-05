from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

import httpx
import structlog

from config import settings
from connectors.base import BaseConnector
from models.market import (
    MarketStatus,
    NormalizedMarket,
    OrderBook,
    OrderBookLevel,
    Platform,
)

logger = structlog.get_logger()

BASE_URL = settings.kalshi_base_url
TRADE_URL = BASE_URL.replace("demo-api", "api") if "demo" not in BASE_URL else BASE_URL


class KalshiConnector(BaseConnector):
    platform = Platform.KALSHI

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None
        self._token: str = ""
        self.connected = False

    async def connect(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=BASE_URL,
            timeout=15.0,
            headers={"Accept": "application/json"},
        )
        if settings.kalshi_api_key:
            try:
                await self._authenticate()
                self.connected = True
                logger.info("kalshi_connected", mode="authenticated")
            except Exception as e:
                logger.warning("kalshi_auth_failed", error=str(e))
                self.connected = True  # can still read public data
                logger.info("kalshi_connected", mode="public_only")
        else:
            self.connected = True
            logger.info("kalshi_connected", mode="public_only")

    async def _authenticate(self) -> None:
        # Kalshi v2 uses API key + private key for signing
        # For now, use API key header approach
        if self._client:
            self._client.headers["Authorization"] = f"Bearer {settings.kalshi_api_key}"

    async def disconnect(self) -> None:
        if self._client:
            await self._client.aclose()
        self.connected = False
        logger.info("kalshi_disconnected")

    async def get_markets(self, query: str = "", limit: int = 100) -> list[NormalizedMarket]:
        if not self._client:
            return []
        try:
            params: dict[str, Any] = {"limit": min(limit, 200), "status": "open"}
            if query:
                params["series_ticker"] = query

            resp = await self._client.get("/trade-api/v2/markets", params=params)
            resp.raise_for_status()
            data = resp.json()

            markets: list[NormalizedMarket] = []
            for m in data.get("markets", []):
                market = self._normalize_market(m)
                if market:
                    markets.append(market)
            logger.info("kalshi_markets_fetched", count=len(markets))
            return markets
        except Exception as e:
            logger.error("kalshi_get_markets_failed", error=str(e))
            return []

    async def get_orderbook(self, market_id: str) -> OrderBook:
        if not self._client:
            return OrderBook()
        try:
            resp = await self._client.get(
                f"/trade-api/v2/markets/{market_id}/orderbook",
                params={"depth": 10},
            )
            resp.raise_for_status()
            data = resp.json().get("orderbook", {})
            return self._parse_orderbook(data)
        except Exception as e:
            logger.error("kalshi_orderbook_failed", market=market_id, error=str(e))
            return OrderBook()

    async def place_order(
        self,
        market_id: str,
        side: str,
        outcome: str,
        price_cents: int,
        quantity: int,
    ) -> dict[str, Any]:
        if not self._client:
            raise ConnectionError("Kalshi not connected")
        try:
            payload = {
                "ticker": market_id,
                "action": side.lower(),  # "buy" or "sell"
                "side": outcome.lower(),  # "yes" or "no"
                "type": "limit",
                "yes_price": price_cents if outcome.upper() == "YES" else 100 - price_cents,
                "count": quantity,
            }
            resp = await self._client.post("/trade-api/v2/portfolio/orders", json=payload)
            resp.raise_for_status()
            result = resp.json()
            logger.info("kalshi_order_placed", market=market_id, result=result)
            return result
        except Exception as e:
            logger.error("kalshi_order_failed", market=market_id, error=str(e))
            raise

    async def cancel_order(self, order_id: str) -> bool:
        if not self._client:
            return False
        try:
            resp = await self._client.delete(f"/trade-api/v2/portfolio/orders/{order_id}")
            resp.raise_for_status()
            return True
        except Exception:
            return False

    async def get_balance(self) -> int:
        if not self._client:
            return 0
        try:
            resp = await self._client.get("/trade-api/v2/portfolio/balance")
            resp.raise_for_status()
            data = resp.json()
            return int(data.get("balance", 0))
        except Exception:
            return 0

    async def get_positions(self) -> list[dict[str, Any]]:
        if not self._client:
            return []
        try:
            resp = await self._client.get("/trade-api/v2/portfolio/positions")
            resp.raise_for_status()
            return resp.json().get("market_positions", [])
        except Exception:
            return []

    def _normalize_market(self, raw: dict[str, Any]) -> NormalizedMarket | None:
        try:
            ticker = raw.get("ticker", "")
            title = raw.get("title", raw.get("subtitle", ticker))
            yes_ask = raw.get("yes_ask")
            yes_bid = raw.get("yes_bid")
            no_ask = raw.get("no_ask")
            no_bid = raw.get("no_bid")

            status_map = {
                "open": MarketStatus.OPEN,
                "closed": MarketStatus.CLOSED,
                "settled": MarketStatus.SETTLED,
            }

            exp = raw.get("expiration_time") or raw.get("close_time")
            expiration = None
            if exp:
                try:
                    expiration = datetime.fromisoformat(exp.replace("Z", "+00:00"))
                except (ValueError, AttributeError):
                    pass

            return NormalizedMarket(
                platform=Platform.KALSHI,
                platform_market_id=ticker,
                ticker=ticker,
                title=title,
                category=raw.get("category", ""),
                yes_ask_cents=yes_ask,
                yes_bid_cents=yes_bid,
                no_ask_cents=no_ask,
                no_bid_cents=no_bid,
                status=status_map.get(raw.get("status", ""), MarketStatus.UNKNOWN),
                volume=raw.get("volume", 0),
                expiration=expiration,
            )
        except Exception as e:
            logger.warning("kalshi_normalize_failed", error=str(e))
            return None

    def _parse_orderbook(self, data: dict[str, Any]) -> OrderBook:
        def parse_levels(levels: list | None) -> list[OrderBookLevel]:
            if not levels:
                return []
            return [
                OrderBookLevel(price_cents=int(lv[0]), quantity=int(lv[1]))
                for lv in levels
                if len(lv) >= 2
            ]

        return OrderBook(
            yes_asks=parse_levels(data.get("yes", {}).get("asks")),
            yes_bids=parse_levels(data.get("yes", {}).get("bids")),
            no_asks=parse_levels(data.get("no", {}).get("asks")),
            no_bids=parse_levels(data.get("no", {}).get("bids")),
        )
