"""Source adapters: media RSS, exchange boards, Reddit (text → `NewsItem`) and numeric market-attention series (→ DataFrames).

Every adapter is `async fetch(client) -> list[NewsItem] | pandas.DataFrame` and raises on failure; `run()` isolates
failures per source so one dead endpoint never breaks a pass. Series frames are long-format: ts (ms UTC), key, metric, value.
"""

import asyncio
import calendar
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import feedparser
import httpx
import pandas as pd

from trader.models import NewsItem

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36"
HEADERS = {"User-Agent": UA, "Accept": "application/json, application/rss+xml, application/xml;q=0.9, */*;q=0.8"}

MEDIA = {
    "coindesk": "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "cointelegraph": "https://cointelegraph.com/rss",
    "decrypt": "https://decrypt.co/feed",
    "theblock": "https://www.theblock.co/rss.xml",
    "bitcoinmagazine": "https://bitcoinmagazine.com/.rss/full/",
    "blockworks": "https://blockworks.co/feed",
    "cryptoslate": "https://cryptoslate.com/feed/",
    "thedefiant": "https://thedefiant.io/api/feed",
    "beincrypto": "https://beincrypto.com/feed/",
    "utoday": "https://u.today/rss",
    "newsbtc": "https://www.newsbtc.com/feed/",
    "cryptopotato": "https://cryptopotato.com/feed/",
    "bitcoinist": "https://bitcoinist.com/feed/",
    "cryptonews": "https://cryptonews.com/news/feed/",
    "dailyhodl": "https://dailyhodl.com/feed/",
    "ambcrypto": "https://ambcrypto.com/feed/",
    "cryptobriefing": "https://cryptobriefing.com/feed/",
    "coinjournal": "https://coinjournal.net/feed/",
}
BLOG_FEEDS = {"kraken": "https://blog.kraken.com/feed", "coinbase": "https://medium.com/feed/the-coinbase-blog"}
DEAD = {
    "glassnode": "https://insights.glassnode.com/rss/ (403 to non-browser clients)",
    "messari": "https://messari.io/rss (404)",
    "coinbase_blog": "https://www.coinbase.com/blog/rss.xml (403)",
    "bithumb": "https://feed.bithumb.com/notice and api.bithumb.com/v1/notices (403)",
}
SUBREDDITS = ["CryptoCurrency", "CryptoMarkets", "Bitcoin", "ethereum", "solana", "altcoin"]
REDDIT_UA = "python:crypto-trader-intel:v0.1 (research; contact via repo)"

FAPI = "https://fapi.binance.com"
POSITIONING = {
    "open_interest": ("/futures/data/openInterestHist", "sumOpenInterestValue"),
    "top_account_ratio": ("/futures/data/topLongShortAccountRatio", "longShortRatio"),
    "top_position_ratio": ("/futures/data/topLongShortPositionRatio", "longShortRatio"),
    "global_account_ratio": ("/futures/data/globalLongShortAccountRatio", "longShortRatio"),
    "taker_buy_sell_ratio": ("/futures/data/takerlongshortRatio", "buySellRatio"),
}
POSITIONING_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT", "BNBUSDT"]
WIKI_ARTICLES = {
    "BTC": ["Bitcoin"],
    "ETH": ["Ethereum"],
    "SOL": ["Solana_(blockchain_platform)"],
    "XRP": ["XRP_Ledger", "Ripple_(payment_protocol)"],
    "DOGE": ["Dogecoin"],
    "ADA": ["Cardano_(blockchain_platform)"],
    "LTC": ["Litecoin"],
    "TRX": ["Tron_(cryptocurrency)"],
    "SHIB": ["Shiba_Inu_(cryptocurrency)"],
}
GDELT_QUERIES = {"BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana crypto", "XRP": "xrp ripple", "DOGE": "dogecoin"}
GDELT = "https://api.gdeltproject.org/api/v2/doc/doc"
SERIES_COLUMNS = ["ts", "key", "metric", "value"]


@dataclass(frozen=True)
class Source:
    name: str
    kind: str
    fetch: Callable[[httpx.AsyncClient], Awaitable[list[NewsItem] | pd.DataFrame]]


@dataclass
class Result:
    source: Source
    ok: bool
    items: int
    latency_s: float
    error: str | None = None
    payload: list[NewsItem] | pd.DataFrame | None = None


