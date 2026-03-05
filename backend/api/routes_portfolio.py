from __future__ import annotations

from fastapi import APIRouter

from api.dependencies import get_connector
from models.market import Platform
from models.portfolio import PlatformBalance, PortfolioSummary

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


@router.get("/balances")
async def get_balances():
    """Get balances across all platforms."""
    connector = get_connector()
    balances = await connector.get_all_balances()
    result = []
    for platform, cents in balances.items():
        result.append(
            PlatformBalance(
                platform=platform,
                available_cents=cents,
                total_cents=cents,
            ).model_dump()
        )
    return {"balances": result}


@router.get("/positions")
async def get_positions():
    """Get open positions across all platforms."""
    connector = get_connector()
    all_positions = []
    for platform, conn in connector.connectors.items():
        if conn.is_connected():
            try:
                positions = await conn.get_positions()
                for p in positions:
                    p["platform"] = platform.value
                    all_positions.append(p)
            except Exception:
                pass
    return {"positions": all_positions}


@router.get("/summary")
async def portfolio_summary():
    """Get full portfolio summary."""
    connector = get_connector()
    balances = await connector.get_all_balances()

    import aiosqlite
    from database import DB_PATH

    # Get daily PnL from trade history
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            SELECT
                COALESCE(SUM(net_profit_cents), 0) as total_pnl,
                COUNT(*) as trade_count
            FROM trade_history
            WHERE status = 'filled'
            AND date(executed_at) = date('now')
            """
        )
        row = await cursor.fetchone()
        daily_pnl = row[0] if row else 0
        trade_count = row[1] if row else 0

    total_balance = sum(balances.values())

    return PortfolioSummary(
        balances=[
            PlatformBalance(
                platform=p,
                available_cents=c,
                total_cents=c,
            )
            for p, c in balances.items()
        ],
        total_balance_cents=total_balance,
        daily_pnl_cents=daily_pnl,
        trade_count_today=trade_count,
    ).model_dump()
