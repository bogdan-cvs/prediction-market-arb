from __future__ import annotations

import asyncio
import time
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
        self._ob_fail_cache: set[tuple[str, str]] = set()  # (platform, market_id) that 404

    async def refresh_matches(self) -> list[MatchedMarket]:
        """Fetch markets from all platforms and find cross-platform matches."""
        t0 = time.monotonic()
        self._ob_fail_cache.clear()  # Reset failed orderbooks on refresh
        markets_by_platform = await self.connector.get_all_markets()
        t_fetch = time.monotonic() - t0

        if not any(markets_by_platform.values()):
            logger.warning("no_markets_fetched")
            return []

        t1 = time.monotonic()
        self.active_matches = find_matches(markets_by_platform)
        t_match = time.monotonic() - t1

        # Save to cache in batch
        await self.match_cache.save_matches_batch(self.active_matches)

        logger.info(
            "matches_refreshed",
            match_count=len(self.active_matches),
            platforms={p.value: len(m) for p, m in markets_by_platform.items()},
            fetch_sec=round(t_fetch, 1),
            match_sec=round(t_match, 2),
        )
        return self.active_matches

    @staticmethod
    def _orderbook_id(market: NormalizedMarket) -> str:
        """Return the ID to use when fetching an orderbook.

        Polymarket CLOB API requires the YES token_id (stored in ticker),
        not the conditionId (stored in platform_market_id).
        """
        if market.platform == Platform.POLYMARKET and market.ticker:
            return market.ticker
        return market.platform_market_id

    async def scan_once(self) -> list[ArbitrageOpportunity]:
        """Run a single scan cycle across all matched markets."""
        t0 = time.monotonic()

        # Phase 1: sort matches by score (exact matches first), take top 500
        sorted_matches = sorted(self.active_matches, key=lambda m: m.match_score, reverse=True)
        top_matches = [m for m in sorted_matches if len(m.markets) >= 2][:500]

        # Phase 1b: collect unique orderbook IDs
        ob_keys: list[tuple[Platform, str]] = []
        seen_ob: set[tuple[str, str]] = set()
        for match in top_matches:
            for platform, market in match.markets.items():
                ob_id = self._orderbook_id(market)
                key = (platform.value, ob_id)
                if key not in seen_ob:
                    seen_ob.add(key)
                    ob_keys.append((platform, ob_id))

        logger.info("scan_phase1", total_matches=len(self.active_matches), scanning=len(top_matches), orderbooks_needed=len(ob_keys))

        # Phase 2: fetch orderbooks concurrently (semaphore = 10 to balance speed vs rate limits)
        sem = asyncio.Semaphore(10)

        async def _fetch_ob(plat: Platform, mid: str) -> tuple[str, str, OrderBook]:
            cache_key = (plat.value, mid)
            if cache_key in self._ob_fail_cache:
                return (plat.value, mid, OrderBook())
            async with sem:
                return (plat.value, mid, await self._fetch_orderbook(plat, mid))

        results = await asyncio.gather(*[_fetch_ob(p, m) for p, m in ob_keys])
        ob_map: dict[tuple[str, str], OrderBook] = {}
        for pval, mid, ob in results:
            ob_map[(pval, mid)] = ob

        # Phase 3: evaluate top matches using pre-fetched orderbooks
        opportunities: list[ArbitrageOpportunity] = []
        for match in top_matches:
            platforms = list(match.markets.keys())
            if len(platforms) < 2:
                continue
            for plat_a, plat_b in combinations(platforms, 2):
                market_a = match.markets[plat_a]
                market_b = match.markets[plat_b]
                ob_a = ob_map.get((plat_a.value, self._orderbook_id(market_a)), OrderBook())
                ob_b = ob_map.get((plat_b.value, self._orderbook_id(market_b)), OrderBook())

                for side_a, side_b in [("YES", "NO"), ("NO", "YES")]:
                    opp = self._evaluate_pair(
                        match, plat_a, market_a, ob_a, side_a, plat_b, market_b, ob_b, side_b
                    )
                    if opp:
                        opportunities.append(opp)

        opportunities.sort(key=lambda o: o.net_profit_cents, reverse=True)
        self.opportunities = opportunities

        elapsed = round(time.monotonic() - t0, 2)
        skipped = len([k for k in ob_keys if (k[0].value, k[1]) in self._ob_fail_cache])
        if opportunities:
            logger.info(
                "scan_complete",
                count=len(opportunities),
                best_profit_cents=opportunities[0].net_profit_cents,
                elapsed_sec=elapsed,
                orderbooks_fetched=len(ob_keys) - skipped,
                orderbooks_cached_skip=skipped,
            )
        else:
            logger.info("scan_complete", count=0, elapsed_sec=elapsed)

        return opportunities

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

        # Prices must be valid (0.1-99.9 cents range)
        if price_a < 0.1 or price_a > 99.9 or price_b < 0.1 or price_b > 99.9:
            return None

        total_cost = round(price_a + price_b, 1)
        if total_cost >= 100:
            return None  # No arbitrage

        gross_profit = round(100 - total_cost, 1)

        # Calculate fees
        qty = settings.min_quantity
        fees_total = total_fees_for_arb(plat_a, price_a, plat_b, price_b, qty)
        fees_per_contract = round(fees_total / qty, 1) if qty > 0 else 0

        net_profit = round(gross_profit - fees_per_contract, 1)
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
            ob = await self.connector.get_orderbook(platform, market_id)
            return ob
        except Exception as e:
            err_str = str(e)
            if "404" in err_str or "Not Found" in err_str:
                self._ob_fail_cache.add((platform.value, market_id))
                logger.debug("orderbook_cached_as_failed", platform=platform.value, market=market_id)
            else:
                logger.warning("orderbook_fetch_failed", platform=platform.value, market=market_id, error=err_str)
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
