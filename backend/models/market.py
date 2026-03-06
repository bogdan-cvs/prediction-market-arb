from __future__ import annotations

from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field


class Platform(str, Enum):
    KALSHI = "kalshi"
    POLYMARKET = "polymarket"
    LIMITLESS = "limitless"
    IBKR = "ibkr"


class OutcomeSide(str, Enum):
    YES = "YES"
    NO = "NO"


class MarketStatus(str, Enum):
    OPEN = "open"
    CLOSED = "closed"
    SETTLED = "settled"
    UNKNOWN = "unknown"


class OrderBookLevel(BaseModel):
    price_cents: float = Field(..., gt=0, lt=100, description="Price in cents")
    quantity: int = Field(..., ge=0, description="Available contracts")


class OrderBook(BaseModel):
    yes_asks: list[OrderBookLevel] = Field(default_factory=list)
    yes_bids: list[OrderBookLevel] = Field(default_factory=list)
    no_asks: list[OrderBookLevel] = Field(default_factory=list)
    no_bids: list[OrderBookLevel] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class NormalizedMarket(BaseModel):
    platform: Platform
    platform_market_id: str = Field(..., description="Native ID on the platform")
    ticker: str = Field(default="", description="Ticker symbol if available")
    title: str = Field(..., description="Human-readable market title")
    category: str = Field(default="", description="Category (crypto, politics, etc.)")

    # Extracted entities for matching
    asset: str = Field(default="", description="Underlying asset (BTC, ETH, etc.)")
    threshold: float | None = Field(default=None, description="Price threshold")
    direction: str = Field(default="", description="above/below/exact")
    event_date: datetime | None = Field(default=None, description="Resolution date")

    # Pricing (cents with decimal precision, e.g. 2.9, 93.2)
    yes_ask_cents: float | None = Field(default=None, description="Best YES ask price")
    yes_bid_cents: float | None = Field(default=None, description="Best YES bid price")
    no_ask_cents: float | None = Field(default=None, description="Best NO ask price")
    no_bid_cents: float | None = Field(default=None, description="Best NO bid price")

    orderbook: OrderBook | None = Field(default=None, description="Full orderbook")

    status: MarketStatus = MarketStatus.OPEN
    volume: int = Field(default=0, description="Total volume traded")
    expiration: datetime | None = None
    last_updated: datetime = Field(default_factory=datetime.utcnow)


class MatchedMarket(BaseModel):
    match_id: str
    markets: dict[Platform, NormalizedMarket] = Field(
        ..., description="Platform -> normalized market"
    )
    match_score: float = Field(
        default=1.0, ge=0.0, le=1.0, description="Confidence of match"
    )
    verified: bool = Field(default=False, description="Manually verified by user")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_seen: datetime = Field(default_factory=datetime.utcnow)
