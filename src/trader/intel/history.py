"""Historical series caches under data/intel/: long-format parquet per series family + the Binance metrics archive per symbol.

The metrics archive (data.binance.vision, 5-minute OI and long/short ratios since late 2021) is downloaded day by day
and reduced to hourly bars: the row of hour `t` holds the last 5-minute snapshot with create_time in [t, t+1h).
"""

import asyncio
import io
import json
import logging
import zipfile
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx
import pandas as pd

from trader.core.config import settings
from trader.intel import sources

log = logging.getLogger(__name__)

ARCHIVE = "https://data.binance.vision/data/futures/um/daily/metrics"
METRIC_COLUMNS = {
    "sum_open_interest": "oi",
    "sum_open_interest_value": "oi_value",
    "count_toptrader_long_short_ratio": "top_account_ratio",
    "sum_toptrader_long_short_ratio": "top_position_ratio",
    "count_long_short_ratio": "global_account_ratio",
    "sum_taker_long_short_vol_ratio": "taker_ratio",
}
RAW_COLUMNS = ["create_time", "symbol", *METRIC_COLUMNS]
HOUR_MS = 3_600_000


def intel_dir() -> Path:
    path = settings.data_dir / "intel"
    path.mkdir(parents=True, exist_ok=True)
    return path


def series_path(name: str) -> Path:
    path = intel_dir() / "series"
    path.mkdir(parents=True, exist_ok=True)
    return path / f"{name}.parquet"


def load_series(name: str) -> pd.DataFrame:
    path = series_path(name)
    return pd.read_parquet(path) if path.exists() else pd.DataFrame(columns=sources.SERIES_COLUMNS)


def upsert_series(name: str, frame: pd.DataFrame) -> int:
    """Merge rows into the cache (newest value wins per ts/key/metric); returns the cached row count."""
    if frame is None or frame.empty:
        return len(load_series(name))
    merged = pd.concat([load_series(name), frame[sources.SERIES_COLUMNS]], ignore_index=True)
    merged["ts"] = merged["ts"].astype("int64")
    merged["value"] = merged["value"].astype(float)
    merged = merged.drop_duplicates(["ts", "key", "metric"], keep="last").sort_values(["metric", "key", "ts"]).reset_index(drop=True)
    merged.to_parquet(series_path(name), index=False)
    return len(merged)


def parse_metrics_zip(raw: bytes) -> pd.DataFrame:
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        text = archive.read(archive.namelist()[0])
    has_header = text[:11] == b"create_time"
    frame = pd.read_csv(io.BytesIO(text), header=0 if has_header else None, names=None if has_header else RAW_COLUMNS)
    frame["create_time"] = pd.to_datetime(frame["create_time"], utc=True)
    return frame


RETRY_STATUS = (403, 408, 429, 500, 502, 503, 504)


class ArchiveError(RuntimeError):
    """One archive day could not be fetched after every retry (transient: the next backfill retries it)."""


async def fetch_metrics_day(c: httpx.AsyncClient, symbol: str, day: date, *, attempts: int = 5, backoff_s: float = 2.0) -> pd.DataFrame | None:
    """One archive day → raw 5-minute frame; None when the file does not exist (404: not listed yet / delisted).

    Transport errors, throttling/5xx statuses and truncated zips are retried with linear backoff, then `ArchiveError`.
    """
    url = f"{ARCHIVE}/{symbol}/{symbol}-metrics-{day.isoformat()}.zip"
    last = "no attempt"
    for attempt in range(attempts):
        try:
            response = await c.get(url, timeout=60)
        except httpx.TransportError as exc:
            last = f"{type(exc).__name__}: {exc}"
            await asyncio.sleep(backoff_s * (attempt + 1))
            continue
        if response.status_code == 404:
            return None
        if response.status_code in RETRY_STATUS:
            last = f"HTTP {response.status_code}"
            await asyncio.sleep(backoff_s * 1.5 * (attempt + 1))
            continue
        response.raise_for_status()
        try:
            return parse_metrics_zip(response.content)
        except (zipfile.BadZipFile, pd.errors.ParserError, pd.errors.EmptyDataError, KeyError, IndexError) as exc:
            last = f"bad archive: {type(exc).__name__}"
            await asyncio.sleep(backoff_s * (attempt + 1))
    raise ArchiveError(f"metrics archive kept failing for {symbol} {day} ({last})")