def client(timeout: float = 20.0) -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=timeout, follow_redirects=True, headers=HEADERS)


def _ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def _from_ms(ms) -> datetime:
    return datetime.fromtimestamp(int(ms) / 1000, UTC)


def _item(source: str, source_id: str, title: str, published_at: datetime, url: str | None, summary: str | None = None) -> NewsItem:
    return NewsItem(id=f"{source}:{source_id[-200:]}", source=source, title=title.strip(), url=url, summary=(summary or "")[:2000] or None, published_at=published_at)


def parse_feed(source: str, content: bytes) -> list[NewsItem]:
    """RSS/Atom bytes → items (entries without a timestamp are skipped); raises when the payload is not a feed at all."""
    parsed = feedparser.parse(content)
    if not parsed.entries and (parsed.bozo or not parsed.feed):
        raise ValueError(f"not a feed: {content[:80]!r}")
    out = []
    for entry in parsed.entries:
        stamp = entry.get("published_parsed") or entry.get("updated_parsed")
        if not stamp or not entry.get("title"):
            continue
        published = datetime.fromtimestamp(calendar.timegm(stamp), UTC)
        out.append(_item(source, str(entry.get("id") or entry.get("link")), entry["title"], published, entry.get("link"), entry.get("summary")))
    return out


async def _get(c: httpx.AsyncClient, url: str, **kwargs) -> httpx.Response:
    response = await c.get(url, **kwargs)
    response.raise_for_status()
    return response


def rss_source(name: str, url: str, prefix: str = "rss") -> Source:
    async def fetch(c: httpx.AsyncClient) -> list[NewsItem]:
        return parse_feed(f"{prefix}:{name}", (await _get(c, url)).content)

    return Source(f"{prefix}:{name}", "media" if prefix == "rss" else "board", fetch)


async def bybit(c: httpx.AsyncClient) -> list[NewsItem]:
    data = (await _get(c, "https://api.bybit.com/v5/announcements/index", params={"locale": "en-US", "limit": 50})).json()
    if data.get("retCode") != 0:
        raise RuntimeError(data.get("retMsg"))
    return [
        _item("bybit", a["url"].rstrip("/").rsplit("-", 1)[-1], a["title"], _from_ms(a["publishTime"]), a["url"], f"[{a['type']['title']}] {a.get('description') or ''}")
        for a in data["result"]["list"]
    ]


async def okx(c: httpx.AsyncClient) -> list[NewsItem]:
    data = (await _get(c, "https://www.okx.com/api/v5/support/announcements")).json()
    if data.get("code") != "0":
        raise RuntimeError(data.get("msg"))
    return [_item("okx", a["url"].rsplit("/", 1)[-1], a["title"], _from_ms(a["pTime"]), a["url"], f"[{a['annType']}]") for page in data["data"] for a in page["details"]]


async def kucoin(c: httpx.AsyncClient) -> list[NewsItem]:
    data = (await _get(c, "https://api.kucoin.com/api/v3/announcements", params={"lang": "en_US", "pageSize": 50})).json()
    if data.get("code") != "200000":
        raise RuntimeError(data.get("msg"))
    return [_item("kucoin", str(a["annId"]), a["annTitle"], _from_ms(a["cTime"]), a["annUrl"], a.get("annDesc")) for a in data["data"]["items"]]


async def binance_board(c: httpx.AsyncClient) -> list[NewsItem]:
    from trader.integrations import binance
    from trader.services.events import binance_notice
    from trader.services.news import to_item

    pages = await asyncio.gather(*(binance.announcements(c, catalog, 1, 20) for catalog in binance.CATALOGS))
    return [to_item(binance_notice(a)) for page in pages for a in page]


async def upbit_board(c: httpx.AsyncClient) -> list[NewsItem]:
    from trader.integrations import upbit
    from trader.services.events import upbit_notice
    from trader.services.news import to_item

    found, _ = await upbit.notices(c, 1, per_page=20)
    return [to_item(upbit_notice(n)) for n in found]


