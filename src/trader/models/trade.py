from datetime import datetime

from sqlmodel import Field, SQLModel

from trader.models.news import utcnow


class Trade(SQLModel, table=True):
    """A position opened by the trading loop (paper or live). Aware UTC timestamps, amounts in USDT."""

    id: int | None = Field(default=None, primary_key=True)
    mode: str = Field(index=True)
    symbol: str = Field(index=True)
    side: int
    leverage: float
    margin: float
    quantity: float
    entry_price: float
    entry_time: datetime = Field(default_factory=utcnow)
    stop_price: float | None = None
    take_profit_price: float | None = None
    trail: float = 0.0
    best_price: float
    exit_due: datetime
    trigger: str
    news_id: str | None = Field(default=None, index=True)
    status: str = Field(default="open", index=True)
    exit_price: float | None = None
    exit_time: datetime | None = None
    exit_reason: str | None = None
    fees: float = 0.0
    pnl: float | None = None
