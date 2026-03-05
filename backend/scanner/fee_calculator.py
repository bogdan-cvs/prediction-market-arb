from __future__ import annotations

from models.market import Platform


def calculate_fee_cents(
    platform: Platform,
    price_cents: int,
    quantity: int,
    side: str = "YES",
) -> int:
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


def _kalshi_fee(price_cents: int, quantity: int) -> int:
    """Kalshi: up to ~0.7% of expected profit per contract, capped at ~$0.085/contract.

    Fee applies to the expected earnings (winning - cost).
    Simplified: ~0.7 cents per contract on average for typical arb prices.
    Cap: 8.5 cents per contract (if really profitable).
    """
    # Expected profit per contract if this side wins
    expected_profit = 100 - price_cents  # cents
    # Fee rate ~7% of expected profit
    fee_per_contract = min(int(expected_profit * 0.07), 8)
    return fee_per_contract * quantity


def _polymarket_fee(price_cents: int, quantity: int) -> int:
    """Polymarket: 0% maker, ~2% of winnings for takers.

    For arb we're likely taking. Fee on expected earnings.
    """
    expected_profit = 100 - price_cents
    fee_per_contract = int(expected_profit * 0.02)
    return fee_per_contract * quantity


def _limitless_fee(price_cents: int, quantity: int) -> int:
    """Limitless: taker fee on orderbook trades.

    Estimated ~1-2% taker fee. Maker rebates available but we assume taker.
    """
    fee_per_contract = max(1, int(price_cents * 0.015))
    return fee_per_contract * quantity


def _ibkr_fee(price_cents: int, quantity: int) -> int:
    """IBKR/ForecastEx: zero commission.

    But the spread (YES + NO = $1.01) means there's an implicit cost.
    We don't count the spread as a fee here; it's reflected in the price.
    """
    return 0


def total_fees_for_arb(
    platform_a: Platform,
    price_a_cents: int,
    platform_b: Platform,
    price_b_cents: int,
    quantity: int,
) -> int:
    """Total fees for an arbitrage pair trade."""
    fee_a = calculate_fee_cents(platform_a, price_a_cents, quantity)
    fee_b = calculate_fee_cents(platform_b, price_b_cents, quantity)
    return fee_a + fee_b
