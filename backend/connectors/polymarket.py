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

GAMMA_API = "https://gamma-api.polymarket.com"
CLOB_API = "https://clob.polymarket.com"
DATA_API = "https://data-api.polymarket.com"


class PolymarketConnector(BaseConnector):
    platform = Platform.POLYMARKET

    def __init__(self) -> None:
        self._gamma_client: httpx.AsyncClient | None = None
        self._clob_client: httpx.AsyncClient | None = None
        self.connected = False

    async def connect(self) -> None:
        self._gamma_client = httpx.AsyncClient(
            base_url=GAMMA_API, timeout=15.0
        )
        self._clob_client = httpx.AsyncClient(
            base_url=CLOB_API, timeout=15.0
        )
        self.connected = True
        logger.info(
            "polymarket_connected",
            trading_enabled=bool(settings.polymarket_private_key),
        )

    async def disconnect(self) -> None:
        if self._gamma_client:
            await self._gamma_client.aclose()
        if self._clob_client:
            await self._clob_client.aclose()
        self.connected = False
        logger.info("polymarket_disconnected")

    async def get_markets(self, query: str = "", limit: int = 100) -> list[NormalizedMarket]:
        if not self._gamma_client:
            return []
        try:
            markets: list[NormalizedMarket] = []

            # Fetch multiple pages of events for broader coverage
            for offset in range(0, 200, 50):
                try:
                    params: dict[str, Any] = {
                        "limit": 50,
                        "offset": offset,
                        "active": "true",
                        "closed": "false",
                    }
                    resp = await self._gamma_client.get("/events", params=params)
                    resp.raise_for_status()
                    events = resp.json()
                    if not events:
                        break
                    for event in events:
                        for m in event.get("markets", []):
                            if not m.get("active") or m.get("closed"):
                                continue
                            normalized = self._normalize_market(m)
                            markets.extend(normalized)
                except Exception as e:
                    logger.warning("polymarket_events_page_failed", offset=offset, error=str(e))
                    break

            # Also fetch direct markets endpoint for broader coverage
            try:
                resp2 = await self._gamma_client.get("/markets", params={
                    "limit": 100,
                    "active": "true",
                    "closed": "false",
                })
                resp2.raise_for_status()
                for m in resp2.json():
                    normalized = self._normalize_market(m)
                    markets.extend(normalized)
            except Exception as e:
                logger.warning("polymarket_markets_fetch_failed", error=str(e))

            # Deduplicate by market_id
            seen: set[str] = set()
            unique: list[NormalizedMarket] = []
            for m in markets:
                if m.platform_market_id not in seen:
                    seen.add(m.platform_market_id)
                    unique.append(m)

            logger.info("polymarket_markets_fetched", count=len(unique))
            return unique
        except Exception as e:
            logger.error("polymarket_get_markets_failed", error=str(e))
            return []

    async def get_orderbook(self, market_id: str) -> OrderBook:
        """market_id here is the CLOB token_id (condition_id)."""
        if not self._clob_client:
            return OrderBook()
        try:
            resp = await self._clob_client.get(
                "/book", params={"token_id": market_id}
            )
            resp.raise_for_status()
            data = resp.json()
            return self._parse_orderbook(data)
        except Exception as e:
            logger.error("polymarket_orderbook_failed", market=market_id, error=str(e))
            return OrderBook()

    async def place_order(
        self,
        market_id: str,
        side: str,
        outcome: str,
        price_cents: int,
        quantity: int,
    ) -> dict[str, Any]:
        if not settings.polymarket_private_key:
            raise ConnectionError("Polymarket trading requires private key")

        # Polymarket uses py-clob-client for order signing
        # This is a simplified version; real impl needs EIP-712 signing
        try:
            price = price_cents / 100.0
            payload = {
                "tokenID": market_id,
                "price": str(price),
                "size": str(quantity),
                "side": "BUY" if side.lower() == "buy" else "SELL",
                "feeRateBps": "0",
                "nonce": "0",
            }
            logger.info(
                "polymarket_order_submitted",
                market=market_id,
                payload=payload,
            )
            # In production: use py_clob_client.ClobClient for proper signing
            return {"status": "submitted", "payload": payload}
        except Exception as e:
            logger.error("polymarket_order_failed", error=str(e))
            raise

    async def cancel_order(self, order_id: str) -> bool:
        logger.info("polymarket_cancel", order_id=order_id)
        return True

    async def get_balance(self) -> int:
        # Balance is on-chain USDC on Polygon — would need web3 call
        return 0

    async def get_positions(self) -> list[dict[str, Any]]:
        if not self._clob_client:
            return []
        return []

    def _normalize_market(self, raw: dict[str, Any]) -> list[NormalizedMarket]:
        """Polymarket markets can have multiple outcomes (tokens)."""
        results: list[NormalizedMarket] = []
        try:
            question = raw.get("question", "")
            category = raw.get("category", "")
            end_date = raw.get("end_date_iso") or raw.get("endDate")

            expiration = None
            if end_date:
                try:
                    expiration = datetime.fromisoformat(
                        end_date.replace("Z", "+00:00")
                    )
                except (ValueError, AttributeError):
                    pass

            active = raw.get("active", False)
            closed = raw.get("closed", False)
            if closed:
                status = MarketStatus.CLOSED
            elif active:
                status = MarketStatus.OPEN
            else:
                status = MarketStatus.UNKNOWN

            # Each market has tokens (YES/NO outcomes)
            import json as _json
            tokens = raw.get("tokens", [])
            clob_token_ids = raw.get("clobTokenIds", [])
            outcomes = raw.get("outcomes", ["Yes", "No"])
            outcome_prices = raw.get("outcomePrices", [])

            # These fields can be JSON strings instead of lists
            if isinstance(clob_token_ids, str):
                try:
                    clob_token_ids = _json.loads(clob_token_ids)
                except (ValueError, TypeError):
                    clob_token_ids = []
            if isinstance(outcomes, str):
                try:
                    outcomes = _json.loads(outcomes)
                except (ValueError, TypeError):
                    outcomes = ["Yes", "No"]

            # Use the first token (YES) as the market representation
            yes_token_id = ""
            no_token_id = ""
            yes_price = None
            no_price = None

            if clob_token_ids and len(clob_token_ids) >= 2:
                yes_token_id = clob_token_ids[0]
                no_token_id = clob_token_ids[1]
            elif tokens and len(tokens) >= 2:
                yes_token_id = tokens[0].get("token_id", "")
                no_token_id = tokens[1].get("token_id", "")

            if outcome_prices:
                try:
                    # outcomePrices can be a JSON string or a list
                    import json as _json
                    if isinstance(outcome_prices, str):
                        outcome_prices = _json.loads(outcome_prices)
                    prices = [float(p) for p in outcome_prices if p]
                    if len(prices) >= 1:
                        yes_price = int(prices[0] * 100)
                    if len(prices) >= 2:
                        no_price = int(prices[1] * 100)
                except (ValueError, TypeError):
                    pass

            condition_id = raw.get("conditionId", raw.get("condition_id", ""))
            market_id = condition_id or raw.get("id", "")

            market = NormalizedMarket(
                platform=Platform.POLYMARKET,
                platform_market_id=market_id,
                ticker=yes_token_id,
                title=question,
                category=category,
                yes_ask_cents=yes_price,
                no_ask_cents=no_price,
                status=status,
                volume=int(float(raw.get("volume", 0) or 0)),
                expiration=expiration,
            )
            results.append(market)

        except Exception as e:
            logger.warning("polymarket_normalize_failed", error=str(e))

        return results

    def _parse_orderbook(self, data: dict[str, Any]) -> OrderBook:
        def parse_levels(levels: list | None) -> list[OrderBookLevel]:
            if not levels:
                return []
            result = []
            for lv in levels:
                price = lv.get("price", "0")
                size = lv.get("size", "0")
                price_cents = int(float(price) * 100)
                qty = int(float(size))
                if 1 <= price_cents <= 99 and qty > 0:
                    result.append(OrderBookLevel(price_cents=price_cents, quantity=qty))
            return result

        asks = parse_levels(data.get("asks"))
        bids = parse_levels(data.get("bids"))

        return OrderBook(
            yes_asks=asks,
            yes_bids=bids,
            # Polymarket orderbook is per-token; NO is complement
            no_asks=[
                OrderBookLevel(price_cents=100 - b.price_cents, quantity=b.quantity)
                for b in bids
            ],
            no_bids=[
                OrderBookLevel(price_cents=100 - a.price_cents, quantity=a.quantity)
                for a in asks
            ],
        )