def parse_reddit_feed(content: bytes) -> list[NewsItem]:
    """Multireddit Atom feed → items whose source is `reddit:<subreddit>` (from each entry's category term)."""
    parsed = feedparser.parse(content)
    if not parsed.entries and (parsed.bozo or not parsed.feed):
        raise ValueError(f"not a feed: {content[:80]!r}")
    out = []
    for entry in parsed.entries:
        stamp = entry.get("published_parsed") or entry.get("updated_parsed")
        if not stamp or not entry.get("title"):
            continue
        sub = (entry.get("tags") or [{}])[0].get("term") or "unknown"
        published = datetime.fromtimestamp(calendar.timegm(stamp), UTC)
        out.append(_item(f"reddit:{sub}", str(entry.get("id") or entry.get("link")), entry["title"], published, entry.get("link"), entry.get("summary")))
    return out


async def reddit(c: httpx.AsyncClient) -> list[NewsItem]:
    """All subreddits in ONE multireddit request: unauthenticated clients get roughly one request per minute."""
    url = f"https://www.reddit.com/r/{'+'.join(SUBREDDITS)}/new/.rss"
    return parse_reddit_feed((await _get(c, url, params={"limit": 100}, headers={"User-Agent": REDDIT_UA})).content)


def parse_fear_greed(doc: dict) -> pd.DataFrame:
    rows = [(int(d["timestamp"]) * 1000, "MARKET", "fear_greed", float(d["value"])) for d in doc["data"]]
    return pd.DataFrame(rows, columns=SERIES_COLUMNS)


async def fear_greed(c: httpx.AsyncClient, limit: int = 0) -> pd.DataFrame:
    return parse_fear_greed((await _get(c, "https://api.alternative.me/fng/", params={"limit": limit, "format": "json"})).json())


def parse_trending(doc: dict, at_ms: int) -> pd.DataFrame:
    rows = [(at_ms, coin["item"]["symbol"].upper(), "cg_trending_rank", float(rank + 1)) for rank, coin in enumerate(doc.get("coins", []))]
    return pd.DataFrame(rows, columns=SERIES_COLUMNS)


async def coingecko_trending(c: httpx.AsyncClient) -> pd.DataFrame:
    doc = (await _get(c, "https://api.coingecko.com/api/v3/search/trending")).json()
    return parse_trending(doc, _ms(datetime.now(UTC).replace(minute=0, second=0, microsecond=0)))


