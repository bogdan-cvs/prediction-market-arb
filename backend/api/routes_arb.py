from __future__ import annotations

import structlog
from fastapi import APIRouter

from api.dependencies import get_scanner

logger = structlog.get_logger()
router = APIRouter(prefix="/api/arb", tags=["arbitrage"])


@router.get("/opportunities")
async def list_opportunities():
    """List current arbitrage opportunities."""
    scanner = get_scanner()
    opps = scanner.opportunities
    logger.info("api_opportunities_request", raw_count=len(opps))
    try:
        result = [o.model_dump(mode="json") for o in opps]
        return {
            "opportunities": result,
            "count": len(result),
        }
    except Exception as e:
        logger.error("api_opportunities_error", error=str(e))
        return {
            "opportunities": [],
            "count": 0,
            "error": str(e),
        }


@router.post("/scan")
async def trigger_scan():
    """Trigger a single scan cycle."""
    scanner = get_scanner()
    try:
        opps = await scanner.scan_once()
        logger.info("api_scan_result", count=len(opps))
        return {
            "opportunities": [o.model_dump(mode="json") for o in opps],
            "count": len(opps),
        }
    except Exception as e:
        logger.error("api_scan_error", error=str(e))
        return {
            "opportunities": [],
            "count": 0,
            "error": str(e),
        }


@router.get("/opportunities/{opportunity_id}")
async def get_opportunity(opportunity_id: str):
    """Get details for a specific opportunity."""
    scanner = get_scanner()
    for opp in scanner.opportunities:
        if opp.opportunity_id == opportunity_id:
            return opp.model_dump(mode="json")
    return {"error": "Opportunity not found"}
