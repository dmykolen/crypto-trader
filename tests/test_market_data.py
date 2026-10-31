from datetime import UTC, datetime, timedelta

import pandas as pd

from trader.core.config import settings
from trader.services import market_data


def _bars(start: datetime, hours: int) -> pd.DataFrame:
    t0 = market_data.to_ms(start)
    return pd.DataFrame({c: [1.0] * hours for c in market_data.KLINE_FIELDS} | {"open_time": [t0 + h * 3_600_000 for h in range(hours)], "count": [1] * hours})


def test_a_recent_day_the_archive_has_not_published_comes_from_rest_and_is_not_cached_as_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    day = (datetime.now(UTC) - timedelta(days=3)).date()
    start = datetime(day.year, day.month, day.day, tzinfo=UTC)
    monkeypatch.setattr(market_data.binance, "archive_klines", lambda *args: None)
    monkeypatch.setattr(market_data._rest, "klines", lambda symbol, interval, lo, hi: _bars(market_data.from_ms(lo), 24))
    out = market_data.load_klines("SOLUSDT", start, start + timedelta(days=1), "1h")
    assert len(out) == 24
    assert not (tmp_path / "klines" / "1h" / "SOLUSDT" / f"{day:%Y-%m-%d}.parquet").exists()


def test_an_old_day_missing_from_the_archive_is_remembered_as_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    start = datetime(2025, 3, 3, tzinfo=UTC)
    monkeypatch.setattr(market_data.binance, "archive_klines", lambda *args: None)
    monkeypatch.setattr(market_data._rest, "klines", lambda *args: _bars(start, 24))
    assert market_data.load_klines("SOLUSDT", start, start + timedelta(days=1), "1h").empty
    assert (tmp_path / "klines" / "1h" / "SOLUSDT" / "2025-03-03.parquet").exists()
