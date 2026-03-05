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
MIN_FUZZY_SCORE = 75.0


def find_matches(
    markets_by_platform: dict[Platform, list[NormalizedMarket]],
) -> list[MatchedMarket]:
    """Find matching markets across platforms.

    Strategy:
    1. Extract entities (asset, date, threshold, direction) from each market
    2. Exact match on (asset + date + threshold) for structured markets
    3. High fuzzy text similarity for unstructured markets (politics, entertainment)
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

    for market, entities in indexed:
        key = _entity_key(entities)
        if key:
            entity_groups.setdefault(key, []).append((market, entities))

    matches: list[MatchedMarket] = []

    # Phase 1: Exact entity matches
    for key, group in entity_groups.items():
        platforms_in_group: dict[Platform, NormalizedMarket] = {}
        for market, _ in group:
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

    # Phase 2: Fuzzy matching — only cross-platform pairs
    matched_ids = set()
    for m in matches:
        for market in m.markets.values():
            matched_ids.add((market.platform, market.platform_market_id))

    # Group remaining by platform for efficient cross-platform comparison
    by_platform: dict[Platform, list[tuple[NormalizedMarket, dict[str, Any]]]] = {}
    for market, entities in indexed:
        if (market.platform, market.platform_market_id) not in matched_ids:
            by_platform.setdefault(market.platform, []).append((market, entities))

    platform_list = list(by_platform.keys())

    # Compare each platform pair (not within same platform)
    for pi in range(len(platform_list)):
        for pj in range(pi + 1, len(platform_list)):
            plat_a = platform_list[pi]
            plat_b = platform_list[pj]
            group_a = by_platform[plat_a]
            group_b = by_platform[plat_b]

            # Use rapidfuzz batch extraction for speed: for each market in A,
            # find best match in B using cleaned titles
            from rapidfuzz import process as rfprocess

            # Build lookup for B
            b_titles = [_clean_for_comparison(m.title) for m, _ in group_b]
            b_lookup = list(range(len(group_b)))

            for idx_a, (market_a, ent_a) in enumerate(group_a):
                if (market_a.platform, market_a.platform_market_id) in matched_ids:
                    continue

                clean_a = _clean_for_comparison(market_a.title)
                # Use rapidfuzz extractBests for batch comparison
                results = rfprocess.extract(
                    clean_a, b_titles, scorer=fuzz.token_sort_ratio,
                    score_cutoff=MIN_FUZZY_SCORE - 5, limit=3,
                )

                for title_b, raw_score, idx_b in results:
                    market_b, ent_b = group_b[idx_b]
                    if (market_b.platform, market_b.platform_market_id) in matched_ids:
                        continue

                    # Re-score with full logic (handles entity matching, length guards)
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
                            a=market_a.title[:60],
                            b=market_b.title[:60],
                        )
                        break  # Market A matched, move to next

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
    """Compute similarity score between two markets.

    For structured markets (crypto prices): uses entity matching.
    For unstructured markets (politics, entertainment): uses text similarity.
    """
    has_asset_a = bool(ent_a.get("asset"))
    has_asset_b = bool(ent_b.get("asset"))

    # If both have assets, use structured matching
    if has_asset_a and has_asset_b:
        return _structured_score(market_a, ent_a, market_b, ent_b)

    # If one has an asset and the other doesn't, unlikely match
    if has_asset_a != has_asset_b:
        # Still allow if text similarity is very high
        text_score = _text_similarity(market_a.title, market_b.title)
        return text_score if text_score >= 85.0 else 0.0

    # Neither has an asset — use pure text similarity (politics, entertainment, etc.)
    return _text_similarity(market_a.title, market_b.title)


def _structured_score(
    market_a: NormalizedMarket,
    ent_a: dict[str, Any],
    market_b: NormalizedMarket,
    ent_b: dict[str, Any],
) -> float:
    """Score for structured markets (crypto, financial)."""
    score = 0.0

    if ent_a["asset"] != ent_b["asset"]:
        return 0.0  # Different assets = no match
    score += 40.0

    # Threshold match
    if ent_a["threshold"] is not None and ent_b["threshold"] is not None:
        if ent_a["threshold"] == ent_b["threshold"]:
            score += 30.0
        else:
            max_val = max(ent_a["threshold"], ent_b["threshold"])
            if max_val > 0:
                ratio = min(ent_a["threshold"], ent_b["threshold"]) / max_val
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

    # Text similarity bonus
    text_score = _text_similarity(market_a.title, market_b.title)
    score += text_score * 0.1

    return min(score, 100.0)


def _text_similarity(title_a: str, title_b: str) -> float:
    """Compute text similarity between two market titles."""
    clean_a = _clean_for_comparison(title_a)
    clean_b = _clean_for_comparison(title_b)

    # Use token_sort_ratio as primary (order-independent full comparison)
    sort_score = fuzz.token_sort_ratio(clean_a, clean_b)

    # token_set_ratio is too aggressive (subset matching) — only use if
    # lengths are similar (within 2x) to avoid "GTA VI" matching everything
    set_score = 0.0
    len_a, len_b = len(clean_a), len(clean_b)
    if len_a > 0 and len_b > 0:
        length_ratio = min(len_a, len_b) / max(len_a, len_b)
        if length_ratio > 0.4:
            set_score = fuzz.token_set_ratio(clean_a, clean_b) * length_ratio

    return max(sort_score, set_score)


def _clean_for_comparison(text: str) -> str:
    """Clean a market title for fuzzy comparison."""
    import re
    text = text.lower().strip()
    # Remove punctuation
    text = re.sub(r"[?!.,;:\"'()\[\]{}]", " ", text)
    # Remove common noise words
    noise = {
        "will", "be", "the", "on", "at", "or", "by", "end", "of",
        "close", "closing", "price", "market", "contract", "a", "an",
        "in", "to", "for", "and", "is", "are", "was", "were", "this",
        "that", "what", "which", "who", "whom", "when", "where", "how",
    }
    words = text.split()
    words = [w for w in words if w not in noise]
    return " ".join(words)
