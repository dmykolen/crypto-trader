"""Intel history backfill: archive days that keep failing are skipped and retried later, 404 days are remembered,
progress is saved as it arrives, and GDELT chunks already cached are never re-requested."""

import asyncio
import io
import json
import zipfile
from datetime import UTC, date, datetime, timedelta

import httpx
import pandas as pd
import pytest

from trader.intel import history, sources

HEADER = ",".join(history.RAW_COLUMNS)


def metrics_zip(symbol: str, day: date, header: bool = True) -> bytes:
    rows = []
    for minute in range(0, 24 * 60, 5):
        stamp = datetime.combine(day, datetime.min.time()) + timedelta(minutes=minute)
        rows.append(f"{stamp:%Y-%m-%d %H:%M:%S},{symbol},{1000 + minute},{50000 + minute},1.5,1.2,1.1,0.9")
    text = "\n".join(([HEADER] if header else []) + rows) + "\n"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(f"{symbol}-metrics-{day}.csv", text)
    return buffer.getvalue()


def day_of(url: str) -> date:
    return date.fromisoformat(url.rsplit("-metrics-", 1)[1].removesuffix(".zip"))


def run(coro):
    return asyncio.run(coro)


def test_fetch_retries_transient_statuses_then_parses():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url)
        if len(calls) < 3:
            return httpx.Response(503)
        return httpx.Response(200, content=metrics_zip("BTCUSDT", date(2023, 3, 1), header=False))

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
            return await history.fetch_metrics_day(c, "BTCUSDT", date(2023, 3, 1), backoff_s=0)

    frame = run(go())
    assert len(calls) == 3
    assert len(frame) == 288 and frame["create_time"].dt.tz is not None


def test_fetch_returns_none_on_404_and_raises_after_persistent_failure():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404) if "2023-03-02" in str(request.url) else httpx.Response(200, content=b"not a zip")

    async def go(day):
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
            return await history.fetch_metrics_day(c, "ETHUSDT", day, attempts=3, backoff_s=0)

    assert run(go(date(2023, 3, 2))) is None
    with pytest.raises(history.ArchiveError, match="bad archive"):
        run(go(date(2023, 3, 3)))


def test_metrics_hourly_keeps_the_last_snapshot_inside_each_hour():
    hourly = history.metrics_hourly(history.parse_metrics_zip(metrics_zip("BTCUSDT", date(2023, 3, 1))))
    first = int(datetime(2023, 3, 1, tzinfo=UTC).timestamp() * 1000)
    row = hourly.set_index("open_time").loc[first]
    assert row["oi"] == 1000 + 55
    assert len(hourly) == 24


def test_backfill_symbol_skips_failing_days_remembers_404_and_resumes(monkeypatch):
    bad = {date(2023, 5, 3)}
    gone = {date(2023, 5, 5)}
    seen: list[date] = []

    def handler(request: httpx.Request) -> httpx.Response:
        day = day_of(str(request.url))
        seen.append(day)
        if day in gone:
            return httpx.Response(404)
        if day in bad:
            return httpx.Response(500)
        return httpx.Response(200, content=metrics_zip("TESTUSDT", day))

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
            return await history.backfill_symbol(c, "TESTUSDT", date(2023, 5, 1), date(2023, 5, 6), asyncio.Semaphore(4), chunk_days=2)

    monkeypatch.setattr(history, "fetch_metrics_day", _fast(history.fetch_metrics_day))
    first = run(go())
    assert first["failed_days"] == ["2023-05-03"]
    assert first["missing_days"] == 1
    assert history.metrics_path("TESTUSDT").exists()
    assert json.loads(history._missing_path("TESTUSDT").read_text()) == ["2023-05-05"]
    cached_days = set(pd.to_datetime(history.load_metrics("TESTUSDT")["open_time"], unit="ms", utc=True).dt.date)
    assert {date(2023, 5, 1), date(2023, 5, 6)} <= cached_days and date(2023, 5, 3) not in cached_days

    bad.clear()
    seen.clear()
    second = run(go())
    assert seen == [date(2023, 5, 3)]
    assert second["failed_days"] == []


def _fast(fetch):
    async def wrapped(c, symbol, day, **kwargs):
        return await fetch(c, symbol, day, attempts=2, backoff_s=0)

    return wrapped


def test_backfill_metrics_isolates_a_symbol_that_aborts(monkeypatch):
    async def boom(c, symbol, start, end, gate, **kwargs):
        if symbol == "BADUSDT":
            raise OSError("disk full")
        return {"rows": 7, "failed_days": []}

    monkeypatch.setattr(history, "backfill_symbol", boom)
    out = run(history.backfill_metrics(["BADUSDT", "OKUSDT"], date(2023, 1, 1), date(2023, 1, 2)))
    assert out["OKUSDT"]["rows"] == 7
    assert "disk full" in out["BADUSDT"]["error"]


def test_gdelt_backfill_writes_each_chunk_and_skips_cached_ones(monkeypatch):
    calls = []

    async def gdelt_one(c, token, query, mode, start, end):
        calls.append((token, mode, start))
        if mode == "timelinetone" and start.year == 2023:
            raise RuntimeError("rate limited")
        metric = "gdelt_volume" if mode == "timelinevolraw" else "gdelt_tone"
        days = pd.date_range(start, end, freq="D", inclusive="left")
        return pd.DataFrame({"ts": [int(d.timestamp() * 1000) for d in days], "key": token, "metric": metric, "value": 1.0})

    monkeypatch.setattr(sources, "gdelt_one", gdelt_one)
    if history.series_path("gdelt").exists():
        history.series_path("gdelt").unlink()
    start, end = datetime(2022, 1, 1, tzinfo=UTC), datetime(2023, 6, 1, tzinfo=UTC)
    first = run(history.backfill_gdelt(start, end, {"BTC": "bitcoin"}, pause_s=0, chunk_days=365))
    assert first["chunks_fetched"] == 3 and first["chunks_failed"] == 1
    assert first["rows"] > 365 * 2

    calls.clear()
    second = run(history.backfill_gdelt(start, end, {"BTC": "bitcoin"}, pause_s=0, chunk_days=365))
    assert calls == [("BTC", "timelinetone", datetime(2023, 1, 1, tzinfo=UTC))]
    assert second["chunks_cached"] == 3
