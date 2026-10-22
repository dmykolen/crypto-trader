"""News ingestion: exchange notice boards (Upbit, Binance CMS) and media RSS → `NewsItem` rows.

`backfill()` pulls the full notice history once (it feeds the event studies); `poll()` fetches the newest
page of every source and returns only items never seen before — the watcher calls it every few seconds.
"""

import asyncio
import logging
from datetime import UTC

import httpx
from sqlmodel import Session, select

from trader.core.metrics import news_items_total, news_poll_seconds
from trader.integrations import binance, rss, upbit
from trader.models import NewsItem
from trader.services.events import Event, Notice, binance_notice, classify, upbit_notice

log = logging.getLogger(__name__)


def to_item(notice: Notice, summary: str | None = None) -> NewsItem:
    return NewsItem(
        id=f"{notice.source}:{notice.source_id}",
        source=notice.source,
        title=notice.title,
        url=notice.url,
        summary=summary,
        published_at=notice.published_at.astimezone(UTC),
        events=[{"type": e.type.value, "token": e.token} for e in classify(notice)],
    )


def to_notice(item: NewsItem) -> Notice:
    return Notice(item.source, item.id.split(":", 1)[1], item.title, item.published_at.astimezone(UTC), item.url)


def item_events(item: NewsItem) -> list[Event]:
    return classify(to_notice(item))


def store_new(session: Session, items: list[NewsItem]) -> list[NewsItem]:
    """Insert the items not stored yet; returns those (the genuinely new ones)."""
    if not items:
        return []
    known = set(session.exec(select(NewsItem.id).where(NewsItem.id.in_([i.id for i in items]))).all())  # type: ignore[attr-defined]
    fresh = list({i.id: i for i in items if i.id not in known}.values())
    session.add_all(fresh)
    session.commit()
    for item in fresh:
        news_items_total.labels(item.source).inc()
    return fresh


# ---------------------------------------------------------------- history


async def backfill(session: Session, *, binance_pages: int = 100, page_size: int = 50) -> dict[str, int]:
    """Full notice history of Upbit (trade category) and the Binance listing/delisting/news catalogs.

    Every page is stored as it arrives and known items are skipped, so an interrupted run is continued by running it again.
    """
    counts: dict[str, int] = {}
    async with httpx.AsyncClient(timeout=30) as client:
        page, pages, stored = 1, 1, 0
        while page <= pages:
            batch, pages = await upbit.notices(client, page, per_page=20)
            stored += len(store_new(session, [to_item(upbit_notice(n)) for n in batch]))
            page += 1
            await asyncio.sleep(0.7)
        counts["upbit"] = stored
        for catalog, name in binance.CATALOGS.items():
            stored, page = 0, 1
            try:
                for page in range(1, binance_pages + 1):
                    batch = await binance.announcements(client, catalog, page, page_size)
                    stored += len(store_new(session, [to_item(binance_notice(a)) for a in batch]))
                    await asyncio.sleep(2.0)
                    if len(batch) < page_size:
                        break
            except (RuntimeError, httpx.HTTPError) as exc:  # keep what is stored; the next catalog may still work
                log.warning("binance %s backfill stopped at page %d (%s) — run the backfill again to continue", name, page, exc)
            counts[f"binance:{name}"] = stored
    log.info("backfill stored %s", counts)
    return counts


# ---------------------------------------------------------------- live


async def _timed(source: str, coro):
    with news_poll_seconds.labels(source).time():
        try:
            return await coro
        except Exception as exc:  # one flaky source must not stop the others
            log.warning("news source %s failed: %s", source, exc)
            return []


async def fetch_exchange_notices(client: httpx.AsyncClient) -> list[NewsItem]:
    async def upbit_page():
        found, _ = await upbit.notices(client, 1, per_page=20)
        return [to_item(upbit_notice(n)) for n in found]

    async def binance_page(catalog: int):
        return [to_item(binance_notice(a)) for a in await binance.announcements(client, catalog, 1, 20)]

    pages = await asyncio.gather(_timed("upbit", upbit_page()), *(_timed(f"binance_{name}", binance_page(c)) for c, name in binance.CATALOGS.items()))
    return [item for page in pages for item in page]


async def fetch_media(client: httpx.AsyncClient) -> list[NewsItem]:
    pages = await asyncio.gather(*(_timed(feed, rss.entries(client, feed)) for feed in rss.FEEDS))
    items = []
    for feed, entries in zip(rss.FEEDS, pages, strict=True):
        for e in entries:
            notice = Notice(feed, str(e["id"])[-200:], e["title"], e["published_at"], e["url"])
            items.append(to_item(notice, summary=e["summary"]))
    return items
