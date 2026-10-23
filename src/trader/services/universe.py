import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

from trader.core.config import settings
from trader.integrations import binance
from trader.services import market_data
from trader.services.events import EventType
from trader.services.playbooks import Sample

log = logging.getLogger(__name__)

HOUR_MS = 3_600_000
DAY_MS = 24 * HOUR_MS
COLUMNS = ["open_time", "open", "high", "low", "close", "volume", "quote_volume", "taker_buy_volume", "funding"]


def _root(interval: str) -> Path:
    return settings.data_dir / "universe" / interval


def usdt_perps() -> list[str]:
    return sorted(s for s in market_data.perp_universe() if s.endswith("USDT") and "_" not in s)


def _download(symbol: str, interval: str, first: str, last: str) -> int:
    path = _root(interval) / f"{symbol}.parquet"
    if path.exists():
        return 0
    months = [m for m in binance.archive_months(symbol, interval) if first <= m <= last]
    frames = [d for m in months if (d := binance.archive_klines(symbol, interval, m)) is not None]
    bars = market_data._normalize(pd.concat(frames, ignore_index=True) if frames else None)
    rates = [d for m in months if (d := binance.archive_funding(symbol, m)) is not None]
    funding = market_data._normalize_funding(pd.concat(rates, ignore_index=True) if rates else None)
    bars["funding"] = market_data.funding_per_bar(bars.open_time.to_numpy(), binance.INTERVAL_MS[interval], funding)
    path.parent.mkdir(parents=True, exist_ok=True)
    bars[COLUMNS].to_parquet(path, index=False)
    return len(bars)


def build(interval: str = "1h", first: str = "2022-01", last: str = "2026-09", workers: int = 24) -> dict:
    def safe(symbol: str) -> tuple[str, int]:
        try:
            return symbol, _download(symbol, interval, first, last)
        except Exception as exc:
            log.warning("universe %s failed: %s", symbol, exc)
            return symbol, -1

    with ThreadPoolExecutor(workers) as pool:
        result = dict(pool.map(safe, usdt_perps()))
    return {"symbols": len(result), "downloaded": sum(1 for v in result.values() if v > 0), "failed": sorted(k for k, v in result.items() if v < 0)}


def load(interval: str = "1h", min_bars: int = 24 * 14) -> dict[str, pd.DataFrame]:
    panel = {}
    for path in sorted(_root(interval).glob("*.parquet")):
        df = pd.read_parquet(path)
        if len(df) >= min_bars:
            panel[path.stem] = df.reset_index(drop=True)
    return panel


def features(df: pd.DataFrame) -> pd.DataFrame:
    c = df.close
    logret = np.log(c).diff()
    f = pd.DataFrame({"open_time": df.open_time, "close": c, "qv": df.quote_volume})
    f["r1"] = c / c.shift(1) - 1
    f["r4"] = c / c.shift(4) - 1
    f["r24"] = c / c.shift(24) - 1
    f["r168"] = c / c.shift(168) - 1
    f["vratio"] = df.quote_volume / df.quote_volume.rolling(168, min_periods=48).median().shift(1)
    f["range1"] = (df.high - df.low) / df.open
    f["taker"] = df.taker_buy_volume / df.volume.replace(0, np.nan)
    f["hi720"] = df.high.rolling(720, min_periods=240).max().shift(1)
    f["lo720"] = df.low.rolling(720, min_periods=240).min().shift(1)
    f["vol24"] = logret.rolling(24, min_periods=12).std()
    f["vol168"] = logret.rolling(168, min_periods=48).std()
    f["fund"] = df.funding
    f["fund24"] = df.funding.rolling(24, min_periods=1).sum()
    f["qv24"] = df.quote_volume.rolling(24, min_periods=1).sum()
    f["age"] = np.arange(len(df))
    return f


DETECTORS: dict[EventType, Callable[[pd.DataFrame], pd.Series]] = {
    EventType.SHOCK_PUMP_1H: lambda f: f.r1 >= 0.10,
    EventType.SHOCK_DUMP_1H: lambda f: f.r1 <= -0.10,
    EventType.SHOCK_PUMP_4H: lambda f: f.r4 >= 0.25,
    EventType.SHOCK_DUMP_4H: lambda f: f.r4 <= -0.20,
    EventType.VOLUME_SPIKE: lambda f: (f.vratio >= 10) & (f.r1.abs() < 0.03),
    EventType.BREAKOUT_30D: lambda f: (f.close > f.hi720) & (f.vratio >= 3) & (f.age >= 720),
    EventType.BREAKDOWN_30D: lambda f: (f.close < f.lo720) & (f.vratio >= 3) & (f.age >= 720),
    EventType.FUNDING_SQUEEZE: lambda f: f.fund <= -0.003,
    EventType.FUNDING_CROWDED: lambda f: f.fund >= 0.003,
}


def detect(panel: dict[str, pd.DataFrame], types: set[EventType] | None = None, dedup_ms: int = DAY_MS, min_qv24: float = 2e6) -> list[tuple[EventType, str, int, str]]:
    start = min(int(df.open_time.iloc[0]) for df in panel.values())
    events = []
    for symbol, df in panel.items():
        f = features(df)
        liquid = f.qv24 >= min_qv24
        for etype, rule in DETECTORS.items():
            if types and etype not in types:
                continue
            last = -(10**18)
            for k in np.flatnonzero((rule(f) & liquid).to_numpy()):
                ts = int(f.open_time.iat[k]) + HOUR_MS
                if ts - last >= dedup_ms:
                    events.append((etype, symbol, ts, f"{etype.value} {symbol} r1={f.r1.iat[k]:+.3f} r4={f.r4.iat[k]:+.3f} v={f.vratio.iat[k]:.1f}"))
                    last = ts
        if (types is None or EventType.NEW_PERP in types) and int(df.open_time.iloc[0]) > start + 31 * DAY_MS:
            events.append((EventType.NEW_PERP, symbol, int(df.open_time.iloc[0]) + HOUR_MS, f"new perpetual {symbol}"))
    return sorted(events, key=lambda e: e[2])


def samples(panel: dict[str, pd.DataFrame], events: list[tuple[EventType, str, int, str]], post_bars: int = 24) -> list[Sample]:
    arrays: dict[str, tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
    out = []
    for etype, symbol, ts, title in events:
        if symbol not in arrays:
            df = panel[symbol]
            arrays[symbol] = (df.open_time.to_numpy(np.int64), df[["open", "high", "low", "close"]].to_numpy(np.float64).T.copy(), df.funding.to_numpy(np.float64))
        t, ohlc, fr = arrays[symbol]
        k = int(np.searchsorted(t, ts))
        if k < 1 or k + post_bars > len(t) or t[k] != ts or t[k + post_bars - 1] != ts + (post_bars - 1) * HOUR_MS:
            continue
        lo, hi = k - 1, k + post_bars
        out.append(Sample(etype, symbol.removesuffix("USDT"), symbol, ts, title, t[lo:hi].copy(), ohlc[:, lo:hi].copy(), fr[lo:hi].copy(), 1))
    return out


def wide(panel: dict[str, pd.DataFrame], column: str) -> pd.DataFrame:
    return pd.DataFrame({s: pd.Series(df[column].to_numpy(), index=df.open_time.to_numpy()) for s, df in panel.items()}).sort_index()
