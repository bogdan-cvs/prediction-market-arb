from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.dependencies import get_scanner, get_executor
from config import settings

router = APIRouter(prefix="/api/execution", tags=["execution"])


class ExecuteRequest(BaseModel):
    opportunity_id: str
    quantity: int | None = None
    override_dry_run: bool = False


@router.post("/execute")
async def execute_opportunity(req: ExecuteRequest):
    """Execute an arbitrage opportunity."""
    scanner = get_scanner()
    executor = get_executor()

    # Find the opportunity
    opp = None
    for o in scanner.opportunities:
        if o.opportunity_id == req.opportunity_id:
            opp = o
            break

    if not opp:
        raise HTTPException(404, "Opportunity not found or expired")

    qty = req.quantity or opp.max_quantity
    dry_run = settings.dry_run and not req.override_dry_run

    result = await executor.execute(opp, qty, dry_run=dry_run)
    return result.model_dump()


@router.get("/history")
async def trade_history(limit: int = 50):
    """Get trade execution history."""
    import aiosqlite
    from database import DB_PATH

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM trade_history ORDER BY executed_at DESC LIMIT ?",
            (limit,),
        )
        rows = await cursor.fetchall()
        return {"trades": [dict(row) for row in rows], "count": len(rows)}


@router.get("/mode")
async def get_mode():
    """Get current execution mode."""
    return {"dry_run": settings.dry_run}


@router.post("/mode")
async def set_mode(dry_run: bool = True):
    """Toggle dry run mode."""
    settings.dry_run = dry_run
    return {"dry_run": settings.dry_run}
