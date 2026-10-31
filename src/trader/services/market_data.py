"""Local market-data store — Binance USDⓈ-M klines and funding rates as parquet, plus resampling.

    data/klines/{interval}/{SYMBOL}/{YYYY-MM}.parquet      a complete month (monthly archive file)
    data/klines/{interval}/{SYMBOL}/{YYYY-MM-DD}.parquet   one day (daily archive file): event windows, edges
    data/funding/{SYMBOL}/{YYYY-MM}.parquet                funding settlements of a month

Archive files are immutable, so they are cached forever; a 404 for an old day is cached as an empty frame (the
contract did not trade then). Days the archive may not have published yet come from REST and are never cached.
"""

import json
from collections.abc import Callable, Iterator
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from trader.core.config import settings
from trader.integrations import binance

KLINE_FIELDS = ["open_time", "open", "high", "low", "close", "volume", "quote_volume", "count", "taker_buy_volume"]
_INT_FIELDS = {"open_time", "count"}
ARCHIVE_LAG = timedelta(days=2)
RECENT = timedelta(days=7)
_rest = binance.FuturesREST()


def to_ms(moment: datetime | date) -> int:
    if not isinstance(moment, datetime):
        moment = datetime(moment.year, moment.month, moment.day, tzinfo=UTC)
    return int(moment.replace(tzinfo=moment.tzinfo or UTC).timestamp() * 1000)


def from_ms(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000, UTC)


def _normalize(df: pd.DataFrame | None) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame({c: pd.Series(dtype="int64" if c in _INT_FIELDS else "float64") for c in KLINE_FIELDS})
    df = df[KLINE_FIELDS].astype({c: "int64" if c in _INT_FIELDS else "float64" for c in KLINE_FIELDS})
    return df.drop_duplicates("open_time").sort_values("open_time", ignore_index=True)


def _cached(path: Path, fetch: Callable[[], pd.DataFrame | None], normalize: Callable[[pd.DataFrame | None], pd.DataFrame], *, cache_missing: bool) -> pd.DataFrame | None:
    if path.exists():
        return pd.read_parquet(path)
    raw = fetch()
    if raw is None and not cache_missing:
        return None
    df = normalize(raw)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)
    return df


def _months(first: date, last: date) -> Iterator[tuple[date, date]]:
    """(month_start, next_month_start) for every month touching [first, last]."""
    month = first.replace(day=1)
    while month <= last:
        following = (month + timedelta(days=32)).replace(day=1)
        yield month, following
        month = following


def _days(first: date, stop: date) -> Iterator[date]:
    while first < stop:
        yield first
        first += timedelta(days=1)


def load_klines(symbol: str, start: datetime, end: datetime, interval: str = "1m") -> pd.DataFrame:
    """Klines with open_time in [start, end), filling the local store from the archive and REST as needed.

    A month the request covers for more than a week is fetched as one monthly file; shorter spans (event
    windows) use daily files, so a one-day window never downloads a month of 1m data.
    """
    start_ms, end_ms = to_ms(start), to_ms(end)
    fresh = (datetime.now(UTC) - ARCHIVE_LAG).date()
    first, last = start.date(), (end - timedelta(milliseconds=1)).date()
    root = settings.data_dir / "klines" / interval / symbol
    frames: list[pd.DataFrame] = []
    rest_from: date | None = None
    for month, following in _months(first, last):
        lo, hi = max(month, first), min(following, last + timedelta(days=1))
        month_file = root / f"{month:%Y-%m}.parquet"
        if month_file.exists():
            frames.append(pd.read_parquet(month_file))
            continue
        if following <= fresh and (hi - lo).days > 7:
            df = _cached(month_file, lambda m=month: binance.archive_klines(symbol, interval, f"{m:%Y-%m}"), _normalize, cache_missing=False)
            if df is not None:
                frames.append(df)
                continue
        for day in _days(lo, hi):
            if day >= fresh:
                rest_from = rest_from or day
                continue
            path = root / f"{day:%Y-%m-%d}.parquet"
            df = _cached(path, lambda d=day: binance.archive_klines(symbol, interval, f"{d:%Y-%m-%d}"), _normalize, cache_missing=day < fresh - RECENT)
            frames.append(df if df is not None else _normalize(_rest.klines(symbol, interval, to_ms(day), to_ms(day + timedelta(days=1)))))
    if rest_from is not None:
        frames.append(_normalize(_rest.klines(symbol, interval, max(start_ms, to_ms(rest_from)), end_ms)))
    df = _normalize(pd.concat(frames, ignore_index=True) if frames else None)
    return df[(df.open_time >= start_ms) & (df.open_time < end_ms)].reset_index(drop=True)


