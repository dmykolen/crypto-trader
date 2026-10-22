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

    # Anthropic: the fast model triages news in the hot path, the deep one writes briefs and reviews.
    anthropic_api_key: SecretStr | None = None
    llm_fast_model: str = "claude-haiku-5-5"
    llm_deep_model: str = "claude-opus-5-5"

    # Binance USDⓈ-M — keys are only needed for TRADING_MODE=live (CCXT_API_KEY / CCXT_SECRET are accepted too).
    binance_api_key: SecretStr | None = Field(default=None, validation_alias=AliasChoices("binance_api_key", "ccxt_api_key"))
    binance_api_secret: SecretStr | None = Field(default=None, validation_alias=AliasChoices("binance_api_secret", "ccxt_secret"))
    binance_testnet: bool = False  # Binance demo trading (needs demo-account keys)
    trading_mode: Literal["paper", "live"] = "paper"

    # Cost model shared by every backtest and by the paper broker (conservative for VIP0 taker flow).
    taker_fee: float = 0.0005
    slippage: float = 0.0003  # per side, liquid majors
    event_slippage: float = 0.0015  # per side, small caps right after an announcement
    stop_slippage_mult: float = 2.0  # stop-market exits slip this many times more
    maintenance_margin: float = 0.02  # above Binance's 0.4-2.5 % tiers → liquidation modelled early
    entry_latency_s: int = 60  # reaction time assumed between an announcement and our first fill

    # Risk rails for paper/live trading.
    max_leverage: int = 20
    margin_fraction: float = 0.2  # isolated margin committed per trade, fraction of equity
    max_notice_fraction: float = 0.3  # all trades triggered by ONE announcement together commit at most this much
    max_open_positions: int = 5
    max_daily_loss: float = 0.2  # no new positions once the UTC day's realized loss reaches this fraction of equity
    paper_equity: float = 1000.0

    # Trading loop (`trader run`, or inside uvicorn when RUN_WATCHER=true).
    run_watcher: bool = False
    poll_seconds: float = 15.0  # exchange notice boards
    rss_poll_seconds: float = 120.0  # media feeds
    monitor_seconds: float = 5.0  # open positions
    max_notice_age_s: float = 300.0  # a notice first seen later than this is recorded, never traded
    llm_news_trading: bool = False  # trade free-text news on the LLM's word alone (no learned playbook)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
