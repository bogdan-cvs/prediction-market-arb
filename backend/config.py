from __future__ import annotations

from pydantic_settings import BaseSettings
from pydantic import Field
from pathlib import Path


class Settings(BaseSettings):
    # Kalshi
    kalshi_api_key: str = ""
    kalshi_private_key_path: str = "./keys/kalshi_private.pem"
    kalshi_base_url: str = "https://api.elections.kalshi.com"

    # Polymarket
    polymarket_private_key: str = ""
    polymarket_proxy_address: str = ""

    # Limitless Exchange
    limitless_private_key: str = ""
    limitless_api_key: str = ""

    # IBKR
    ibkr_host: str = "127.0.0.1"
    ibkr_port: int = 7497
    ibkr_client_id: int = 1

    # Scanner
    min_profit_cents: int = 2
    min_quantity: int = 10
    scan_interval_seconds: int = 3

    # Risk
    max_exposure_per_market: int = 100
    max_total_exposure: int = 1000
    max_daily_loss: int = 50

    # Mode
    dry_run: bool = True

    # DB
    db_path: str = "arb_data.db"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
