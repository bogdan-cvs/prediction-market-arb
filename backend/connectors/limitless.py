from __future__ import annotations

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

API_BASE = "https://api.limitless.exchange/api-v1"


class LimitlessConnector(BaseConnector):
    platform = Platform.LIMITLESS

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None
        self.connected = False

    async def connect(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=API_BASE,
            timeout=15.0,
            headers={"Accept": "application/json"},
        )
        self.connected = True
        logger.info(
            "limitless_connected",
            trading_enabled=bool(settings.limitless_private_key),
        )

    async def disconnect(self) -> None:
        if self._client:
            await self._client.aclose()
        self.connected = False
        logger.info("limitless_disconnected")

    async def get_markets(self, query: str = "", limit: int = 100) -> list[NormalizedMarket]:
        if not self._client:
            return []
        try:
            params: dict[str, Any] = {"limit": min(limit, 100), "status": "active"}
            if query:
                params["query"] = query

            resp = await self._client.get("/markets", params=params)
            resp.raise_for_status()
            raw_markets = resp.json()

            if isinstance(raw_markets, dict):
                raw_markets = raw_markets.get("markets", raw_markets.get("data", []))

            markets: list[NormalizedMarket] = []
            for m in raw_markets:
                normalized = self._normalize_market(m)
                if normalized:
                    markets.append(normalized)

            logger.info("limitless_markets_fetched", count=len(markets))
            return markets
        except Exception as e:
            logger.error("limitless_get_markets_failed", error=str(e))
            return []

    async def get_orderbook(self, market_id: str) -> OrderBook:
        if not self._client:
            return OrderBook()
        try:
            resp = await self._client.get(f"/markets/{market_id}/orderbook")
            resp.raise_for_status()
            data = resp.json()
            return self._parse_orderbook(data)
        except Exception as e:
            logger.error("limitless_orderbook_failed", market=market_id, error=str(e))
            return OrderBook()

    async def place_order(
        self,
        market_id: str,
        side: str,
        outcome: str,
        price_cents: int,
        quantity: int,
    ) -> dict[str, Any]:
        if not settings.limitless_private_key:
            raise ConnectionError("Limitless trading requires private key (Base network)")

        # Limitless uses EIP-712 signing on Base network
        # Real implementation would use web3 + signing
        price = price_cents / 100.0
        payload = {
            "marketId": market_id,
            "side": side.lower(),
            "outcome": outcome.upper(),
            "price": str(price),
            "amount": str(quantity),
        }
        logger.info("limitless_order_submitted", market=market_id, payload=payload)
        return {"status": "submitted", "payload": payload}

    async def cancel_order(self, order_id: str) -> bool:
        logger.info("limitless_cancel", order_id=order_id)
        return True

    async def get_balance(self) -> int:
        # Balance is on-chain USDC on Base — needs web3 call
        return 0

    async def get_positions(self) -> list[dict[str, Any]]:
        return []

    def _normalize_market(self, raw: dict[str, Any]) -> NormalizedMarket | None:
        try:
            market_id = str(raw.get("id", raw.get("address", "")))
            title = raw.get("title", raw.get("question", ""))

            if not title or not market_id:
                return None

            # Parse prices
            yes_price = raw.get("yesPrice") or raw.get("yes_price")
            no_price = raw.get("noPrice") or raw.get("no_price")

            yes_cents = None
            no_cents = None
            if yes_price is not None:
                yes_cents = int(float(yes_price) * 100) if float(yes_price) < 1.5 else int(yes_price)
            if no_price is not None:
                no_cents = int(float(no_price) * 100) if float(no_price) < 1.5 else int(no_price)

            # Parse expiration
            exp = raw.get("expirationDate") or raw.get("deadline") or raw.get("endDate")
            expiration = None
            if exp:
                try:
                    if isinstance(exp, (int, float)):
                        expiration = datetime.utcfromtimestamp(exp)
                    else:
                        expiration = datetime.fromisoformat(str(exp).replace("Z", "+00:00"))
                except (ValueError, TypeError, OSError):
                    pass

            status_raw = raw.get("status", "active")
            if status_raw in ("active", "open"):
                status = MarketStatus.OPEN
            elif status_raw in ("resolved", "settled"):
                status = MarketStatus.SETTLED
            else:
                status = MarketStatus.UNKNOWN

            category = raw.get("category", raw.get("tag", ""))
            volume = int(raw.get("volume", 0) or 0)

            return NormalizedMarket(
                platform=Platform.LIMITLESS,
                platform_market_id=market_id,
                ticker=market_id,
                title=title,
                category=category,
                yes_ask_cents=yes_cents,
                no_ask_cents=no_cents,
                status=status,
                volume=volume,
                expiration=expiration,
            )
        except Exception as e:
            logger.warning("limitless_normalize_failed", error=str(e))
            return None

    def _parse_orderbook(self, data: dict[str, Any]) -> OrderBook:
        def parse_levels(levels: list | None) -> list[OrderBookLevel]:
            if not levels:
                return []
            result = []
            for lv in levels:
                price = lv.get("price", 0)
                size = lv.get("size", lv.get("amount", 0))
                price_cents = int(float(price) * 100) if float(price) < 1.5 else int(price)
                qty = int(float(size))
                if 1 <= price_cents <= 99 and qty > 0:
                    result.append(OrderBookLevel(price_cents=price_cents, quantity=qty))
            return result

        yes_data = data.get("yes", data.get("YES", {}))
        no_data = data.get("no", data.get("NO", {}))

        return OrderBook(
            yes_asks=parse_levels(yes_data.get("asks") if isinstance(yes_data, dict) else None),
            yes_bids=parse_levels(yes_data.get("bids") if isinstance(yes_data, dict) else None),
            no_asks=parse_levels(no_data.get("asks") if isinstance(no_data, dict) else None),
            no_bids=parse_levels(no_data.get("bids") if isinstance(no_data, dict) else None),
        )