def metrics_hourly(frame: pd.DataFrame) -> pd.DataFrame:
    """5-minute archive rows → one row per hour (last snapshot inside the hour), keyed by open_time in ms."""
    frame = frame.rename(columns=METRIC_COLUMNS)
    frame["open_time"] = ((frame["create_time"] - pd.Timestamp(0, tz=UTC)) // pd.Timedelta(hours=1)).astype("int64") * HOUR_MS
    cols = list(METRIC_COLUMNS.values())
    for col in cols:
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    return frame.sort_values("create_time").groupby("open_time", as_index=False)[cols].last()


def metrics_day_long(symbol: str, frame: pd.DataFrame | None) -> pd.DataFrame:
    if frame is None:
        raise RuntimeError(f"no archive file for {symbol}")
    hourly = metrics_hourly(frame).melt(id_vars="open_time", var_name="metric", value_name="value").rename(columns={"open_time": "ts"})
    hourly["key"] = symbol
    return hourly[sources.SERIES_COLUMNS]


def metrics_path(symbol: str) -> Path:
    path = intel_dir() / "metrics"
    path.mkdir(parents=True, exist_ok=True)
    return path / f"{symbol}.parquet"


def load_metrics(symbol: str) -> pd.DataFrame:
    path = metrics_path(symbol)
    return pd.read_parquet(path) if path.exists() else pd.DataFrame(columns=["open_time", *METRIC_COLUMNS.values()])


def _missing_path(symbol: str) -> Path:
    return metrics_path(symbol).with_suffix(".missing.json")


def _merge_metrics(cached: pd.DataFrame, frames: list[pd.DataFrame]) -> pd.DataFrame:
    merged = pd.concat([f for f in (cached, *frames) if len(f)], ignore_index=True)
    merged["open_time"] = merged["open_time"].astype("int64")
    return merged.drop_duplicates("open_time", keep="last").sort_values("open_time").reset_index(drop=True)


def _cached_days(cached: pd.DataFrame) -> set[date]:
    return set(pd.to_datetime(cached["open_time"], unit="ms", utc=True).dt.date) if len(cached) else set()


async def backfill_symbol(c: httpx.AsyncClient, symbol: str, start: date, end: date, gate: asyncio.Semaphore, *, chunk_days: int = 120) -> dict:
    """Fetch the not-yet-cached, not-known-404 days of one symbol, saving after every chunk so a crash keeps progress.

    A day that keeps failing is logged and skipped (never cached as missing), so the next run retries exactly those days.
    """
    cached = load_metrics(symbol)
    missing_file = _missing_path(symbol)
    missing = set(json.loads(missing_file.read_text())) if missing_file.exists() else set()
    have = _cached_days(cached)
    todo = [d for d in (start + timedelta(days=i) for i in range((end - start).days + 1)) if d not in have and d.isoformat() not in missing]
    remember_404 = (datetime.now(UTC).date() - end).days > 2
    failed: list[str] = []

    async def one(day: date):
        async with gate:
            try:
                frame = await fetch_metrics_day(c, symbol, day)
                return day, None if frame is None or frame.empty else metrics_hourly(frame)
            except (ArchiveError, httpx.HTTPError, ValueError, KeyError) as exc:
                log.warning("metrics %s %s skipped (%s); re-run to retry", symbol, day, exc)
                return day, False

    for i in range(0, len(todo), chunk_days):
        frames = []
        for day, hourly in await asyncio.gather(*(one(d) for d in todo[i : i + chunk_days])):
            if hourly is False:
                failed.append(day.isoformat())
            elif hourly is None:
                missing.add(day.isoformat())
            else:
                frames.append(hourly)
        if frames:
            cached = _merge_metrics(cached, frames)
            cached.to_parquet(metrics_path(symbol), index=False)
        if remember_404:
            missing_file.write_text(json.dumps(sorted(missing)))
    summary = {"rows": len(cached), "requested_days": len(todo), "failed_days": failed, "missing_days": len(missing)}
    log.info("metrics %s: %d hourly rows (%d days requested, %d failed, %d known missing)", symbol, len(cached), len(todo), len(failed), len(missing))
    return summary


async def backfill_metrics(symbols: list[str], start: date, end: date, *, concurrency: int = 24) -> dict[str, dict]:
    """Backfill the metrics archive for every symbol; one symbol failing never stops the others."""
    gate = asyncio.Semaphore(concurrency)
    out: dict[str, dict] = {}
    async with sources.client(timeout=60) as c:
        for symbol in symbols:
            try:
                out[symbol] = await backfill_symbol(c, symbol, start, end, gate)
            except Exception as exc:
                log.exception("metrics %s aborted", symbol)
                out[symbol] = {"rows": len(load_metrics(symbol)), "error": f"{type(exc).__name__}: {exc}"[:200]}
    return out


def _gdelt_done(cached: pd.DataFrame, token: str, metric: str, start: datetime, stop: datetime) -> bool:
    """True when the cache already holds (almost) every daily point of this chunk."""
    if cached.empty:
        return False
    sel = cached[(cached["key"] == token) & (cached["metric"] == metric) & (cached["ts"] >= sources._ms(start)) & (cached["ts"] < sources._ms(stop))]
    return len(sel) >= max(1, (stop - start).days - 2)


async def backfill_gdelt(start: datetime, end: datetime, queries: dict[str, str] | None = None, *, pause_s: float = 6.5, chunk_days: int = 2000) -> dict:
    """GDELT DOC 2.0 volume + tone timelines (daily resolution for long spans), paced at one request per ~6 s.

    GDELT throttles per IP far below its documented limit, so the default chunk spans the whole range: two requests
    per token. Resumable: chunks already in the cache are skipped and every fetched chunk is written immediately.
    """
    done = failed = skipped = 0
    async with sources.client(timeout=90) as c:
        for token, query in (queries or sources.GDELT_QUERIES).items():
            cursor = start
            while cursor < end:
                stop = min(cursor + timedelta(days=chunk_days), end)
                for mode, metric in (("timelinevolraw", "gdelt_volume"), ("timelinetone", "gdelt_tone")):
                    if _gdelt_done(load_series("gdelt"), token, metric, cursor, stop):
                        skipped += 1
                        continue
                    try:
                        upsert_series("gdelt", await sources.gdelt_one(c, token, query, mode, cursor, stop))
                        done += 1
                    except Exception as exc:
                        failed += 1
                        log.warning("gdelt %s %s %s failed: %s", token, mode, cursor.date(), f"{type(exc).__name__}: {exc}")
                    await asyncio.sleep(pause_s)
                cursor = stop
    return {"rows": len(load_series("gdelt")), "chunks_fetched": done, "chunks_failed": failed, "chunks_cached": skipped}


async def backfill_series(*, wiki_start: str = "20211201", gdelt_from: datetime | None = None) -> dict:
    """Full Fear & Greed history + Wikipedia pageviews (+ GDELT when `gdelt_from` is given); each family fails alone."""
    out: dict = {}
    async with sources.client(timeout=60) as c:
        for name, job in (("fear_greed", lambda: sources.fear_greed(c, limit=0)), ("wiki", lambda: sources.wikipedia(c, start=wiki_start))):
            try:
                out[name] = upsert_series(name, await job())
            except Exception as exc:
                log.warning("%s backfill failed: %s", name, exc)
                out[name] = f"FAIL {type(exc).__name__}: {exc}"[:200]
    if gdelt_from is not None:
        out["gdelt"] = await backfill_gdelt(gdelt_from, datetime.now(UTC).replace(minute=0, second=0, microsecond=0))
    return out
