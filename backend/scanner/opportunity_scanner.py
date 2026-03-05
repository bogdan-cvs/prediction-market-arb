from __future__ import annotations

import asyncio
import uuid
from itertools import combinations
from typing import Any

import structlog

from config import settings
from connectors.unified import UnifiedConnector
from matching.fuzzy_matcher import find_matches
from matching.match_cache import MatchCache
from models.market import MatchedMarket, NormalizedMarket, OrderBook, Platform
from models.opportunity import ArbLeg, ArbitrageOpportunity, OpportunityStatus
from scanner.fee_calculator import total_fees_for_arb
from scanner.liquidity_checker import get_best_ask, get_available_quantity

logger = structlog.get_logger()


class OpportunityScanner:
    """Core arbitrage scanner that detects profitable opportunities."""

    def __init__(self, connector: UnifiedConnector) -> None:
        self.connector = connector
        self.match_cache = MatchCache()
        self.active_matches: list[MatchedMarket] = []
        self.opportunities: list[ArbitrageOpportunity] = []
        self._running = False

    async def refresh_matches(self) -> list[MatchedMarket]:
        """Fetch markets from all platforms and find cross-platform matches."""
        markets_by_platform = await self.connector.get_all_markets()

        if not any(markets_by_platform.values()):
            logger.warning("no_markets_fetched")
            return []

        self.active_matches = find_matches(markets_by_platform)

        # Save to cache
        for match in self.active_matches:
            await self.match_cache.save_match(match)

        logger.info(
            "matches_refreshed",
            match_count=len(self.active_matches),
            platforms={p.value: len(m) for p, m in markets_by_platform.items()},
        )
        return self.active_matches

    async def scan_once(self) -> list[ArbitrageOpportunity]:
        """Run a single scan cycle across all matched markets."""
        opportunities: list[ArbitrageOpportunity] = []

        for match in self.active_matches:
            match_opps = await self._scan_match(match)
            opportunities.extend(match_opps)

        # Sort by net profit descending
        opportunities.sort(key=lambda o: o.net_profit_cents, reverse=True)
        self.opportunities = opportunities

        if opportunities:
            logger.info(
                "opportunities_found",
                count=len(opportunities),
                best_profit_cents=opportunities[0].net_profit_cents if opportunities else 0,
            )

        return opportunities

    async def _scan_match(self, match: MatchedMarket) -> list[ArbitrageOpportunity]:
        """Check all platform pairs within a matched market for arb."""
        opps: list[ArbitrageOpportunity] = []
        platforms = list(match.markets.keys())

        if len(platforms) < 2:
            return opps

        # Fetch orderbooks concurrently for all platforms in this match
        orderbooks: dict[Platform, OrderBook] = {}
        tasks = []
        for platform in platforms:
            market = match.markets[platform]
            tasks.append(self._fetch_orderbook(platform, market.platform_market_id))

        results = await asyncio.gather(*tasks)
        for platform, ob in zip(platforms, results):
            orderbooks[platform] = ob

        # Check all pairs: buy YES on A + buy NO on B
        for plat_a, plat_b in combinations(platforms, 2):
            market_a = match.markets[plat_a]
            market_b = match.markets[plat_b]
            ob_a = orderbooks[plat_a]
            ob_b = orderbooks[plat_b]

            # Direction 1: YES on A + NO on B
            opp = self._evaluate_pair(
                match, plat_a, market_a, ob_a, "YES", plat_b, market_b, ob_b, "NO"
            )
            if opp:
                opps.append(opp)

            # Direction 2: NO on A + YES on B
            opp = self._evaluate_pair(
                match, plat_a, market_a, ob_a, "NO", plat_b, market_b, ob_b, "YES"
            )
            if opp:
                opps.append(opp)

        return opps

    def _evaluate_pair(
        self,
        match: MatchedMarket,
        plat_a: Platform,
        market_a: NormalizedMarket,
        ob_a: OrderBook,
        side_a: str,
        plat_b: Platform,
        market_b: NormalizedMarket,
        ob_b: OrderBook,
        side_b: str,
    ) -> ArbitrageOpportunity | None:
        """Evaluate a specific YES/NO pair across two platforms."""
        price_a = get_best_ask(ob_a, side_a)
        price_b = get_best_ask(ob_b, side_b)

        # Fallback to market-level prices if orderbook empty
        if price_a is None:
            price_a = (
                market_a.yes_ask_cents if side_a == "YES" else market_a.no_ask_cents
            )
        if price_b is None:
            price_b = (
                market_b.yes_ask_cents if side_b == "YES" else market_b.no_ask_cents
            )

        if price_a is None or price_b is None:
            return None

        total_cost = price_a + price_b
        if total_cost >= 100:
            return None  # No arbitrage

        gross_profit = 100 - total_cost

        # Calculate fees
        qty = settings.min_quantity
        fees_total = total_fees_for_arb(plat_a, price_a, plat_b, price_b, qty)
        fees_per_contract = fees_total // qty if qty > 0 else 0

        net_profit = gross_profit - fees_per_contract
        if net_profit < settings.min_profit_cents:
            return None

        # Check liquidity
        avail_a = get_available_quantity(ob_a, side_a, price_a)
        avail_b = get_available_quantity(ob_b, side_b, price_b)

        # If orderbook was empty, use a default
        if avail_a == 0:
            avail_a = 50
        if avail_b == 0:
            avail_b = 50

        max_qty = min(avail_a, avail_b)
        if max_qty < settings.min_quantity:
            return None

        # Use first market's title for display
        title = market_a.title or market_b.title

        return ArbitrageOpportunity(
            opportunity_id=str(uuid.uuid4())[:12],
            match_id=match.match_id,
            market_title=title,
            leg_a=ArbLeg(
                platform=plat_a,
                market_id=market_a.platform_market_id,
                side=side_a,
                price_cents=price_a,
                available_qty=avail_a,
            ),
            leg_b=ArbLeg(
                platform=plat_b,
                market_id=market_b.platform_market_id,
                side=side_b,
                price_cents=price_b,
                available_qty=avail_b,
            ),
            total_cost_cents=total_cost,
            gross_profit_cents=gross_profit,
            fees_cents=fees_per_contract,
            net_profit_cents=net_profit,
            net_profit_pct=round(net_profit / total_cost * 100, 2) if total_cost > 0 else 0,
            max_quantity=max_qty,
            max_profit_dollars=round(net_profit * max_qty / 100, 2),
        )

    async def _fetch_orderbook(self, platform: Platform, market_id: str) -> OrderBook:
        try:
            return await self.connector.get_orderbook(platform, market_id)
        except Exception as e:
            logger.warning(
                "orderbook_fetch_failed",
                platform=platform.value,
                market=market_id,
                error=str(e),
            )
            return OrderBook()

    async def run_continuous(self, callback=None) -> None:
        """Run continuous scanning loop."""
        self._running = True
        logger.info("scanner_started", interval=settings.scan_interval_seconds)

        # Initial match refresh
        await self.refresh_matches()

        scan_count = 0
        while self._running:
            try:
                opps = await self.scan_once()
                scan_count += 1

                if callback and opps:
                    await callback(opps)

                # Refresh matches every 50 scans
                if scan_count % 50 == 0:
                    await self.refresh_matches()

                await asyncio.sleep(settings.scan_interval_seconds)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("scan_error", error=str(e))
                await asyncio.sleep(settings.scan_interval_seconds)

        logger.info("scanner_stopped")

    def stop(self) -> None:
        self._running = False
