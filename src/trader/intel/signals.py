"""Hourly per-token news signals + market-wide series, persisted as `IntelSignal` rows, and `features()` for bots.

Timing contract: a row with open_time t aggregates items published in [t, t+1h) and is joined to the 1h bar with the
same open_time, i.e. it is usable at that bar's close. Daily series for day D are only used once complete and
published: GDELT from D+1 00:00, Wikipedia pageviews (published hours after midnight) from D+1 06:00; Fear & Greed
(published at 00:00 UTC for that day) from its own timestamp.
"""

import re
from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd
from sqlmodel import Session, col, select

from trader.intel import history
from trader.intel.analyze import llm_scores, tag
from trader.intel.entities import Linker, base_assets
from trader.intel.models import IntelSignal
from trader.models import NewsItem

HOUR_MS = 3_600_000
BASELINE_HOURS = 168
MARKET = "MARKET"
RECORD_COLUMNS = ["ts", "symbol", "source", "key", "polarity", "llm", "category"]
DAILY_LAG_HOURS = {"wiki": 30, "gdelt": 24}


def _ms(value: datetime | int | float | pd.Timestamp) -> int:
    if isinstance(value, int | float | np.integer):
        return int(value)
    stamp = pd.Timestamp(value)
    return int((stamp.tz_convert(UTC) if stamp.tzinfo else stamp.tz_localize(UTC)).timestamp() * 1000)


def _floor_hour(ms: int) -> int:
    return ms // HOUR_MS * HOUR_MS