def _normalize_funding(df: pd.DataFrame | None) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame({"funding_time": pd.Series(dtype="int64"), "rate": pd.Series(dtype="float64")})
    return df.astype({"funding_time": "int64", "rate": "float64"}).drop_duplicates("funding_time").sort_values("funding_time", ignore_index=True)


def load_funding(symbol: str, start: datetime, end: datetime) -> pd.DataFrame:
    """Funding settlements (funding_time ms, rate) in [start, end). Positive rate: longs pay shorts."""
    fresh = (datetime.now(UTC) - ARCHIVE_LAG).date()
    root = settings.data_dir / "funding" / symbol
    frames = []
    for month, following in _months(start.date(), (end - timedelta(milliseconds=1)).date()):
        if following <= fresh:

            def fetch(m=month, f=following):
                archived = binance.archive_funding(symbol, f"{m:%Y-%m}")
                return archived if archived is not None else _rest.funding(symbol, to_ms(m), to_ms(f))

            frames.append(_cached(root / f"{month:%Y-%m}.parquet", fetch, _normalize_funding, cache_missing=True))
        else:
            frames.append(_normalize_funding(_rest.funding(symbol, to_ms(month), to_ms(following))))
    df = _normalize_funding(pd.concat(frames, ignore_index=True) if frames else None)
    return df[(df.funding_time >= to_ms(start)) & (df.funding_time < to_ms(end))].reset_index(drop=True)


def funding_per_bar(open_time: np.ndarray, interval_ms: int, funding: pd.DataFrame) -> np.ndarray:
    """Funding rate placed on the bar whose [open, open+interval) contains each settlement; 0 elsewhere."""
    out = np.zeros(len(open_time))
    if funding.empty or not len(open_time):
        return out
    times = funding.funding_time.to_numpy()
    idx = np.searchsorted(open_time, times, side="right") - 1
    ok = (idx >= 0) & (times < open_time[np.clip(idx, 0, None)] + interval_ms)
    np.add.at(out, idx[ok], funding.rate.to_numpy()[ok])
    return out


def resample(bars: pd.DataFrame, interval: str) -> pd.DataFrame:
    """Aggregate finer klines into `interval` bars (labelled by their open time)."""
    step = binance.INTERVAL_MS[interval]
    grouped = bars.groupby(bars.open_time // step * step, sort=True)
    out = grouped.agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
        quote_volume=("quote_volume", "sum"),
        count=("count", "sum"),
        taker_buy_volume=("taker_buy_volume", "sum"),
    )
    return out.rename_axis("open_time").reset_index()


def load_bars(symbol: str, interval: str, start: datetime, end: datetime) -> tuple[pd.DataFrame, np.ndarray]:
    """`interval` bars plus the funding rate aligned to them — the input every backtest needs."""
    bars = load_klines(symbol, start, end, interval)
    funding = load_funding(symbol, start, end)
    return bars, funding_per_bar(bars.open_time.to_numpy(), binance.INTERVAL_MS[interval], funding)


def perp_universe(max_age: timedelta = timedelta(days=1)) -> set[str]:
    """Every USDⓈ-M symbol that ever traded (delisted included, so studies are survivorship-free)."""
    path = settings.data_dir / "symbols.json"
    if path.exists() and datetime.now(UTC).timestamp() - path.stat().st_mtime < max_age.total_seconds():
        return set(json.loads(path.read_text()))
    symbols = binance.archive_symbols()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(symbols))
    return set(symbols)


def perp_symbol(token: str, universe: set[str]) -> str | None:
    """USDT perpetual of a base asset — meme coins trade as 1000X / 1000000X / 1MX contracts."""
    return next((s for s in (f"{token}USDT", f"1000{token}USDT", f"1000000{token}USDT", f"1M{token}USDT") if s in universe), None)
