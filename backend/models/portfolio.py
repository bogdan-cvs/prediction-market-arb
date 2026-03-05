from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, Field

from .market import Platform


class PlatformBalance(BaseModel):
    platform: Platform
    available_cents: int = Field(default=0, description="Available balance in cents")
    reserved_cents: int = Field(default=0, description="Reserved for open orders")
    total_cents: int = Field(default=0, description="Total = available + reserved")
    currency: str = Field(default="USD")
    last_updated: datetime = Field(default_factory=datetime.utcnow)


class Position(BaseModel):
    position_id: str
    platform: Platform
    market_id: str
    market_title: str
    outcome: str = Field(..., description="YES or NO")
    quantity: int = Field(default=0, ge=0)
    avg_price_cents: int = Field(default=0)
    current_price_cents: int | None = None
    unrealized_pnl_cents: int = Field(default=0)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class PortfolioSummary(BaseModel):
    balances: list[PlatformBalance] = Field(default_factory=list)
    positions: list[Position] = Field(default_factory=list)
    total_balance_cents: int = 0
    total_exposure_cents: int = 0
    total_realized_pnl_cents: int = 0
    total_unrealized_pnl_cents: int = 0
    daily_pnl_cents: int = 0
    trade_count_today: int = 0