def title_key(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()[:120]


def records(items: list[NewsItem], linker: Linker) -> pd.DataFrame:
    """Items → one row per (item, linked symbol) plus one MARKET row per item."""
    rows = []
    for item in items:
        intel = (item.analysis or {}).get("intel") or tag(item, linker)
        ts = _ms(item.published_at)
        key = title_key(item.title)
        scores = llm_scores(item.analysis, linker)
        rows.append((ts, MARKET, item.source, key, intel["polarity"], 0.0, intel["category"]))
        for symbol in intel["symbols"]:
            rows.append((ts, symbol, item.source, key, intel["polarity"], scores.get(symbol, 0.0), intel["category"]))
    return pd.DataFrame(rows, columns=RECORD_COLUMNS)


def burst_z(counts: pd.Series, window: int = BASELINE_HOURS) -> pd.Series:
    """Count vs its trailing `window`-hour baseline (current hour excluded); the variance is floored at the Poisson
    variance (the mean) and at 1/24 so a quiet history does not turn one mention into an infinite z."""
    prev = counts.shift(1)
    mean = prev.rolling(window, min_periods=24).mean()
    var = prev.rolling(window, min_periods=24).var().fillna(0.0)
    scale = np.sqrt(np.maximum(np.maximum(var, mean), 1.0 / 24))
    return ((counts - mean) / scale).fillna(0.0)


def aggregate(frame: pd.DataFrame, start_ms: int, end_ms: int) -> pd.DataFrame:
    """Records → hourly rows per symbol in [start, end): mentions (distinct titles), distinct sources, burst z vs the
    trailing 7 days (records before `start` serve as baseline), mean polarity, Σ LLM score, category counts."""
    columns = ["symbol", "open_time", "mentions", "sources", "burst_z", "polarity", "llm_score", "categories"]
    if frame.empty:
        return pd.DataFrame(columns=columns)
    frame = frame.assign(open_time=frame["ts"].astype("int64") // HOUR_MS * HOUR_MS)
    first = min(int(frame["open_time"].min()), _floor_hour(start_ms))
    grid = np.arange(first, _floor_hour(end_ms - 1) + HOUR_MS, HOUR_MS)
    out = []
    for symbol, group in frame.groupby("symbol"):
        dedup = group.drop_duplicates(["open_time", "key"])
        hourly = pd.DataFrame({
            "mentions": dedup.groupby("open_time").size(),
            "sources": group.groupby("open_time")["source"].nunique(),
            "polarity": dedup.groupby("open_time")["polarity"].mean(),
            "llm_score": group.drop_duplicates(["open_time", "key", "llm"]).groupby("open_time")["llm"].sum(),
        }).reindex(grid)
        hourly["mentions"] = hourly["mentions"].fillna(0).astype(int)
        hourly["sources"] = hourly["sources"].fillna(0).astype(int)
        hourly["burst_z"] = burst_z(hourly["mentions"].astype(float))
        cats = dedup.groupby(["open_time", "category"]).size()
        hourly["categories"] = [{c: int(n) for c, n in cats.loc[t].items()} if t in cats.index.get_level_values(0) else {} for t in hourly.index]
        hourly = hourly[(hourly.index >= _floor_hour(start_ms)) & (hourly.index < end_ms)]
        hourly = hourly[(hourly["mentions"] > 0) | (symbol == MARKET)]
        hourly = hourly.assign(symbol=symbol, open_time=hourly.index, polarity=hourly["polarity"].fillna(0.0), llm_score=hourly["llm_score"].fillna(0.0))
        out.append(hourly[columns])
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame(columns=columns)


def compute(session: Session, start: datetime, end: datetime, linker: Linker) -> int:
    """Recompute and upsert `IntelSignal` rows for [start, end) from stored items; returns rows written."""
    start_ms, end_ms = _ms(start), _ms(end)
    since = start - timedelta(hours=BASELINE_HOURS)
    items = list(session.exec(select(NewsItem).where(col(NewsItem.published_at) >= since, col(NewsItem.published_at) < end)).all())
    frame = aggregate(records(items, linker), start_ms, end_ms)
    stamp = datetime.now(UTC).isoformat()
    for row in frame.itertuples(index=False):
        session.merge(
            IntelSignal(
                id=f"{row.symbol}:{int(row.open_time)}",
                symbol=row.symbol,
                open_time=int(row.open_time),
                mentions=int(row.mentions),
                sources=int(row.sources),
                burst_z=float(row.burst_z),
                polarity=float(row.polarity),
                llm_score=float(row.llm_score),
                categories=row.categories,
                updated_at=stamp,
            )
        )
    session.commit()
    return len(frame)


def _signal_frame(session: Session, symbol: str, start_ms: int, end_ms: int) -> pd.DataFrame:
    rows = session.exec(select(IntelSignal).where(IntelSignal.symbol == symbol, col(IntelSignal.open_time) >= start_ms, col(IntelSignal.open_time) < end_ms)).all()
    return pd.DataFrame([r.model_dump() for r in rows]) if rows else pd.DataFrame(columns=list(IntelSignal.model_fields))


def _asof(index: pd.Index, series: pd.DataFrame, value: str, lag_ms: int = 0) -> pd.Series:
    """Latest series value with ts + lag ≤ open_time, aligned to `index` (NaN before the first observation)."""
    if series.empty:
        return pd.Series(np.nan, index=index)
    right = series[["ts", value]].assign(ts=series["ts"].astype("int64") + lag_ms).sort_values("ts")
    left = pd.DataFrame({"open_time": index.astype("int64")})
    merged = pd.merge_asof(left, right, left_on="open_time", right_on="ts", direction="backward")
    return pd.Series(merged[value].to_numpy(), index=index)


def _daily_z(series: pd.DataFrame, window: int = 28) -> pd.DataFrame:
    """Daily log value vs its trailing `window`-day mean/std (current day included — it is complete when used)."""
    series = series.sort_values("ts").copy()
    logv = np.log1p(series["value"].astype(float))
    series["z"] = (logv - logv.rolling(window, min_periods=7).mean()) / logv.rolling(window, min_periods=7).std()
    return series


def features(symbol: str, start: datetime | int, end: datetime | int, session: Session | None = None) -> pd.DataFrame:
    """Hourly model features for `symbol` over [start, end), indexed by open_time (ms UTC) like the 1h panel."""
    from trader.core.db import engine

    start_ms, end_ms = _floor_hour(_ms(start)), _ms(end)
    index = pd.Index(np.arange(start_ms, end_ms, HOUR_MS, dtype="int64"), name="open_time")
    out = pd.DataFrame(index=index)
    own = session is None
    session = session or Session(engine)
    try:
        sig = _signal_frame(session, symbol, start_ms, end_ms).set_index("open_time").reindex(index)
        mkt = _signal_frame(session, MARKET, start_ms, end_ms).set_index("open_time").reindex(index)
    finally:
        if own:
            session.close()
    for name in ("mentions", "sources", "burst_z", "polarity", "llm_score"):
        out[f"news_{name}"] = pd.to_numeric(sig[name], errors="coerce").fillna(0.0).to_numpy()
    for cat in ("listing", "delisting", "hack_exploit", "regulation", "lawsuit", "etf", "unlock_supply", "partnership_adoption", "macro", "outage"):
        out[f"news_cat_{cat}"] = [int((c or {}).get(cat, 0)) if isinstance(c, dict) else 0 for c in sig["categories"]]
    out["mkt_mentions"] = pd.to_numeric(mkt["mentions"], errors="coerce").fillna(0.0).to_numpy()
    out["mkt_polarity"] = pd.to_numeric(mkt["polarity"], errors="coerce").fillna(0.0).to_numpy()
    out["mkt_burst_z"] = pd.to_numeric(mkt["burst_z"], errors="coerce").fillna(0.0).to_numpy()
    fng = history.load_series("fear_greed")
    out["fear_greed"] = _asof(index, fng[fng["metric"] == "fear_greed"], "value")
    out = out.join(positioning_features(symbol, index))
    base = next(iter(base_assets({symbol})), symbol.removesuffix("USDT"))
    for name, metric in (("wiki", "wiki_views"), ("gdelt", "gdelt_volume")):
        series = history.load_series(name)
        series = series[(series["key"] == base) & (series["metric"] == metric)]
        z = _daily_z(series) if len(series) else series.assign(z=[])
        out[f"{name}_z"] = _asof(index, z, "z", lag_ms=DAILY_LAG_HOURS[name] * HOUR_MS)
    return out


def positioning_features(symbol: str, index: pd.Index) -> pd.DataFrame:
    """OI and long/short ratios from the metrics archive (REST positioning cache fills recent hours)."""
    arch = history.load_metrics(symbol).set_index("open_time")
    rest = history.load_series("positioning")
    if len(rest):
        rest = rest[rest["key"] == symbol].pivot_table(index="ts", columns="metric", values="value")
        rename = {"open_interest": "oi_value", "taker_buy_sell_ratio": "taker_ratio"}
        rest = rest.rename(columns=rename)
        arch = rest.combine_first(arch) if arch.empty else arch.combine_first(rest)
    cols = ["oi_value", "top_account_ratio", "top_position_ratio", "global_account_ratio", "taker_ratio"]
    arch = arch.reindex(columns=cols)
    full = arch.reindex(arch.index.union(index)).sort_index().ffill(limit=2)
    out = pd.DataFrame(index=index)
    for c in cols:
        out[c] = full[c].reindex(index).to_numpy(dtype=float)
    oi = full["oi_value"].astype(float)
    out["oi_chg_1h"] = (oi / oi.shift(1) - 1).reindex(index).to_numpy()
    out["oi_chg_24h"] = (oi / oi.shift(24) - 1).reindex(index).to_numpy()
    return out


def recent(session: Session, symbol: str, hours: int = 72) -> list[dict]:
    end = _floor_hour(int(datetime.now(UTC).timestamp() * 1000)) + HOUR_MS
    frame = _signal_frame(session, symbol, end - hours * HOUR_MS, end).sort_values("open_time")
    return [
        {
            "hour": datetime.fromtimestamp(r.open_time / 1000, UTC).isoformat(),
            **{k: getattr(r, k) for k in ("mentions", "sources", "polarity", "llm_score", "categories")},
            "burst_z": round(r.burst_z, 2),
        }
        for r in frame.itertuples()
        if r.mentions or symbol == MARKET
    ]