def parse_positioning(symbol: str, metric: str, field: str, rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame([(int(r["timestamp"]), symbol, metric, float(r[field])) for r in rows], columns=SERIES_COLUMNS)


async def positioning(c: httpx.AsyncClient, symbols: list[str] | None = None, period: str = "1h", limit: int = 500) -> pd.DataFrame:
    """Binance futures positioning (≈30 days of history at most) for a few symbols."""

    async def one(symbol: str, metric: str, path: str, field: str) -> pd.DataFrame:
        rows = (await _get(c, FAPI + path, params={"symbol": symbol, "period": period, "limit": limit})).json()
        return parse_positioning(symbol, metric, field, rows)

    jobs = [one(s, m, path, field) for s in symbols or POSITIONING_SYMBOLS for m, (path, field) in POSITIONING.items()]
    return pd.concat(await asyncio.gather(*jobs), ignore_index=True)


def parse_pageviews(token: str, doc: dict) -> pd.DataFrame:
    rows = [(_ms(datetime.strptime(i["timestamp"][:8], "%Y%m%d").replace(tzinfo=UTC)), token, "wiki_views", float(i["views"])) for i in doc.get("items", [])]
    return pd.DataFrame(rows, columns=SERIES_COLUMNS)


async def wikipedia(c: httpx.AsyncClient, start: str = "20200101", end: str | None = None, articles: dict[str, list[str]] | None = None) -> pd.DataFrame:
    """Daily English-Wikipedia user pageviews per token; renamed articles are summed. Paced, Wikimedia throttles bursts."""
    end = end or (datetime.now(UTC) - timedelta(days=1)).strftime("%Y%m%d")
    base = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user"
    frames = []
    for token, titles in (articles or WIKI_ARTICLES).items():
        for title in titles:
            for attempt in range(4):
                response = await c.get(f"{base}/{title}/daily/{start}/{end}")
                if response.status_code not in (403, 429):
                    break
                await asyncio.sleep(5 * (attempt + 1))
            response.raise_for_status()
            frames.append(parse_pageviews(token, response.json()))
            await asyncio.sleep(1.0)
    frame = pd.concat(frames, ignore_index=True)
    return frame.groupby(["ts", "key", "metric"], as_index=False)["value"].sum()[SERIES_COLUMNS]


def parse_gdelt(token: str, metric: str, doc: dict) -> pd.DataFrame:
    rows = []
    for series in doc.get("timeline", []):
        for point in series.get("data", []):
            ts = _ms(datetime.strptime(point["date"], "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC))
            rows.append((ts, token, metric, float(point["value"])))
            if metric == "gdelt_volume" and "norm" in point:
                rows.append((ts, token, "gdelt_total", float(point["norm"])))
    return pd.DataFrame(rows, columns=SERIES_COLUMNS)


async def gdelt_one(c: httpx.AsyncClient, token: str, query: str, mode: str, start: datetime, end: datetime) -> pd.DataFrame:
    params = {"query": query, "mode": mode, "format": "json", "startdatetime": start.strftime("%Y%m%d%H%M%S"), "enddatetime": end.strftime("%Y%m%d%H%M%S")}
    for attempt in range(6):
        response = await c.get(GDELT, params=params, timeout=60)
        if response.status_code == 429 or "limit requests" in response.text[:200]:
            await asyncio.sleep(8 * (attempt + 1))
            continue
        response.raise_for_status()
        return parse_gdelt(token, "gdelt_volume" if mode == "timelinevolraw" else "gdelt_tone", response.json())
    raise RuntimeError("GDELT kept rate-limiting (one request per 5 s)")


async def gdelt(c: httpx.AsyncClient, days: int = 7, queries: dict[str, str] | None = None) -> pd.DataFrame:
    end = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    frames = []
    for token, query in (queries or GDELT_QUERIES).items():
        for mode in ("timelinevolraw", "timelinetone"):
            frames.append(await gdelt_one(c, token, query, mode, end - timedelta(days=days), end))
            await asyncio.sleep(5.5)
    return pd.concat(frames, ignore_index=True)


async def metrics_archive_probe(c: httpx.AsyncClient) -> pd.DataFrame:
    from trader.intel import history

    day = (datetime.now(UTC) - timedelta(days=3)).date()
    return history.metrics_day_long("BTCUSDT", await history.fetch_metrics_day(c, "BTCUSDT", day))


def registry() -> list[Source]:
    out = [rss_source(name, url) for name, url in MEDIA.items()]
    out += [
        Source("binance", "board", binance_board),
        Source("upbit", "board", upbit_board),
        Source("bybit", "board", bybit),
        Source("okx", "board", okx),
        Source("kucoin", "board", kucoin),
    ]
    out += [rss_source(name, url, prefix="blog") for name, url in BLOG_FEEDS.items()]
    out.append(Source("reddit", "reddit", reddit))
    out += [
        Source("fear_greed", "series", lambda c: fear_greed(c, limit=30)),
        Source("coingecko_trending", "series", coingecko_trending),
        Source("binance_positioning", "series", positioning),
        Source("binance_metrics_archive", "series", metrics_archive_probe),
        Source("wikipedia_pageviews", "series", lambda c: wikipedia(c, start=(datetime.now(UTC) - timedelta(days=30)).strftime("%Y%m%d"), articles={"BTC": ["Bitcoin"]})),
        Source("gdelt", "series", lambda c: gdelt(c, days=3, queries={"BTC": "bitcoin"})),
    ]
    return out


async def _run_one(c: httpx.AsyncClient, source: Source, timeout: float) -> Result:
    started = time.perf_counter()
    try:
        payload = await asyncio.wait_for(source.fetch(c), timeout)
    except Exception as exc:
        return Result(source, False, 0, time.perf_counter() - started, f"{type(exc).__name__}: {exc}"[:200])
    return Result(source, True, len(payload), time.perf_counter() - started, payload=payload)


async def run(sources: list[Source] | None = None, *, c: httpx.AsyncClient | None = None, timeout: float = 90.0) -> list[Result]:
    """Fetch every source concurrently; failures become `ok=False` results instead of exceptions."""
    sources = registry() if sources is None else sources
    own = c is None
    c = c or client()
    try:
        return list(await asyncio.gather(*(_run_one(c, s, timeout) for s in sources)))
    finally:
        if own:
            await c.aclose()
