from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel

from trader.models.news import utcnow


class IntelSignal(SQLModel, table=True):
    """One hour of news attention for one perp symbol (symbol "MARKET" holds the market-wide aggregates).

    `open_time` is the hour start in ms UTC; the row aggregates items published in [open_time, open_time + 1h),
    so it is known at that 1h bar's close — join it to the bar with the same open_time.
    """

    id: str = Field(primary_key=True)
    symbol: str = Field(index=True)
    open_time: int = Field(index=True)
    mentions: int = 0
    sources: int = 0
    burst_z: float = 0.0
    polarity: float = 0.0
    llm_score: float = 0.0
    categories: dict = Field(default_factory=dict, sa_column=Column(JSON))
    updated_at: str = Field(default_factory=lambda: utcnow().isoformat())
