from __future__ import annotations

from datetime import datetime
from typing import Any

import aiosqlite
import structlog

from config import settings
from models.market import MatchedMarket, Platform

logger = structlog.get_logger()


class MatchCache:
    """SQLite-backed cache for verified market matches."""

    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = db_path or settings.db_path

    async def save_match(self, match: MatchedMarket) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            kalshi_id = ""
            poly_id = ""
            limitless_id = ""
            ibkr_id = ""

            for platform, market in match.markets.items():
                if platform == Platform.KALSHI:
                    kalshi_id = market.platform_market_id
                elif platform == Platform.POLYMARKET:
                    poly_id = market.platform_market_id
                elif platform == Platform.LIMITLESS:
                    limitless_id = market.platform_market_id
                elif platform == Platform.IBKR:
                    ibkr_id = market.platform_market_id

            await db.execute(
                """
                INSERT OR REPLACE INTO match_cache
                (match_id, kalshi_ticker, polymarket_market_id, limitless_market_id,
                 ibkr_con_id, match_score, verified, last_seen)
                VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
                """,
                (
                    match.match_id,
                    kalshi_id,
                    poly_id,
                    limitless_id,
                    ibkr_id,
                    match.match_score,
                    1 if match.verified else 0,
                ),
            )
            await db.commit()
            logger.debug("match_saved", match_id=match.match_id)

    async def get_verified_matches(self) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM match_cache WHERE verified = 1"
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_all_matches(self) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM match_cache ORDER BY last_seen DESC")
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def verify_match(self, match_id: str, verified: bool = True) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            result = await db.execute(
                "UPDATE match_cache SET verified = ? WHERE match_id = ?",
                (1 if verified else 0, match_id),
            )
            await db.commit()
            return result.rowcount > 0

    async def delete_match(self, match_id: str) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            result = await db.execute(
                "DELETE FROM match_cache WHERE match_id = ?", (match_id,)
            )
            await db.commit()
            return result.rowcount > 0

    async def find_by_platform_id(
        self, platform: Platform, market_id: str
    ) -> dict[str, Any] | None:
        column_map = {
            Platform.KALSHI: "kalshi_ticker",
            Platform.POLYMARKET: "polymarket_market_id",
            Platform.LIMITLESS: "limitless_market_id",
            Platform.IBKR: "ibkr_con_id",
        }
        column = column_map.get(platform)
        if not column:
            return None

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                f"SELECT * FROM match_cache WHERE {column} = ?", (market_id,)
            )
            row = await cursor.fetchone()
            return dict(row) if row else None
