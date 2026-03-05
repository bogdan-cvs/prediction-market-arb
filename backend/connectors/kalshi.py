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
            all_markets: list[NormalizedMarket] = []
            seen_ids: set[str] = set()

            # Strategy 1: Fetch all events (sequential pages), then fetch
            # per-event markets concurrently with a semaphore
            try:
                # Phase A: collect all events
                all_events: list[dict] = []
                cursor = None
                pages = 0
                while pages < 5:
                    params: dict[str, Any] = {"limit": 50, "status": "open"}
                    if cursor:
                        params["cursor"] = cursor
                    resp = await self._client.get("/trade-api/v2/events", params=params)
                    resp.raise_for_status()
                    data = resp.json()
                    events = data.get("events", [])
                    if not events:
                        break
                    all_events.extend(events)
                    cursor = data.get("cursor")
                    if not cursor:
                        break
                    pages += 1

                # Phase B: fetch per-event markets in batches of 5 with delay
                BATCH_SIZE = 5

                async def _fetch_event_markets(event: dict) -> list[dict]:
                    event_ticker = event.get("event_ticker", "")
                    if not event_ticker:
                        return []
                    for attempt in range(3):
                        try:
                            mresp = await self._client.get(
                                "/trade-api/v2/markets",
                                params={"event_ticker": event_ticker, "limit": 50, "status": "open"},
                            )
                            if mresp.status_code == 429:
                                await asyncio.sleep(1.0 * (attempt + 1))
                                continue
                            mresp.raise_for_status()
                            result = []
                            for m in mresp.json().get("markets", []):
                                m["_event_title"] = event.get("title", "")
                                m["_event_category"] = event.get("category", "")
                                result.append(m)
                            return result
                        except Exception:
                            if attempt < 2:
                                await asyncio.sleep(0.5)
                            continue
                    return []

                # Process in batches: 5 concurrent, 0.3s between batches
                all_raw: list[dict] = []
                for i in range(0, len(all_events), BATCH_SIZE):
                    batch = all_events[i:i + BATCH_SIZE]
                    batch_results = await asyncio.gather(
                        *[_fetch_event_markets(ev) for ev in batch]
                    )
                    for market_list in batch_results:
                        all_raw.extend(market_list)
                    if i + BATCH_SIZE < len(all_events):
                        await asyncio.sleep(0.3)

                for m in all_raw:
                    market = self._normalize_market(m)
                    if market and market.platform_market_id not in seen_ids:
                        seen_ids.add(market.platform_market_id)
                        all_markets.append(market)

            except Exception as e:
                logger.warning("kalshi_events_fetch_failed", error=str(e))

            # Strategy 2: Fetch key crypto series specifically
            for series in ["KXBTC", "KXETH"]:
                try:
                    params = {"limit": 50, "status": "open", "series_ticker": series}
                    resp = await self._client.get("/trade-api/v2/markets", params=params)
                    resp.raise_for_status()
                    data = resp.json()
                    for m in data.get("markets", []):
                        market = self._normalize_market(m)
                        if market and market.platform_market_id not in seen_ids:
                            seen_ids.add(market.platform_market_id)
                            all_markets.append(market)
                except Exception as e:
                    logger.warning("kalshi_series_fetch_failed", series=series, error=str(e))

            logger.info("kalshi_markets_fetched", count=len(all_markets))
            return all_markets
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
            # Use event title if market title is too generic or same as event
            event_title = raw.get("_event_title", "")
            event_category = raw.get("_event_category", "")
            if event_title and title == event_title:
                pass
            elif event_title and not title:
                title = event_title

            # Skip parlay/combo markets (multi-leg bets with comma-separated outcomes)
            if title and (title.startswith("yes ") or title.startswith("no ") or title.count(",yes ") >= 1 or title.count(",no ") >= 1):
                return None

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
                category=raw.get("category", "") or raw.get("_event_category", ""),
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
        def parse_levels(levels) -> list[OrderBookLevel]:
            if not levels or not isinstance(levels, list):
                return []
            result = []
            for lv in levels:
                if isinstance(lv, (list, tuple)) and len(lv) >= 2:
                    price = int(lv[0])
                    qty = int(lv[1])
                    if 1 <= price <= 99 and qty > 0:
                        result.append(OrderBookLevel(price_cents=price, quantity=qty))
            return result

        # Kalshi v2 orderbook: {"yes": [[price, qty], ...], "no": [[price, qty], ...]}
        # "yes" = bids to BUY yes, "no" = bids to BUY no
        # A NO bid at price P is equivalent to a YES ask at (100 - P) and vice versa.
        yes_bids_raw = data.get("yes")
        no_bids_raw = data.get("no")

        if isinstance(yes_bids_raw, dict):
            yes_bids_raw = yes_bids_raw.get("asks", [])
        if isinstance(no_bids_raw, dict):
            no_bids_raw = no_bids_raw.get("asks", [])

        yes_bids = parse_levels(yes_bids_raw)
        no_bids = parse_levels(no_bids_raw)

        # Derive asks from the complement side's bids
        yes_asks = [
            OrderBookLevel(price_cents=100 - b.price_cents, quantity=b.quantity)
            for b in no_bids
            if 1 <= 100 - b.price_cents <= 99
        ]
        no_asks = [
            OrderBookLevel(price_cents=100 - b.price_cents, quantity=b.quantity)
            for b in yes_bids
            if 1 <= 100 - b.price_cents <= 99
        ]

        return OrderBook(
            yes_asks=yes_asks,
            yes_bids=yes_bids,
            no_asks=no_asks,
            no_bids=no_bids,
        )
