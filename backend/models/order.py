from __future__ import annotations

from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field

from .market import Platform


class OrderStatus(str, Enum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    FILLED = "filled"
    PARTIAL = "partial"
    CANCELLED = "cancelled"
    FAILED = "failed"


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"


class Order(BaseModel):
    order_id: str
    platform: Platform
    market_id: str
    side: OrderSide
    outcome: str = Field(..., description="YES or NO")
    order_type: OrderType = OrderType.MARKET
    price_cents: int = Field(..., ge=1, le=99)
    quantity: int = Field(..., ge=1)
    filled_quantity: int = Field(default=0, ge=0)
    filled_avg_price_cents: int | None = None
    status: OrderStatus = OrderStatus.PENDING
    platform_order_id: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    error_message: str | None = None


class ExecutionResult(BaseModel):
    opportunity_id: str
    order_a: Order
    order_b: Order
    dry_run: bool = True
    total_cost_cents: int = 0
    realized_profit_cents: int = 0
    success: bool = False
    error_message: str | None = None
    executed_at: datetime = Field(default_factory=datetime.utcnow)
