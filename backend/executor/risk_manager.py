from __future__ import annotations

import aiosqlite
import structlog

from config import settings
from database import DB_PATH

logger = structlog.get_logger()


class RiskManager:
    """Enforce position limits, max exposure, and daily loss limits."""

    def __init__(self) -> None:
        self.max_per_market = settings.max_exposure_per_market * 100  # cents
        self.max_total = settings.max_total_exposure * 100  # cents
        self.max_daily_loss = settings.max_daily_loss * 100  # cents
        self._killed = False

    async def check_allowed(
        self, market_id: str, cost_cents: int, quantity: int
    ) -> tuple[bool, str]:
        """Check if a trade is allowed under risk limits.

        Returns (allowed, reason).
        """
        if self._killed:
            return False, "Kill switch activated"

        total_cost = cost_cents * quantity

        # Check per-market exposure
        market_exposure = await self._get_market_exposure(market_id)
        if market_exposure + total_cost > self.max_per_market:
            return False, (
                f"Per-market limit exceeded: "
                f"${(market_exposure + total_cost) / 100:.2f} > "
                f"${self.max_per_market / 100:.2f}"
            )

        # Check total exposure
        total_exposure = await self._get_total_exposure()
        if total_exposure + total_cost > self.max_total:
            return False, (
                f"Total exposure limit exceeded: "
                f"${(total_exposure + total_cost) / 100:.2f} > "
                f"${self.max_total / 100:.2f}"
            )

        # Check daily loss
        daily_loss = await self._get_daily_loss()
        if daily_loss >= self.max_daily_loss:
            return False, (
                f"Daily loss limit reached: "
                f"${daily_loss / 100:.2f} >= ${self.max_daily_loss / 100:.2f}"
            )

        return True, "OK"

    async def _get_market_exposure(self, market_id: str) -> int:
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                """
                SELECT COALESCE(SUM(price_a_cents * quantity + price_b_cents * quantity), 0)
                FROM trade_history
                WHERE (match_id = ? OR opportunity_id LIKE ?)
                AND status IN ('filled', 'pending')
                AND date(executed_at) = date('now')
                """,
                (market_id, f"%{market_id}%"),
            )
            row = await cursor.fetchone()
            return row[0] if row else 0

    async def _get_total_exposure(self) -> int:
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                """
                SELECT COALESCE(SUM(price_a_cents * quantity + price_b_cents * quantity), 0)
                FROM trade_history
                WHERE status IN ('filled', 'pending')
                AND date(executed_at) = date('now')
                """
            )
            row = await cursor.fetchone()
            return row[0] if row else 0

    async def _get_daily_loss(self) -> int:
        """Get total realized losses for today (negative P&L)."""
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                """
                SELECT COALESCE(SUM(CASE WHEN net_profit_cents < 0 THEN ABS(net_profit_cents) ELSE 0 END), 0)
                FROM trade_history
                WHERE status = 'filled'
                AND date(executed_at) = date('now')
                """
            )
            row = await cursor.fetchone()
            return row[0] if row else 0

    def kill(self) -> None:
        """Emergency stop — block all new trades."""
        self._killed = True
        logger.warning("risk_manager_kill_switch_activated")

    def resume(self) -> None:
        self._killed = False
        logger.info("risk_manager_resumed")

    @property
    def is_killed(self) -> bool:
        return self._killed
