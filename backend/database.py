from __future__ import annotations

import aiosqlite
import structlog

from config import settings

logger = structlog.get_logger()

DB_PATH = settings.db_path

SCHEMA = """
CREATE TABLE IF NOT EXISTS match_cache (
    match_id TEXT PRIMARY KEY,
    kalshi_ticker TEXT,
    polymarket_market_id TEXT,
    limitless_market_id TEXT,
    ibkr_con_id TEXT,
    match_score REAL DEFAULT 1.0,
    verified INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    last_seen TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS trade_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    opportunity_id TEXT NOT NULL,
    match_id TEXT,
    platform_a TEXT NOT NULL,
    platform_b TEXT NOT NULL,
    side_a TEXT NOT NULL,
    side_b TEXT NOT NULL,
    price_a_cents INTEGER NOT NULL,
    price_b_cents INTEGER NOT NULL,
    quantity INTEGER NOT NULL,
    gross_profit_cents INTEGER NOT NULL,
    fees_cents INTEGER NOT NULL,
    net_profit_cents INTEGER NOT NULL,
    dry_run INTEGER DEFAULT 1,
    status TEXT DEFAULT 'pending',
    order_a_id TEXT,
    order_b_id TEXT,
    error_message TEXT,
    executed_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS daily_pnl (
    date TEXT PRIMARY KEY,
    realized_pnl_cents INTEGER DEFAULT 0,
    trade_count INTEGER DEFAULT 0,
    opportunities_detected INTEGER DEFAULT 0,
    opportunities_executed INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_trade_history_date ON trade_history(executed_at);
CREATE INDEX IF NOT EXISTS idx_trade_history_status ON trade_history(status);
CREATE INDEX IF NOT EXISTS idx_match_cache_verified ON match_cache(verified);
"""


async def init_db() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(SCHEMA)
        await db.commit()
    logger.info("database_initialized", path=DB_PATH)


async def get_db() -> aiosqlite.Connection:
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    return db
