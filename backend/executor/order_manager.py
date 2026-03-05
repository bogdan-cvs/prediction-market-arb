from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

import aiosqlite
import structlog

from database import DB_PATH
from models.market import Platform
from models.order import Order, OrderSide, OrderStatus, OrderType

logger = structlog.get_logger()


class OrderManager:
    """Track order lifecycle: create, update status, record in DB."""

    def create_order(
        self,
        platform: Platform,
        market_id: str,
        outcome: str,
        price_cents: int,
        quantity: int,
    ) -> Order:
        return Order(
            order_id=str(uuid.uuid4())[:12],
            platform=platform,
            market_id=market_id,
            side=OrderSide.BUY,
            outcome=outcome,
            order_type=OrderType.MARKET,
            price_cents=price_cents,
            quantity=quantity,
        )

    async def record_execution(
        self,
        opportunity_id: str,
        match_id: str,
        order_a: Order,
        order_b: Order,
        net_profit_cents: int,
        fees_cents: int,
        dry_run: bool,
        status: str = "filled",
        error_message: str | None = None,
    ) -> None:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                """
                INSERT INTO trade_history
                (opportunity_id, match_id, platform_a, platform_b, side_a, side_b,
                 price_a_cents, price_b_cents, quantity, gross_profit_cents,
                 fees_cents, net_profit_cents, dry_run, status,
                 order_a_id, order_b_id, error_message)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    opportunity_id,
                    match_id,
                    order_a.platform.value,
                    order_b.platform.value,
                    order_a.outcome,
                    order_b.outcome,
                    order_a.price_cents,
                    order_b.price_cents,
                    order_a.quantity,
                    100 - order_a.price_cents - order_b.price_cents,
                    fees_cents,
                    net_profit_cents,
                    1 if dry_run else 0,
                    status,
                    order_a.platform_order_id or order_a.order_id,
                    order_b.platform_order_id or order_b.order_id,
                    error_message,
                ),
            )
            await db.commit()
            logger.info(
                "trade_recorded",
                opportunity=opportunity_id,
                profit=net_profit_cents,
                dry_run=dry_run,
            )
