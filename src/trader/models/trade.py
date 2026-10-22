from datetime import datetime

from sqlmodel import Field, SQLModel

from trader.models.news import utcnow


class Trade(SQLModel, table=True):
    """A position opened by the trading loop (paper or live). Aware UTC timestamps, amounts in USDT."""

    id: int | None = Field(default=None, primary_key=True)
    mode: str = Field(index=True)  # paper | live
    symbol: str = Field(index=True)
    side: int  # 1 long, -1 short
    leverage: float
    margin: float  # isolated margin committed
    quantity: float
    entry_price: float
    entry_time: datetime = Field(default_factory=utcnow)
    stop_price: float | None = None  # a trailing stop moves it
    take_profit_price: float | None = None
    trail: float = 0.0
    best_price: float  # most favourable price seen — drives the trailing stop
    exit_due: datetime  # time exit
    trigger: str  # what opened it: "upbit_krw_listing: SHORT 3x, enter +15m, …" or "llm:listing"
    news_id: str | None = Field(default=None, index=True)
    status: str = Field(default="open", index=True)  # open | closed
    exit_price: float | None = None
    exit_time: datetime | None = None
    exit_reason: str | None = None
    fees: float = 0.0
    pnl: float | None = None  # realized, after fees
