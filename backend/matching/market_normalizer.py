from __future__ import annotations

import re
from datetime import datetime
from typing import Any

import structlog

logger = structlog.get_logger()

# Common asset aliases
ASSET_ALIASES: dict[str, str] = {
    "bitcoin": "BTC",
    "btc": "BTC",
    "xbt": "BTC",
    "ethereum": "ETH",
    "eth": "ETH",
    "ether": "ETH",
    "solana": "SOL",
    "sol": "SOL",
    "spy": "SPY",
    "s&p": "SPY",
    "s&p 500": "SPY",
    "sp500": "SPY",
    "nasdaq": "QQQ",
    "qqq": "QQQ",
    "gold": "GOLD",
    "xau": "GOLD",
    "trump": "TRUMP",
    "biden": "BIDEN",
    "fed": "FED",
}

# Month mappings
MONTH_MAP: dict[str, int] = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}


def extract_entities(text: str) -> dict[str, Any]:
    """Extract key entities from a market title/ticker for matching.

    Returns dict with: asset, threshold, direction, date, clean_text
    """
    result: dict[str, Any] = {
        "asset": "",
        "threshold": None,
        "direction": "",
        "date": None,
        "clean_text": "",
    }

    if not text:
        return result

    text_lower = text.lower().strip()
    text_clean = text_lower

    # Extract asset
    result["asset"] = _extract_asset(text_lower)

    # Extract threshold (price level)
    result["threshold"] = _extract_threshold(text_lower)

    # Extract direction
    result["direction"] = _extract_direction(text_lower)

    # Extract date
    result["date"] = _extract_date(text)

    # Clean text for fuzzy comparison
    result["clean_text"] = _clean_text(text_lower)

    return result


def _extract_asset(text: str) -> str:
    """Extract asset identifier from text."""
    # Try ticker-style patterns first: KXBTC, FXBTC, etc.
    ticker_match = re.search(r"(?:KX|FX|PX|LX)?([A-Z]{2,5})", text.upper())

    # Check known aliases
    for alias, canonical in sorted(ASSET_ALIASES.items(), key=lambda x: -len(x[0])):
        if alias in text:
            return canonical

    # Try to find standalone tickers
    token_match = re.search(r"\b(BTC|ETH|SOL|SPY|QQQ|XRP|DOGE|ADA|DOT|AVAX)\b", text.upper())
    if token_match:
        return token_match.group(1)

    return ""


def _extract_threshold(text: str) -> float | None:
    """Extract price threshold from text."""
    # Patterns: $99,500 / $99500 / 99,500 / 99500 / $4,000 / 100K / 100k
    patterns = [
        r"\$?([\d,]+(?:\.\d+)?)\s*(?:k|K)",  # 100K
        r"\$\s*([\d,]+(?:\.\d+)?)",  # $99,500
        r"(?:above|below|over|under|at)\s+\$?([\d,]+(?:\.\d+)?)",  # above 99500
    ]

    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            val_str = match.group(1).replace(",", "")
            try:
                val = float(val_str)
                # Handle K suffix
                if "k" in text[match.start():match.end()].lower():
                    val *= 1000
                return val
            except ValueError:
                continue

    return None


def _extract_direction(text: str) -> str:
    """Extract direction (above/below) from text."""
    above_words = ["above", "over", "higher", "exceed", ">=", ">", "at or above"]
    below_words = ["below", "under", "lower", "less than", "<=", "<", "at or below"]

    for w in above_words:
        if w in text:
            return "above"

    for w in below_words:
        if w in text:
            return "below"

    return ""


def _extract_date(text: str) -> datetime | None:
    """Extract resolution date from text."""
    text_lower = text.lower()

    # Pattern: Mar 14, March 14, Mar14, 14 Mar
    for month_name, month_num in MONTH_MAP.items():
        # "Mar 14" or "March 14"
        match = re.search(
            rf"\b{month_name}\s*(\d{{1,2}})\b", text_lower
        )
        if match:
            day = int(match.group(1))
            return _make_date(month_num, day)

        # "14 Mar" or "14 March"
        match = re.search(
            rf"\b(\d{{1,2}})\s*{month_name}\b", text_lower
        )
        if match:
            day = int(match.group(1))
            return _make_date(month_num, day)

    # Ticker-style dates: 26MAR14, MAR26
    match = re.search(r"(\d{2})(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)(\d{2})", text.upper())
    if match:
        year_or_day = int(match.group(1))
        month_str = match.group(2).lower()
        day_or_year = int(match.group(3))
        month_num = MONTH_MAP.get(month_str, 0)
        if month_num:
            # Determine which is year and which is day
            if year_or_day > 12:  # likely day
                return _make_date(month_num, year_or_day)
            else:
                return _make_date(month_num, day_or_year)

    # Pattern: MAR14, MAR26
    match = re.search(r"(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)(\d{1,2})\b", text.upper())
    if match:
        month_str = match.group(1).lower()
        day = int(match.group(2))
        month_num = MONTH_MAP.get(month_str, 0)
        if month_num and 1 <= day <= 31:
            return _make_date(month_num, day)

    return None


def _make_date(month: int, day: int) -> datetime | None:
    """Create a datetime for the given month/day in the current or next year."""
    now = datetime.utcnow()
    try:
        dt = datetime(now.year, month, day)
        if dt < now:
            dt = datetime(now.year + 1, month, day)
        return dt
    except ValueError:
        return None


def _clean_text(text: str) -> str:
    """Clean text for fuzzy comparison."""
    # Remove common noise words and punctuation
    text = re.sub(r"[?!.,;:\"'()\[\]{}]", " ", text)
    noise = [
        "will", "be", "the", "on", "at", "or", "by", "end", "of",
        "close", "closing", "price", "market", "contract",
    ]
    words = text.split()
    words = [w for w in words if w not in noise]
    return " ".join(words)
