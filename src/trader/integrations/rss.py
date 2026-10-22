"""Crypto-media RSS feeds — free-text news the LLM triages (no learned playbook, so trading on them is opt-in)."""

import calendar
from datetime import UTC, datetime

import feedparser
import httpx

FEEDS = {
    "cointelegraph": "https://cointelegraph.com/rss",
    "coindesk": "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "decrypt": "https://decrypt.co/feed",
    "theblock": "https://www.theblock.co/rss.xml",
    "bitcoinmagazine": "https://bitcoinmagazine.com/.rss/full/",
}


async def entries(client: httpx.AsyncClient, feed: str) -> list[dict]:
    """Feed entries → [{id, title, url, summary, published_at (UTC)}]; empty on any feed error."""
    try:
        response = await client.get(FEEDS[feed], follow_redirects=True, headers={"User-Agent": "Mozilla/5.0 (trader research bot)"})
        response.raise_for_status()
    except httpx.HTTPError:
        return []
    out = []
    for entry in feedparser.parse(response.content).entries:
        stamp = entry.get("published_parsed") or entry.get("updated_parsed")
        if not stamp:
            continue
        out.append({
            "id": entry.get("id") or entry.get("link"),
            "title": entry.get("title", "").strip(),
            "url": entry.get("link"),
            "summary": entry.get("summary", "")[:2000],
            "published_at": datetime.fromtimestamp(calendar.timegm(stamp), UTC),
        })
    return out
