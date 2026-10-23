"""Application settings — one BaseSettings read from env / `.env` (documented shape: `.env.example`)."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", ".env.local"), env_ignore_empty=True, extra="ignore")

    service_name: str = "trader"
    log_level: str = "INFO"
    log_format: Literal["text", "json"] = "text"

    data_dir: Path = Path("data")
    reports_dir: Path = Path("reports")
    database_url: str = "sqlite:///data/trader.db"

    anthropic_api_key: SecretStr | None = None
    llm_fast_model: str = "claude-haiku-5-5"
    llm_deep_model: str = "claude-opus-5-5"

    binance_api_key: SecretStr | None = Field(default=None, validation_alias=AliasChoices("binance_api_key", "ccxt_api_key"))
    binance_api_secret: SecretStr | None = Field(default=None, validation_alias=AliasChoices("binance_api_secret", "ccxt_secret"))
    binance_testnet: bool = False
    trading_mode: Literal["paper", "live"] = "paper"

    taker_fee: float = 0.0005
    slippage: float = 0.0003
    event_slippage: float = 0.0015
    stop_slippage_mult: float = 2.0
    maintenance_margin: float = 0.02
    entry_latency_s: int = 60

    max_leverage: int = 20
    margin_fraction: float = 0.2
    max_notice_fraction: float = 0.3
    max_open_positions: int = 5
    max_daily_loss: float = 0.2
    paper_equity: float = 1000.0

    run_watcher: bool = False
    poll_seconds: float = 15.0
    rss_poll_seconds: float = 120.0
    monitor_seconds: float = 5.0
    max_notice_age_s: float = 300.0
    fast_trading: bool = True
    fast_max_latency_s: float = 3.0
    fast_upbit_poll_s: float = 1.0
    fast_binance_poll_s: float = 5.0
    fast_monitor_seconds: float = 1.0
    llm_news_trading: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
