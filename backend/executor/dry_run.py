from __future__ import annotations

import structlog

from models.opportunity import ArbitrageOpportunity
from models.order import ExecutionResult, Order, OrderStatus

logger = structlog.get_logger()


def simulate_execution(
    opp: ArbitrageOpportunity,
    order_a: Order,
    order_b: Order,
    quantity: int,
) -> ExecutionResult:
    """Simulate an execution without sending real orders."""
    # Mark as filled in simulation
    order_a.status = OrderStatus.FILLED
    order_a.filled_quantity = quantity
    order_a.filled_avg_price_cents = order_a.price_cents
    order_a.platform_order_id = f"DRY-{order_a.order_id}"

    order_b.status = OrderStatus.FILLED
    order_b.filled_quantity = quantity
    order_b.filled_avg_price_cents = order_b.price_cents
    order_b.platform_order_id = f"DRY-{order_b.order_id}"

    total_cost = order_a.price_cents + order_b.price_cents
    realized_profit = opp.net_profit_cents * quantity

    logger.info(
        "dry_run_executed",
        opportunity=opp.opportunity_id,
        market=opp.market_title,
        leg_a=f"{order_a.platform.value} {order_a.outcome}@{order_a.price_cents}c",
        leg_b=f"{order_b.platform.value} {order_b.outcome}@{order_b.price_cents}c",
        quantity=quantity,
        profit_cents=realized_profit,
    )

    return ExecutionResult(
        opportunity_id=opp.opportunity_id,
        order_a=order_a,
        order_b=order_b,
        dry_run=True,
        total_cost_cents=total_cost * quantity,
        realized_profit_cents=realized_profit,
        success=True,
    )
