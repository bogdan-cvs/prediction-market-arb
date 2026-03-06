from __future__ import annotations

from models.market import Platform


def calculate_fee_cents(
    platform: Platform,
    price_cents: float,
    quantity: int,
    side: str = "YES",
) -> float:
    """Calculate estimated fee in cents for a trade.

    Returns total fee for the given quantity.
    """
    if platform == Platform.KALSHI:
        return _kalshi_fee(price_cents, quantity)
    elif platform == Platform.POLYMARKET:
        return _polymarket_fee(price_cents, quantity)
    elif platform == Platform.LIMITLESS:
        return _limitless_fee(price_cents, quantity)
    elif platform == Platform.IBKR:
        return _ibkr_fee(price_cents, quantity)
    return 0


def _kalshi_fee(price_cents: float, quantity: int) -> float:
    """Kalshi: ~7% of expected profit, capped at 8.5c/contract."""
    expected_profit = 100 - price_cents
    fee_per_contract = min(round(expected_profit * 0.07, 1), 8.5)
    return fee_per_contract * quantity


def _polymarket_fee(price_cents: float, quantity: int) -> float:
    """Polymarket: ~2% of winnings for takers."""
    expected_profit = 100 - price_cents
    fee_per_contract = round(expected_profit * 0.02, 1)
    return fee_per_contract * quantity


def _limitless_fee(price_cents: float, quantity: int) -> float:
    """Limitless: ~1.5% taker fee."""
    fee_per_contract = max(0.1, round(price_cents * 0.015, 1))
    return fee_per_contract * quantity


def _ibkr_fee(price_cents: float, quantity: int) -> float:
    """IBKR/ForecastEx: zero commission."""
    return 0


def total_fees_for_arb(
    platform_a: Platform,
    price_a_cents: float,
    platform_b: Platform,
    price_b_cents: float,
    quantity: int,
) -> float:
    """Total fees for an arbitrage pair trade."""
    fee_a = calculate_fee_cents(platform_a, price_a_cents, quantity)
    fee_b = calculate_fee_cents(platform_b, price_b_cents, quantity)
    return fee_a + fee_b
