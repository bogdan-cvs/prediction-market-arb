from __future__ import annotations

import uuid
from datetime import datetime
from itertools import combinations
from typing import Any

import structlog
from rapidfuzz import fuzz

from matching.market_normalizer import extract_entities
from models.market import MatchedMarket, NormalizedMarket, Platform

logger = structlog.get_logger()

# Minimum similarity score (0-100) for fuzzy match fallback
MIN_FUZZY_SCORE = 85.0


def find_matches(
    markets_by_platform: dict[Platform, list[NormalizedMarket]],
) -> list[MatchedMarket]:
    """Find matching markets across platforms.

    Strategy:
    1. Extract entities (asset, date, threshold, direction) from each market
    2. Exact match on (asset + date + threshold)
    3. Fallback: fuzzy string similarity on cleaned titles
    """
    # Build entity index per market
    indexed: list[tuple[NormalizedMarket, dict[str, Any]]] = []
    for platform, markets in markets_by_platform.items():
        for market in markets:
            entities = extract_entities(market.title)
            # Also try ticker
            if not entities["asset"] and market.ticker:
                ticker_entities = extract_entities(market.ticker)
                if ticker_entities["asset"]:
                    entities["asset"] = ticker_entities["asset"]
                if not entities["date"] and ticker_entities["date"]:
                    entities["date"] = ticker_entities["date"]
                if not entities["threshold"] and ticker_entities["threshold"]:
                    entities["threshold"] = ticker_entities["threshold"]

            indexed.append((market, entities))

    # Group by entity key for exact matching
    entity_groups: dict[str, list[tuple[NormalizedMarket, dict[str, Any]]]] = {}
    unmatched: list[tuple[NormalizedMarket, dict[str, Any]]] = []

    for market, entities in indexed:
        key = _entity_key(entities)
        if key:
            entity_groups.setdefault(key, []).append((market, entities))
        else:
            unmatched.append((market, entities))

    matches: list[MatchedMarket] = []

    # Phase 1: Exact entity matches
    for key, group in entity_groups.items():
        platforms_in_group: dict[Platform, NormalizedMarket] = {}
        for market, _ in group:
            # Take the first market per platform in the group
            if market.platform not in platforms_in_group:
                platforms_in_group[market.platform] = market

        if len(platforms_in_group) >= 2:
            match = MatchedMarket(
                match_id=str(uuid.uuid4())[:12],
                markets=platforms_in_group,
                match_score=1.0,
                verified=False,
            )
            matches.append(match)
            logger.debug(
                "exact_match_found",
                key=key,
                platforms=[p.value for p in platforms_in_group],
            )

    # Phase 2: Fuzzy matching for unmatched markets
    # Also try fuzzy between different entity groups
    matched_ids = set()
    for m in matches:
        for market in m.markets.values():
            matched_ids.add((market.platform, market.platform_market_id))

    remaining: list[tuple[NormalizedMarket, dict[str, Any]]] = []
    for market, entities in indexed:
        if (market.platform, market.platform_market_id) not in matched_ids:
            remaining.append((market, entities))

    # Cross-platform fuzzy matching on remaining
    for i, (market_a, ent_a) in enumerate(remaining):
        for j, (market_b, ent_b) in enumerate(remaining):
            if j <= i:
                continue
            if market_a.platform == market_b.platform:
                continue
            if (market_a.platform, market_a.platform_market_id) in matched_ids:
                continue
            if (market_b.platform, market_b.platform_market_id) in matched_ids:
                continue

            score = _fuzzy_score(market_a, ent_a, market_b, ent_b)
            if score >= MIN_FUZZY_SCORE:
                match = MatchedMarket(
                    match_id=str(uuid.uuid4())[:12],
                    markets={
                        market_a.platform: market_a,
                        market_b.platform: market_b,
                    },
                    match_score=score / 100.0,
                    verified=False,
                )
                matches.append(match)
                matched_ids.add((market_a.platform, market_a.platform_market_id))
                matched_ids.add((market_b.platform, market_b.platform_market_id))
                logger.debug(
                    "fuzzy_match_found",
                    score=score,
                    a=market_a.title[:50],
                    b=market_b.title[:50],
                )

    logger.info("matching_complete", total_matches=len(matches))
    return matches


def _entity_key(entities: dict[str, Any]) -> str:
    """Create a match key from extracted entities."""
    asset = entities.get("asset", "")
    threshold = entities.get("threshold")
    date = entities.get("date")

    if not asset:
        return ""

    parts = [asset]
    if threshold is not None:
        parts.append(str(int(threshold)))
    if date is not None:
        parts.append(date.strftime("%Y%m%d"))

    # Need at least asset + one more component to make a useful key
    if len(parts) < 2:
        return ""

    return "|".join(parts)


def _fuzzy_score(
    market_a: NormalizedMarket,
    ent_a: dict[str, Any],
    market_b: NormalizedMarket,
    ent_b: dict[str, Any],
) -> float:
    """Compute similarity score between two markets."""
    score = 0.0

    # Asset match is weighted heavily
    if ent_a["asset"] and ent_b["asset"]:
        if ent_a["asset"] == ent_b["asset"]:
            score += 40.0
        else:
            return 0.0  # Different assets = no match

    # Threshold match
    if ent_a["threshold"] is not None and ent_b["threshold"] is not None:
        if ent_a["threshold"] == ent_b["threshold"]:
            score += 30.0
        else:
            # Close enough? Within 1%
            ratio = min(ent_a["threshold"], ent_b["threshold"]) / max(
                ent_a["threshold"], ent_b["threshold"]
            )
            if ratio > 0.99:
                score += 20.0
            else:
                return score  # Different thresholds

    # Date match
    if ent_a["date"] and ent_b["date"]:
        if ent_a["date"].date() == ent_b["date"].date():
            score += 20.0
        else:
            return score  # Different dates

    # Direction match
    if ent_a["direction"] and ent_b["direction"]:
        if ent_a["direction"] == ent_b["direction"]:
            score += 10.0

    # Fuzzy text similarity as tiebreaker
    text_score = fuzz.token_sort_ratio(
        ent_a.get("clean_text", market_a.title),
        ent_b.get("clean_text", market_b.title),
    )
    score += text_score * 0.1  # Weight text similarity lower

    return min(score, 100.0)
