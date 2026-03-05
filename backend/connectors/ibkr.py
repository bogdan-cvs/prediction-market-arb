from __future__ import annotations

import asyncio
from typing import Any

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


class IBKRConnector(BaseConnector):
    """Interactive Brokers / ForecastEx connector.

    Requires TWS or IB Gateway running locally.
    ForecastEx contracts: secType='OPT', exchange='FORECASTX'
    IMPORTANT: ForecastEx does NOT support SELL. To exit, buy the opposite outcome.
    """

    platform = Platform.IBKR

    def __init__(self) -> None:
        self._ib = None  # ib_insync.IB instance
        self.connected = False

    async def connect(self) -> None:
        try:
            from ib_insync import IB

            self._ib = IB()
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self._ib.connect(
                    settings.ibkr_host,
                    settings.ibkr_port,
                    clientId=settings.ibkr_client_id,
                ),
            )
            self.connected = True
            logger.info(
                "ibkr_connected",
                host=settings.ibkr_host,
                port=settings.ibkr_port,
            )
        except ImportError:
            logger.warning("ibkr_ib_insync_not_installed")
            self.connected = False
        except Exception as e:
            logger.warning("ibkr_connection_failed", error=str(e))
            self.connected = False

    async def disconnect(self) -> None:
        if self._ib:
            try:
                self._ib.disconnect()
            except Exception:
                pass
        self.connected = False
        logger.info("ibkr_disconnected")

    async def get_markets(self, query: str = "", limit: int = 100) -> list[NormalizedMarket]:
        if not self._ib or not self.connected:
            return self._get_mock_markets()

        try:
            from ib_insync import Contract

            contract = Contract(exchange="FORECASTX", secType="OPT")
            details_list = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self._ib.reqContractDetails(contract),
            )

            markets: list[NormalizedMarket] = []
            for details in details_list[:limit]:
                c = details.contract
                title = details.longName or f"{c.symbol} {c.lastTradeDateOrContractMonth}"
                markets.append(
                    NormalizedMarket(
                        platform=Platform.IBKR,
                        platform_market_id=str(c.conId),
                        ticker=c.localSymbol or c.symbol,
                        title=title,
                        category="forecastex",
                        status=MarketStatus.OPEN,
                    )
                )

            logger.info("ibkr_markets_fetched", count=len(markets))
            return markets
        except Exception as e:
            logger.error("ibkr_get_markets_failed", error=str(e))
            return self._get_mock_markets()

    async def get_orderbook(self, market_id: str) -> OrderBook:
        if not self._ib or not self.connected:
            return self._get_mock_orderbook()

        try:
            from ib_insync import Contract

            contract = Contract(conId=int(market_id), exchange="FORECASTX")
            ticker = self._ib.reqMktData(contract)
            await asyncio.sleep(2)  # wait for data

            yes_ask = int(ticker.ask * 100) if ticker.ask and ticker.ask > 0 else None
            yes_bid = int(ticker.bid * 100) if ticker.bid and ticker.bid > 0 else None

            levels: list[OrderBookLevel] = []
            if yes_ask and 1 <= yes_ask <= 99:
                levels.append(
                    OrderBookLevel(
                        price_cents=yes_ask,
                        quantity=int(ticker.askSize or 0),
                    )
                )

            self._ib.cancelMktData(contract)

            return OrderBook(
                yes_asks=levels,
                yes_bids=[
                    OrderBookLevel(price_cents=yes_bid, quantity=int(ticker.bidSize or 0))
                ]
                if yes_bid and 1 <= yes_bid <= 99
                else [],
            )
        except Exception as e:
            logger.error("ibkr_orderbook_failed", market=market_id, error=str(e))
            return OrderBook()

    async def place_order(
        self,
        market_id: str,
        side: str,
        outcome: str,
        price_cents: int,
        quantity: int,
    ) -> dict[str, Any]:
        """ForecastEx only supports BUY. To exit, buy the opposite outcome."""
        if not self._ib or not self.connected:
            raise ConnectionError("IBKR/TWS not connected")

        if side.upper() == "SELL":
            raise ValueError(
                "ForecastEx does not support SELL. Buy the opposite outcome instead."
            )

        try:
            from ib_insync import Contract, LimitOrder

            contract = Contract(conId=int(market_id), exchange="FORECASTX")
            order = LimitOrder("BUY", quantity, price_cents / 100.0)
            trade = self._ib.placeOrder(contract, order)

            logger.info(
                "ibkr_order_placed",
                market=market_id,
                outcome=outcome,
                price=price_cents,
                qty=quantity,
            )
            return {
                "orderId": trade.order.orderId,
                "status": trade.orderStatus.status,
            }
        except Exception as e:
            logger.error("ibkr_order_failed", error=str(e))
            raise

    async def cancel_order(self, order_id: str) -> bool:
        if not self._ib:
            return False
        try:
            for trade in self._ib.trades():
                if str(trade.order.orderId) == order_id:
                    self._ib.cancelOrder(trade.order)
                    return True
            return False
        except Exception:
            return False

    async def get_balance(self) -> int:
        if not self._ib or not self.connected:
            return 0
        try:
            account_values = self._ib.accountValues()
            for av in account_values:
                if av.tag == "CashBalance" and av.currency == "USD":
                    return int(float(av.value) * 100)
            return 0
        except Exception:
            return 0

    async def get_positions(self) -> list[dict[str, Any]]:
        if not self._ib or not self.connected:
            return []
        try:
            positions = self._ib.positions()
            return [
                {
                    "conId": p.contract.conId,
                    "symbol": p.contract.localSymbol,
                    "quantity": p.position,
                    "avgCost": p.avgCost,
                }
                for p in positions
                if p.contract.exchange == "FORECASTX"
            ]
        except Exception:
            return []

    def _get_mock_markets(self) -> list[NormalizedMarket]:
        """Return mock ForecastEx markets when TWS is not running."""
        mocks = [
            ("FXBTC-100K-MAR26", "BTC above $100,000 on March 26?", 62, 39),
            ("FXETH-4K-MAR26", "ETH above $4,000 on March 26?", 35, 66),
            ("FXSPY-600-MAR26", "SPY above $600 on March 26?", 55, 46),
        ]
        markets = []
        for ticker, title, yes_ask, no_ask in mocks:
            markets.append(
                NormalizedMarket(
                    platform=Platform.IBKR,
                    platform_market_id=ticker,
                    ticker=ticker,
                    title=title,
                    category="forecastex",
                    yes_ask_cents=yes_ask,
                    no_ask_cents=no_ask,
                    status=MarketStatus.OPEN,
                )
            )
        return markets

    def _get_mock_orderbook(self) -> OrderBook:
        return OrderBook(
            yes_asks=[OrderBookLevel(price_cents=55, quantity=100)],
            yes_bids=[OrderBookLevel(price_cents=53, quantity=80)],
            no_asks=[OrderBookLevel(price_cents=47, quantity=90)],
            no_bids=[OrderBookLevel(price_cents=45, quantity=70)],
        )
