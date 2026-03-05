from __future__ import annotations

from fastapi import APIRouter, Query

from api.dependencies import get_connector
from models.market import Platform

router = APIRouter(prefix="/api/markets", tags=["markets"])


@router.get("")
async def list_markets(
    platform: Platform | None = None,
    query: str = Query("", description="Search query"),
    limit: int = Query(100, ge=1, le=500),
):
    """List markets from all or a specific platform."""
    connector = get_connector()

    if platform:
        c = connector.get_connector(platform)
        if not c.is_connected():
            return {"markets": [], "error": f"{platform.value} not connected"}
        markets = await c.get_markets(query, limit)
        return {"markets": [m.model_dump() for m in markets]}

    all_markets = await connector.get_all_markets(query, limit)
    flat = []
    for plat, markets in all_markets.items():
        for m in markets:
            flat.append(m.model_dump())

    return {"markets": flat, "count": len(flat)}


@router.get("/{platform}/{market_id}/orderbook")
async def get_orderbook(platform: Platform, market_id: str):
    """Get orderbook for a specific market."""
    connector = get_connector()
    ob = await connector.get_orderbook(platform, market_id)
    return ob.model_dump()


@router.get("/matches")
async def list_matches():
    """List all cross-platform matched markets."""
    from api.dependencies import get_scanner

    scanner = get_scanner()
    matches = scanner.active_matches
    return {
        "matches": [
            {
                "match_id": m.match_id,
                "platforms": {
                    p.value: {
                        "market_id": mk.platform_market_id,
                        "title": mk.title,
                        "yes_ask": mk.yes_ask_cents,
                        "no_ask": mk.no_ask_cents,
                    }
                    for p, mk in m.markets.items()
                },
                "match_score": m.match_score,
                "verified": m.verified,
            }
            for m in matches
        ],
        "count": len(matches),
    }


@router.post("/matches/refresh")
async def refresh_matches():
    """Force refresh of cross-platform market matches."""
    from api.dependencies import get_scanner

    scanner = get_scanner()
    matches = await scanner.refresh_matches()
    return {"matches_found": len(matches)}


@router.post("/matches/{match_id}/verify")
async def verify_match(match_id: str, verified: bool = True):
    """Manually verify or reject a market match."""
    from matching.match_cache import MatchCache

    cache = MatchCache()
    ok = await cache.verify_match(match_id, verified)
    return {"success": ok, "match_id": match_id, "verified": verified}
