from __future__ import annotations

import asyncio
from typing import Any

import structlog

from config import settings
from connectors.unified import UnifiedConnector
from executor.dry_run import simulate_execution
from executor.order_manager import OrderManager
from executor.risk_manager import RiskManager
from models.opportunity import ArbitrageOpportunity
from models.order import ExecutionResult, Order, OrderStatus
from websocket.ws_manager import ws_manager

logger = structlog.get_logger()

EXECUTION_TIMEOUT = 5.0  # seconds per leg
MAX_RETRIES = 2


class ExecutionEngine:
    """Simultaneous multi-platform order execution."""

    def __init__(self, connector: UnifiedConnector) -> None:
        self.connector = connector
        self.order_manager = OrderManager()
        self.risk_manager = RiskManager()

    async def execute(
        self,
        opp: ArbitrageOpportunity,
        quantity: int,
        dry_run: bool | None = None,
    ) -> ExecutionResult:
        """Execute an arbitrage opportunity.

        If dry_run is None, uses global setting.
        """
        if dry_run is None:
            dry_run = settings.dry_run

        # Create order objects
        order_a = self.order_manager.create_order(
            platform=opp.leg_a.platform,
            market_id=opp.leg_a.market_id,
            outcome=opp.leg_a.side,
            price_cents=opp.leg_a.price_cents,
            quantity=quantity,
        )
        order_b = self.order_manager.create_order(
            platform=opp.leg_b.platform,
            market_id=opp.leg_b.market_id,
            outcome=opp.leg_b.side,
            price_cents=opp.leg_b.price_cents,
            quantity=quantity,
        )

        # Dry run mode
        if dry_run:
            result = simulate_execution(opp, order_a, order_b, quantity)
            await self.order_manager.record_execution(
                opportunity_id=opp.opportunity_id,
                match_id=opp.match_id,
                order_a=order_a,
                order_b=order_b,
                net_profit_cents=opp.net_profit_cents * quantity,
                fees_cents=opp.fees_cents * quantity,
                dry_run=True,
            )
            await ws_manager.broadcast("execution", result.model_dump())
            return result

        # LIVE execution — check risk limits first
        total_cost = opp.total_cost_cents
        allowed, reason = await self.risk_manager.check_allowed(
            opp.match_id, total_cost, quantity
        )
        if not allowed:
            logger.warning("execution_blocked_by_risk", reason=reason)
            return ExecutionResult(
                opportunity_id=opp.opportunity_id,
                order_a=order_a,
                order_b=order_b,
                dry_run=False,
                success=False,
                error_message=f"Risk check failed: {reason}",
            )

        # Execute both legs simultaneously
        result = await self._execute_simultaneous(opp, order_a, order_b, quantity)

        # Record in DB
        await self.order_manager.record_execution(
            opportunity_id=opp.opportunity_id,
            match_id=opp.match_id,
            order_a=order_a,
            order_b=order_b,
            net_profit_cents=result.realized_profit_cents,
            fees_cents=opp.fees_cents * quantity,
            dry_run=False,
            status="filled" if result.success else "failed",
            error_message=result.error_message,
        )

        await ws_manager.broadcast("execution", result.model_dump())
        return result

    async def _execute_simultaneous(
        self,
        opp: ArbitrageOpportunity,
        order_a: Order,
        order_b: Order,
        quantity: int,
    ) -> ExecutionResult:
        """Execute both legs concurrently with timeout."""
        logger.info(
            "live_execution_starting",
            opportunity=opp.opportunity_id,
            leg_a=f"{order_a.platform.value}:{order_a.market_id}",
            leg_b=f"{order_b.platform.value}:{order_b.market_id}",
            quantity=quantity,
        )

        try:
            result_a, result_b = await asyncio.wait_for(
                asyncio.gather(
                    self._place_with_retry(order_a),
                    self._place_with_retry(order_b),
                    return_exceptions=True,
                ),
                timeout=EXECUTION_TIMEOUT,
            )

            a_ok = not isinstance(result_a, Exception)
            b_ok = not isinstance(result_b, Exception)

            if a_ok and b_ok:
                order_a.status = OrderStatus.FILLED
                order_a.filled_quantity = quantity
                order_a.platform_order_id = str(result_a.get("orderId", ""))
                order_b.status = OrderStatus.FILLED
                order_b.filled_quantity = quantity
                order_b.platform_order_id = str(result_b.get("orderId", ""))

                realized = opp.net_profit_cents * quantity
                logger.info(
                    "execution_success",
                    profit_cents=realized,
                    opportunity=opp.opportunity_id,
                )
                return ExecutionResult(
                    opportunity_id=opp.opportunity_id,
                    order_a=order_a,
                    order_b=order_b,
                    dry_run=False,
                    total_cost_cents=opp.total_cost_cents * quantity,
                    realized_profit_cents=realized,
                    success=True,
                )

            # One leg failed — try to cancel the other
            error_msg = ""
            if not a_ok:
                error_msg = f"Leg A failed: {result_a}"
                if b_ok:
                    await self._try_cancel(order_b, result_b)
            if not b_ok:
                error_msg = f"Leg B failed: {result_b}"
                if a_ok:
                    await self._try_cancel(order_a, result_a)

            order_a.status = OrderStatus.FAILED if not a_ok else OrderStatus.CANCELLED
            order_b.status = OrderStatus.FAILED if not b_ok else OrderStatus.CANCELLED

            logger.error("execution_partial_failure", error=error_msg)
            return ExecutionResult(
                opportunity_id=opp.opportunity_id,
                order_a=order_a,
                order_b=order_b,
                dry_run=False,
                success=False,
                error_message=error_msg,
            )

        except asyncio.TimeoutError:
            logger.error("execution_timeout", opportunity=opp.opportunity_id)
            order_a.status = OrderStatus.FAILED
            order_b.status = OrderStatus.FAILED
            return ExecutionResult(
                opportunity_id=opp.opportunity_id,
                order_a=order_a,
                order_b=order_b,
                dry_run=False,
                success=False,
                error_message="Execution timed out",
            )

    async def _place_with_retry(self, order: Order) -> dict[str, Any]:
        """Place order with retry logic."""
        last_error = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                result = await self.connector.place_order(
                    platform=order.platform,
                    market_id=order.market_id,
                    side=order.side.value,
                    outcome=order.outcome,
                    price_cents=order.price_cents,
                    quantity=order.quantity,
                )
                return result
            except Exception as e:
                last_error = e
                logger.warning(
                    "order_retry",
                    platform=order.platform.value,
                    attempt=attempt,
                    error=str(e),
                )
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(0.5 * attempt)

        raise last_error or RuntimeError("Order placement failed")

    async def _try_cancel(self, order: Order, result: dict) -> None:
        """Try to cancel a filled order (best effort)."""
        try:
            order_id = str(result.get("orderId", order.order_id))
            connector = self.connector.get_connector(order.platform)
            await connector.cancel_order(order_id)
            logger.info("order_cancelled", platform=order.platform.value, order=order_id)
        except Exception as e:
            logger.error(
                "cancel_failed",
                platform=order.platform.value,
                error=str(e),
            )
