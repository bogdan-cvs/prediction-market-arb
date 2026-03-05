from __future__ import annotations

from models.market import OrderBook, OrderBookLevel


def get_best_ask(orderbook: OrderBook, outcome: str) -> int | None:
    """Get the best (lowest) ask price for an outcome in cents."""
    if outcome.upper() == "YES":
        asks = orderbook.yes_asks
    else:
        asks = orderbook.no_asks

    if not asks:
        return None

    return min(a.price_cents for a in asks)


def get_best_bid(orderbook: OrderBook, outcome: str) -> int | None:
    """Get the best (highest) bid price for an outcome in cents."""
    if outcome.upper() == "YES":
        bids = orderbook.yes_bids
    else:
        bids = orderbook.no_bids

    if not bids:
        return None

    return max(b.price_cents for b in bids)


def get_available_quantity(
    orderbook: OrderBook, outcome: str, at_price_cents: int
) -> int:
    """Get total available quantity at or better than the given price.

    For asks: sum quantities where ask_price <= at_price_cents
    """
    if outcome.upper() == "YES":
        asks = orderbook.yes_asks
    else:
        asks = orderbook.no_asks

    total = 0
    for level in asks:
        if level.price_cents <= at_price_cents:
            total += level.quantity

    return total


def get_effective_price(
    orderbook: OrderBook, outcome: str, quantity: int
) -> int | None:
    """Get volume-weighted average price to fill `quantity` contracts.

    Returns price in cents, or None if insufficient liquidity.
    """
    if outcome.upper() == "YES":
        asks = sorted(orderbook.yes_asks, key=lambda x: x.price_cents)
    else:
        asks = sorted(orderbook.no_asks, key=lambda x: x.price_cents)

    remaining = quantity
    total_cost = 0

    for level in asks:
        fill = min(remaining, level.quantity)
        total_cost += fill * level.price_cents
        remaining -= fill
        if remaining <= 0:
            break

    if remaining > 0:
        return None  # Insufficient liquidity

    return total_cost // quantity  # Average price in cents


def assess_liquidity(
    orderbook: OrderBook, outcome: str, desired_qty: int
) -> dict:
    """Full liquidity assessment for a side of an orderbook."""
    best_ask = get_best_ask(orderbook, outcome)
    available = get_available_quantity(
        orderbook, outcome, best_ask
    ) if best_ask else 0
    effective_price = get_effective_price(orderbook, outcome, desired_qty)

    slippage_cents = 0
    if best_ask and effective_price:
        slippage_cents = effective_price - best_ask

    return {
        "best_ask_cents": best_ask,
        "available_at_best": available,
        "effective_price_cents": effective_price,
        "slippage_cents": slippage_cents,
        "sufficient_liquidity": effective_price is not None,
    }
