from __future__ import annotations

from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field

from .market import Platform


class OpportunityStatus(str, Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    EXECUTED = "executed"
    MISSED = "missed"


class ArbLeg(BaseModel):
    platform: Platform
    market_id: str
    side: str = Field(..., description="YES or NO")
    price_cents: int = Field(..., ge=1, le=99)
    available_qty: int = Field(default=0, ge=0)


class ArbitrageOpportunity(BaseModel):
    opportunity_id: str
    match_id: str
    market_title: str

    leg_a: ArbLeg
    leg_b: ArbLeg

    total_cost_cents: int = Field(..., description="leg_a.price + leg_b.price")
    gross_profit_cents: int = Field(..., description="100 - total_cost")
    fees_cents: int = Field(default=0, description="Total estimated fees")
    net_profit_cents: int = Field(..., description="gross_profit - fees")
    net_profit_pct: float = Field(..., description="net_profit / total_cost * 100")

    max_quantity: int = Field(default=0, description="Max executable quantity")
    max_profit_dollars: float = Field(
        default=0.0, description="net_profit_cents * max_quantity / 100"
    )

    status: OpportunityStatus = OpportunityStatus.ACTIVE
    detected_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: datetime | None = None
