from datetime import UTC, datetime

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(UTC)


class NewsItem(SQLModel, table=True):
    """Any piece of news the app has seen: an exchange notice or a media article (aware UTC timestamps)."""

    id: str = Field(primary_key=True)
    source: str = Field(index=True)
    title: str
    url: str | None = None
    summary: str | None = None
    published_at: datetime = Field(index=True)
    seen_at: datetime = Field(default_factory=utcnow)
    events: list[dict] = Field(default_factory=list, sa_column=Column(JSON))
    analysis: dict | None = Field(default=None, sa_column=Column(JSON))
