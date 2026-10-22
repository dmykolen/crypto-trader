"""Binance public data: the bulk archive (data.binance.vision), USDⓈ-M REST market data, CMS announcements.

The archive is survivorship-free — contracts delisted long ago keep their files — so history comes from it;
REST fills the last day or two the archive has not published yet. Authenticated trading lives in
`integrations/exchange.py`.
"""

import asyncio
import io
import re
import time
import zipfile

import httpx
import pandas as pd
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

ARCHIVE = "https://data.binance.vision"
ARCHIVE_LISTING = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
FAPI = "https://fapi.binance.com"
CMS = "https://www.binance.com/bapi/composite/v1/public/cms/article/list/query"
ANNOUNCEMENT_URL = "https://www.binance.com/en/support/announcement/{code}"

KLINE_COLUMNS = ["open_time", "open", "high", "low", "close", "volume", "close_time", "quote_volume", "count", "taker_buy_volume", "taker_buy_quote_volume", "ignore"]
INTERVAL_MS = {"1m": 60_000, "3m": 180_000, "5m": 300_000, "15m": 900_000, "30m": 1_800_000, "1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000}
# CMS catalogs worth watching: listings, delistings, general news (monitoring tags live there).
CATALOGS = {48: "listing", 161: "delisting", 49: "news"}

_HEADERS = {"User-Agent": "Mozilla/5.0 (trader research bot)", "Accept": "application/json"}
_archive = httpx.Client(timeout=60, follow_redirects=True, headers=_HEADERS)


# ---------------------------------------------------------------- archive (data.binance.vision)


@retry(stop=stop_after_attempt(5), wait=wait_exponential(min=1, max=30), retry=retry_if_exception_type(httpx.TransportError), reraise=True)
def _archive_get(path: str) -> bytes | None:
    response = _archive.get(f"{ARCHIVE}/{path}")
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return response.content


def _read_zip_csv(raw: bytes, names: list[str]) -> pd.DataFrame:
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        body = archive.read(archive.namelist()[0])
    return pd.read_csv(io.BytesIO(body), header=None if body[:1].isdigit() else 0, names=names)


def archive_klines(symbol: str, interval: str, period: str) -> pd.DataFrame | None:
    """One archive file: `period` is `YYYY-MM` (monthly file) or `YYYY-MM-DD` (daily file). None when absent."""
    kind = "monthly" if len(period) == 7 else "daily"
    raw = _archive_get(f"data/futures/um/{kind}/klines/{symbol}/{interval}/{symbol}-{interval}-{period}.zip")
    return None if raw is None else _read_zip_csv(raw, KLINE_COLUMNS)


def archive_funding(symbol: str, month: str) -> pd.DataFrame | None:
    """Monthly funding file → columns funding_time (ms), rate."""
    raw = _archive_get(f"data/futures/um/monthly/fundingRate/{symbol}/{symbol}-fundingRate-{month}.zip")
    if raw is None:
        return None
    df = _read_zip_csv(raw, ["calc_time", "funding_interval_hours", "last_funding_rate"])
    return pd.DataFrame({"funding_time": df["calc_time"].astype("int64"), "rate": df["last_funding_rate"].astype("float64")})


def archive_symbols() -> list[str]:
    """Every USDⓈ-M contract that ever published daily klines, delisted ones included."""
    symbols, marker, prefix = [], "", "data/futures/um/daily/klines/"
    while True:
        xml = _archive.get(ARCHIVE_LISTING, params={"delimiter": "/", "prefix": prefix, "marker": marker}).text
        found = re.findall(rf"<Prefix>{prefix}([^<]+)/</Prefix>", xml)
        symbols += found
        if "<IsTruncated>true</IsTruncated>" not in xml or not found:
            return sorted(set(symbols))
        next_marker = re.search(r"<NextMarker>(.*?)</NextMarker>", xml)
        marker = next_marker.group(1) if next_marker else f"{prefix}{found[-1]}/"


# ---------------------------------------------------------------- REST (fapi)


class FuturesREST:
    """Public USDⓈ-M endpoints. Sync on purpose: used by batch research and wrapped in threads elsewhere."""

    def __init__(self, base_url: str = FAPI) -> None:
        self._http = httpx.Client(base_url=base_url, timeout=20, headers=_HEADERS)

    def _get(self, path: str, **params):
        for attempt in range(8):
            try:
                response = self._http.get(path, params=params)
            except httpx.TransportError:
                time.sleep(2 * (attempt + 1))
                continue
            if response.status_code in (418, 429):  # weight limit / IP ban: back off hard
                time.sleep(min(60, 5 * (attempt + 1)))
                continue
            if response.status_code == 400:  # unknown symbol or out-of-range window
                return None
            response.raise_for_status()
            return response.json()
        raise RuntimeError(f"Binance REST kept rate-limiting {path}")

    def exchange_info(self) -> dict:
        return self._get("/fapi/v1/exchangeInfo")

    def klines(self, symbol: str, interval: str, start_ms: int, end_ms: int) -> pd.DataFrame:
        rows, cursor = [], start_ms
        while cursor < end_ms:
            batch = self._get("/fapi/v1/klines", symbol=symbol, interval=interval, startTime=cursor, endTime=end_ms - 1, limit=1500)
            if not batch:
                break
            rows += batch
            cursor = batch[-1][0] + INTERVAL_MS[interval]
            if len(batch) < 1500:
                break
        return pd.DataFrame(rows, columns=KLINE_COLUMNS)

    def funding(self, symbol: str, start_ms: int, end_ms: int) -> pd.DataFrame | None:
        rows, cursor = [], start_ms
        while cursor < end_ms:
            batch = self._get("/fapi/v1/fundingRate", symbol=symbol, startTime=cursor, endTime=end_ms - 1, limit=1000)
            if batch is None:
                return None
            if not batch:
                break
            rows += batch
            cursor = batch[-1]["fundingTime"] + 1
            if len(batch) < 1000:
                break
        return pd.DataFrame({"funding_time": [int(r["fundingTime"]) for r in rows], "rate": [float(r["fundingRate"]) for r in rows]})

    def last_price(self, symbol: str) -> float:
        return float(self._get("/fapi/v1/ticker/price", symbol=symbol)["price"])


# ---------------------------------------------------------------- CMS announcements


async def announcements(client: httpx.AsyncClient, catalog_id: int, page: int = 1, page_size: int = 20) -> list[dict]:
    """One page of a CMS catalog, newest first → [{id, code, title, releaseDate(ms)}]. Backs off on 418/429 (≈3 min in total)."""
    for attempt in range(6):
        response = await client.get(CMS, params={"type": 1, "catalogId": catalog_id, "pageNo": page, "pageSize": page_size}, headers=_HEADERS)
        if response.status_code in (418, 429):
            await asyncio.sleep(min(60, 5 * 2**attempt))
            continue
        response.raise_for_status()
        catalogs = response.json()["data"]["catalogs"]
        return catalogs[0]["articles"] if catalogs else []
    raise RuntimeError(f"Binance CMS kept rate-limiting catalog {catalog_id}")
