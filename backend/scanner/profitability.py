from __future__ import annotations

from models.market import Platform
from scanner.fee_calculator import total_fees_for_arb


def calculate_net_profit(
    platform_a: Platform,
    price_a_cents: int,
    platform_b: Platform,
    price_b_cents: int,
    quantity: int,
    slippage_cents: int = 0,
) -> dict:
    """Calculate detailed profitability for an arb opportunity.

    Buying YES on platform_a at price_a + NO on platform_b at price_b.
    Guaranteed payout = $1.00 (100 cents) regardless of outcome.
    """
    total_cost_cents = price_a_cents + price_b_cents + slippage_cents
    gross_profit_cents = 100 - total_cost_cents

    if gross_profit_cents <= 0:
        return {
            "total_cost_cents": total_cost_cents,
            "gross_profit_cents": gross_profit_cents,
            "fees_cents": 0,
            "net_profit_cents": gross_profit_cents,
            "net_profit_pct": 0.0,
            "max_profit_dollars": 0.0,
            "profitable": False,
        }

    fees = total_fees_for_arb(
        platform_a, price_a_cents,
        platform_b, price_b_cents,
        quantity,
    )
    fees_per_contract = fees // quantity if quantity > 0 else 0

    net_profit_cents = gross_profit_cents - fees_per_contract
    net_profit_pct = (net_profit_cents / total_cost_cents * 100) if total_cost_cents > 0 else 0
    max_profit_dollars = net_profit_cents * quantity / 100.0

    return {
        "total_cost_cents": total_cost_cents,
        "gross_profit_cents": gross_profit_cents,
        "fees_cents": fees_per_contract,
        "net_profit_cents": net_profit_cents,
        "net_profit_pct": round(net_profit_pct, 2),
        "max_profit_dollars": round(max_profit_dollars, 2),
        "profitable": net_profit_cents > 0,
    }
