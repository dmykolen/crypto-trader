"""News backfill: pages are stored as they arrive, so a rate-limited catalog keeps its progress and a re-run resumes."""

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

from sqlmodel import Session, col, delete

from trader.core.db import create_db_and_tables, engine
from trader.integrations import binance, upbit
from trader.models import NewsItem
from trader.services import news
from trader.services.events import Notice


def test_backfill_keeps_stored_pages_when_a_catalog_keeps_failing(monkeypatch):
    def notice(source: str, i: int) -> Notice:
        return Notice(source, f"backfill-{i}", f"{source} notice {i}", datetime(2026, 1, 1, tzinfo=UTC))

    async def upbit_notices(client, page, per_page=20):
        return [page], 2  # two pages with one notice each

    async def announcements(client, catalog, page, page_size=20):
        if catalog == 49 and page == 2:
            raise RuntimeError("Binance CMS kept rate-limiting catalog 49")
        return [catalog * 100 + page * 10 + k for k in range(page_size if catalog == 49 else 1)]

    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr(upbit, "notices", upbit_notices)
    monkeypatch.setattr(binance, "announcements", announcements)
    monkeypatch.setattr(news, "upbit_notice", lambda n: notice("upbit", n))
    monkeypatch.setattr(news, "binance_notice", lambda a: notice("binance", a))
    monkeypatch.setattr(news, "asyncio", SimpleNamespace(sleep=no_sleep))
    create_db_and_tables()
    mine = col(NewsItem.id).like("%:backfill-%")
    with Session(engine) as session:
        session.exec(delete(NewsItem).where(mine))
        session.commit()
        first = asyncio.run(news.backfill(session, page_size=2))
        again = asyncio.run(news.backfill(session, page_size=2))
        session.exec(delete(NewsItem).where(mine))
        session.commit()
    assert first == {"upbit": 2, "binance:listing": 1, "binance:delisting": 1, "binance:news": 2}  # page 1 of `news` survived the failure
    assert again == dict.fromkeys(first, 0)  # a re-run skips everything already stored
