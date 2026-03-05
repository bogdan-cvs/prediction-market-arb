from __future__ import annotations

from fastapi import APIRouter

from api.dependencies import get_scanner

router = APIRouter(prefix="/api/arb", tags=["arbitrage"])


@router.get("/opportunities")
async def list_opportunities():
    """List current arbitrage opportunities."""
    scanner = get_scanner()
    opps = scanner.opportunities
    return {
        "opportunities": [o.model_dump() for o in opps],
        "count": len(opps),
    }


@router.post("/scan")
async def trigger_scan():
    """Trigger a single scan cycle."""
    scanner = get_scanner()
    opps = await scanner.scan_once()
    return {
        "opportunities": [o.model_dump() for o in opps],
        "count": len(opps),
    }


@router.get("/opportunities/{opportunity_id}")
async def get_opportunity(opportunity_id: str):
    """Get details for a specific opportunity."""
    scanner = get_scanner()
    for opp in scanner.opportunities:
        if opp.opportunity_id == opportunity_id:
            return opp.model_dump()
    return {"error": "Opportunity not found"}
