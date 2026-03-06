from __future__ import annotations

import re
import time
import uuid
from collections import defaultdict

import structlog
from sklearn.feature_extraction.text import TfidfVectorizer
from sparse_dot_topn import sp_matmul_topn

from models.market import MatchedMarket, NormalizedMarket, Platform

logger = structlog.get_logger()

# TF-IDF threshold: 0.85 = titles must be nearly identical
MIN_TFIDF_SIMILARITY = 0.85

# Stop words to remove for normalized exact matching
_STOP_WORDS = frozenset({
    "will", "be", "the", "a", "an", "in", "on", "at", "to", "of", "for",
    "by", "is", "are", "was", "were", "do", "does", "did", "has", "have",
    "before", "after", "during", "from", "than", "or", "and",
})


def find_matches(
    markets_by_platform: dict[Platform, list[NormalizedMarket]],
) -> list[MatchedMarket]:
    """Find matching markets across platforms.

    Layer 1: Exact match on normalized titles (instant, 100% correct).
    Layer 2: TF-IDF cosine similarity at threshold 0.85 (fast, high precision).
    """
    matches: list[MatchedMarket] = []
    matched_ids: set[tuple[str, str]] = set()

    by_platform: dict[Platform, list[NormalizedMarket]] = {}
    for platform, markets in markets_by_platform.items():
        by_platform[platform] = markets

    platform_list = list(by_platform.keys())
    for pi in range(len(platform_list)):
        for pj in range(pi + 1, len(platform_list)):
            plat_a, plat_b = platform_list[pi], platform_list[pj]
            group_a = by_platform[plat_a]
            group_b = by_platform[plat_b]

            # Layer 1: exact normalized title match
            exact = _exact_match(group_a, group_b, matched_ids)
            matches.extend(exact)
            for m in exact:
                for market in m.markets.values():
                    matched_ids.add((market.platform.value, market.platform_market_id))

            # Layer 2: TF-IDF fuzzy match on remaining
            fuzzy = _tfidf_match(group_a, group_b, matched_ids)
            matches.extend(fuzzy)
            for m in fuzzy:
                for market in m.markets.values():
                    matched_ids.add((market.platform.value, market.platform_market_id))

    logger.info("matching_complete", total_matches=len(matches))
    return matches


def _normalize_title(text: str) -> str:
    """Normalize a title for exact matching: lowercase, strip punctuation,
    remove stop words, collapse whitespace."""
    text = text.lower().strip()
    text = re.sub(r"[?!.,;:\"'()\[\]{}\-/]", " ", text)
    words = text.split()
    words = [w for w in words if w not in _STOP_WORDS]
    return " ".join(words)


def _exact_match(
    group_a: list[NormalizedMarket],
    group_b: list[NormalizedMarket],
    matched_ids: set[tuple[str, str]],
) -> list[MatchedMarket]:
    """Layer 1: exact match on normalized titles."""
    if not group_a or not group_b:
        return []

    t0 = time.monotonic()

    # Build index for group_b
    b_index: dict[str, list[NormalizedMarket]] = defaultdict(list)
    for m in group_b:
        key = (m.platform.value, m.platform_market_id)
        if key not in matched_ids:
            norm = _normalize_title(m.title)
            if norm:
                b_index[norm].append(m)

    matches: list[MatchedMarket] = []
    for market_a in group_a:
        key_a = (market_a.platform.value, market_a.platform_market_id)
        if key_a in matched_ids:
            continue

        norm_a = _normalize_title(market_a.title)
        if not norm_a or norm_a not in b_index:
            continue

        # Take first unmatched from b_index
        for market_b in b_index[norm_a]:
            key_b = (market_b.platform.value, market_b.platform_market_id)
            if key_b in matched_ids:
                continue

            matched_ids.add(key_a)
            matched_ids.add(key_b)
            matches.append(MatchedMarket(
                match_id=str(uuid.uuid4())[:12],
                markets={market_a.platform: market_a, market_b.platform: market_b},
                match_score=1.0,
                verified=True,
            ))
            break

    elapsed = round(time.monotonic() - t0, 2)
    logger.info("exact_match_done", matches=len(matches), sec=elapsed)
    return matches


def _tfidf_match(
    group_a: list[NormalizedMarket],
    group_b: list[NormalizedMarket],
    matched_ids: set[tuple[str, str]],
) -> list[MatchedMarket]:
    """Layer 2: TF-IDF cosine similarity matching at high threshold."""
    # Filter out already-matched markets
    filtered_a = [m for m in group_a
                  if (m.platform.value, m.platform_market_id) not in matched_ids]
    filtered_b = [m for m in group_b
                  if (m.platform.value, m.platform_market_id) not in matched_ids]

    if not filtered_a or not filtered_b:
        return []

    t0 = time.monotonic()
    logger.info("tfidf_match_start", group_a=len(filtered_a), group_b=len(filtered_b))

    titles_a = [_clean_for_tfidf(m.title) for m in filtered_a]
    titles_b = [_clean_for_tfidf(m.title) for m in filtered_b]

    vectorizer = TfidfVectorizer(
        analyzer="word",
        ngram_range=(1, 2),
        min_df=2,
        max_df=0.5,
        sublinear_tf=True,
    )
    all_titles = titles_a + titles_b
    tfidf_matrix = vectorizer.fit_transform(all_titles)

    matrix_a = tfidf_matrix[:len(titles_a)]
    matrix_b = tfidf_matrix[len(titles_a):]

    sim_sparse = sp_matmul_topn(
        matrix_a, matrix_b.T,
        top_n=3,
        threshold=MIN_TFIDF_SIMILARITY,
        sort=True,
    )

    t1 = time.monotonic()
    logger.info("tfidf_sparse_done", nnz=sim_sparse.nnz, sec=round(t1 - t0, 2))

    matches: list[MatchedMarket] = []
    used_b: set[int] = set()

    coo = sim_sparse.tocoo()
    row_matches: dict[int, list[tuple[int, float]]] = defaultdict(list)
    for r, c, v in zip(coo.row, coo.col, coo.data):
        row_matches[int(r)].append((int(c), float(v)))

    for idx_a in row_matches:
        row_matches[idx_a].sort(key=lambda x: -x[1])

    sorted_rows = sorted(row_matches.keys(), key=lambda i: -row_matches[i][0][1])

    for idx_a in sorted_rows:
        market_a = filtered_a[idx_a]
        if (market_a.platform.value, market_a.platform_market_id) in matched_ids:
            continue

        for idx_b, score in row_matches[idx_a]:
            if idx_b in used_b:
                continue
            market_b = filtered_b[idx_b]
            if (market_b.platform.value, market_b.platform_market_id) in matched_ids:
                continue

            used_b.add(idx_b)
            matched_ids.add((market_a.platform.value, market_a.platform_market_id))
            matched_ids.add((market_b.platform.value, market_b.platform_market_id))
            matches.append(MatchedMarket(
                match_id=str(uuid.uuid4())[:12],
                markets={market_a.platform: market_a, market_b.platform: market_b},
                match_score=min(score, 1.0),
                verified=False,
            ))
            break

    elapsed = round(time.monotonic() - t0, 2)
    logger.info("tfidf_match_done", matches=len(matches), sec=elapsed)
    return matches


def _clean_for_tfidf(text: str) -> str:
    """Clean a market title for TF-IDF vectorization."""
    text = text.lower().strip()
    text = re.sub(r"[?!.,;:\"'()\[\]{}]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()
