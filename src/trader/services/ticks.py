import io
import itertools
import logging
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import numpy as np
import pandas as pd
from sqlmodel import Session

from trader.core.config import settings
from trader.integrations import binance
from trader.services import market_data, playbooks
from trader.services.engine import liquidation_distance
from trader.services.playbooks import STOP_BEFORE_LIQ

log = logging.getLogger(__name__)

NAMES = ["agg_trade_id", "price", "quantity", "first_trade_id", "last_trade_id", "transact_time", "is_buyer_maker"]
LATENCIES_S = (0.5, 1, 2, 3, 5, 10, 20, 30, 60)
HOLDS_S = (5, 15, 30, 60, 120, 300, 600, 1800)
BEFORE_S, AFTER_S = 60, 2400


def as_latency(value: float) -> float:
    for latency in LATENCIES_S:
        if float(latency) == float(value):
            return latency
    raise ValueError(f"latency must be one of {LATENCIES_S}, got {value}")


def _day(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, UTC).strftime("%Y-%m-%d")


def window(symbol: str, ts: int) -> pd.DataFrame | None:
    path = settings.data_dir / "ticks" / symbol / f"{ts}.parquet"
    if path.exists():
        df = pd.read_parquet(path)
        return df if len(df) else None
    lo, hi = ts - BEFORE_S * 1000, ts + AFTER_S * 1000
    frames = []
    for day in sorted({_day(lo), _day(hi)}):
        raw = binance._archive_get(f"data/futures/um/daily/aggTrades/{symbol}/{symbol}-aggTrades-{day}.zip")
        if raw is None:
            continue
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            body = archive.read(archive.namelist()[0])
        df = pd.read_csv(io.BytesIO(body), header=None if body[:1].isdigit() else 0, names=NAMES, usecols=["price", "quantity", "transact_time", "is_buyer_maker"])
        del body, raw
        frames.append(df[(df.transact_time >= lo) & (df.transact_time < hi)])
    df = (
        pd.concat(frames, ignore_index=True).sort_values("transact_time", ignore_index=True)
        if frames
        else pd.DataFrame(columns=["price", "quantity", "transact_time", "is_buyer_maker"])
    )
    df["is_buyer_maker"] = df.is_buyer_maker.astype(str).str.lower().eq("true")
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)
    return df if len(df) else None


def clean(df: pd.DataFrame, band: float = 0.3) -> pd.DataFrame:
    if len(df) < 5:
        return df
    median = df.price.rolling(21, center=True, min_periods=3).median()
    return df[(df.price / median - 1).abs() <= band].reset_index(drop=True)


def reactions(df: pd.DataFrame, ts: int, fill_s: float = 0.5) -> dict:
    df = clean(df)
    t = df.transact_time.to_numpy(np.int64)
    p = df.price.to_numpy(np.float64)
    before = np.searchsorted(t, ts) - 1
    if before < 0:
        return {}
    ref = p[before]
    out = {"ref": ref, "first_trade_s": round((t[before + 1] - ts) / 1000, 3) if before + 1 < len(t) else None}
    for latency in LATENCIES_S:
        i = int(np.searchsorted(t, ts + latency * 1000))
        i_end = int(np.searchsorted(t, ts + (latency + fill_s) * 1000, side="right"))
        if i >= len(t):
            continue
        fill = p[i : max(i_end, i + 1)]
        entry_long, entry_short = fill.max(), fill.min()
        out[f"pre_{latency}"] = p[i] / ref - 1
        for hold in HOLDS_S:
            j = int(np.searchsorted(t, ts + (latency + hold) * 1000))
            j_end = int(np.searchsorted(t, ts + (latency + hold + fill_s) * 1000, side="right"))
            if j <= i or j >= len(t):
                continue
            seg = p[i : max(j_end, j + 1)]
            exit_fill = p[j : max(j_end, j + 1)]
            out[f"rl_{latency}_{hold}"] = exit_fill.min() / entry_long - 1
            out[f"rs_{latency}_{hold}"] = exit_fill.max() / entry_short - 1
            out[f"mfel_{latency}_{hold}"] = seg.max() / entry_long - 1
            out[f"mael_{latency}_{hold}"] = seg.min() / entry_long - 1
            out[f"mfes_{latency}_{hold}"] = seg.max() / entry_short - 1
            out[f"maes_{latency}_{hold}"] = seg.min() / entry_short - 1
    return out


def restudy(fill_s: float = 0.5) -> pd.DataFrame:
    base = pd.read_parquet(settings.reports_dir / "lab" / "tick_reactions.parquet")[["type", "symbol", "ts", "time", "title"]]
    rows = []
    for row in base.itertuples(index=False):
        path = settings.data_dir / "ticks" / row.symbol / f"{row.ts}.parquet"
        if not path.exists():
            continue
        df = pd.read_parquet(path)
        if df.empty:
            continue
        rows.append(row._asdict() | reactions(df, int(row.ts), fill_s))
    frame = pd.DataFrame(rows).sort_values("ts", ignore_index=True)
    frame.to_parquet(settings.reports_dir / "lab" / "tick_reactions_v2.parquet", index=False)
    return frame


def study(session: Session, workers: int = 6) -> pd.DataFrame:
    events = playbooks.notice_events(session)
    universe = market_data.perp_universe()

    def one(event) -> dict | None:
        etype, token, ts, title = event
        symbol = market_data.perp_symbol(token, universe)
        if symbol is None or ts > (datetime.now(UTC).timestamp() - 3 * 86400) * 1000:
            return None
        try:
            df = window(symbol, ts)
        except Exception as exc:
            log.warning("ticks %s %s: %s", symbol, ts, exc)
            return None
        if df is None or df.transact_time.iloc[0] > ts - 5000:
            return None
        return {"type": etype.value, "symbol": symbol, "ts": ts, "time": datetime.fromtimestamp(ts / 1000, UTC).isoformat(timespec="seconds"), "title": title} | reactions(df, ts)

    with ThreadPoolExecutor(workers) as pool:
        rows = [r for r in pool.map(one, events) if r]
    frame = pd.DataFrame(rows).sort_values("ts", ignore_index=True)
    path = settings.reports_dir / "lab" / "tick_reactions.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False)
    return frame


LEVERAGES = (1.0, 2.0, 3.0, 5.0, 10.0)
CANDIDATES = [
    (side, hold, lev, stop, tp)
    for side, hold, lev, stop, tp in itertools.product((1, -1), HOLDS_S, LEVERAGES, (0.0, 0.02, 0.05, 0.1), (0.0, 0.05, 0.1, 0.2))
    if stop == 0.0 or stop < STOP_BEFORE_LIQ * liquidation_distance(lev, side)
]


def describe(c: tuple) -> str:
    side, hold, lev, stop, tp = c
    return f"{'LONG' if side > 0 else 'SHORT'} {lev:g}x hold {hold}s" + (f" SL {stop:.0%}" if stop else "") + (f" TP {tp:.0%}" if tp else "")


def outcome_matrix(frame: pd.DataFrame, latency: float, fee: float = 0.0005, slip: float | None = None) -> np.ndarray:
    slip = slip if slip is not None else (0.005 if latency < 10 else 0.0015)
    out = np.full((len(frame), len(CANDIDATES)), np.nan)
    for j, (side, hold, lev, stop, tp) in enumerate(CANDIDATES):
        key, leg = f"{latency}_{hold}", "l" if side > 0 else "s"
        if f"r{leg}_{key}" not in frame:
            continue
        r, mfe, mae = (frame[f"{p}{leg}_{key}"].to_numpy(np.float64) for p in ("r", "mfe", "mae"))
        favorable, adverse = (mfe, -mae) if side > 0 else (-mae, mfe)
        stop_hit = (stop > 0) & (adverse >= stop)
        take_hit = (tp > 0) & (favorable >= tp) & ~stop_hit
        liquidated = (adverse >= liquidation_distance(lev, side)) & ~stop_hit
        move = np.where(stop_hit, -stop - slip, np.where(take_hit, tp, side * r))
        out[:, j] = np.maximum(np.where(liquidated, -1.0, lev * (move - 2 * slip - 2 * fee)), -1.0)
    return out


def walk_forward(frame: pd.DataFrame, latency: float, z: float = 1.0, min_history: int = 10, slip: float | None = None) -> pd.DataFrame:
    matrix = outcome_matrix(frame, latency, slip=slip)
    rows = []
    gap = (max(HOLDS_S) + max(LATENCIES_S)) * 1000
    for etype in sorted(frame.type.unique()):
        idx = np.flatnonzero(frame.type.to_numpy() == etype)
        ts = frame.ts.to_numpy()[idx]
        growth = np.log1p(np.clip(np.nan_to_num(matrix[idx], nan=0.0), -0.99, None))
        zero = np.zeros((1, growth.shape[1]))
        total, total2 = np.vstack([zero, np.cumsum(growth, axis=0)]), np.vstack([zero, np.cumsum(growth**2, axis=0)])
        for k, i in enumerate(idx):
            known = int(np.searchsorted(ts, ts[k] - gap, side="right"))
            best, _ = playbooks._select_running(total[known], total2[known], known, z) if known >= min_history else (None, None)
            ret = None if best is None or np.isnan(matrix[i, best]) else float(matrix[i, best])
            rows.append({
                "i": int(i),
                "type": etype,
                "ts": int(frame.ts.iat[i]),
                "symbol": frame.symbol.iat[i],
                "known": known,
                "candidate": describe(CANDIDATES[best]) if best is not None else None,
                "hold_s": CANDIDATES[best][1] if best is not None else None,
                "lev": CANDIDATES[best][2] if best is not None else None,
                "ret": ret,
            })
    return pd.DataFrame(rows).sort_values("ts", ignore_index=True)


def bucketed(frame: pd.DataFrame, latency: float, threshold: float = 0.02) -> pd.DataFrame:
    pre = frame[f"pre_{latency}"].fillna(0.0)
    bucket = np.where(pre >= threshold, "up", np.where(pre <= -threshold, "down", "flat"))
    return frame.assign(type=frame.type + "|" + bucket)


def latency_report(frame: pd.DataFrame, holdout: str = "2026-07-01", caps: tuple[float | None, ...] = (None, 25_000.0, 10_000.0)) -> dict:
    report = {}
    for latency in LATENCIES_S:
        row = {}
        for variant, data in (("by_type", frame), ("by_type_and_premove", bucketed(frame, latency))):
            decisions = walk_forward(data, latency)
            stamp = pd.to_datetime(decisions.ts, unit="ms", utc=True).dt.strftime("%Y-%m-%d")
            per_type = {}
            for etype, group in decisions.dropna(subset=["ret"]).groupby("type"):
                r = group.ret.to_numpy()
                per_type[etype] = {
                    "n": len(r),
                    "mean": round(float(r.mean()), 4),
                    "median": round(float(np.median(r)), 4),
                    "win": round(float((r > 0).mean()), 3),
                    "last": group.candidate.iloc[-1],
                }
            row[variant] = {"per_type": per_type}
            for cap in caps:
                tag = "uncapped" if cap is None else f"cap{int(cap / 1000)}k"
                row[variant][tag] = {
                    "all": account(decisions, cap_notional=cap),
                    "dev": account(decisions[stamp < holdout], last="2026-06-30", cap_notional=cap),
                    "holdout": account(decisions[stamp >= holdout], first=holdout, cap_notional=cap),
                }
        report[str(latency)] = row
    return report


def _account(decisions: pd.DataFrame, fraction: float, notice_cap: float, capital: float, first: str, last: str, cap_notional: float | None) -> dict:
    from trader.services.xsection import stats

    taken = decisions.dropna(subset=["ret"])
    equity, pnl_by_day = capital, {}
    for ts, group in taken.groupby("ts", sort=True):
        budget = min(fraction, notice_cap / len(group)) * equity
        pnl = 0.0
        for r, lev in zip(group.ret, group.lev, strict=True):
            margin = budget if cap_notional is None else min(budget, cap_notional / lev)
            pnl += margin * max(r, -1.0)
        equity += pnl
        day = datetime.fromtimestamp(ts / 1000, UTC).strftime("%Y-%m-%d")
        pnl_by_day[day] = pnl_by_day.get(day, 0.0) + pnl
    days = pd.date_range(first, last, freq="D").strftime("%Y-%m-%d")
    pnl = pd.Series(0.0, index=days).add(pd.Series(pnl_by_day, dtype="float64"), fill_value=0.0).loc[days]
    eq = capital + pnl.cumsum()
    ret = pnl / eq.shift(1).fillna(capital).clip(lower=1e-9)
    trades = taken.ret.to_numpy()
    return {
        "trades": len(trades),
        "mean_ret": round(float(trades.mean()), 4) if len(trades) else None,
        "median_ret": round(float(np.median(trades)), 4) if len(trades) else None,
        "win": round(float((trades > 0).mean()), 3) if len(trades) else None,
        "mean_daily_usd": round(float(pnl.mean()), 2),
        "share_days_ge_100usd": round(float((pnl >= 100).mean()), 4),
    } | stats(ret, capital)


def account(
    decisions: pd.DataFrame,
    fraction: float = 0.2,
    notice_cap: float = 0.3,
    capital: float = 1000.0,
    first: str = "2021-01-01",
    last: str = "2026-10-20",
    cap_notional: float | None = None,
) -> dict:
    return _account(decisions, fraction, notice_cap, capital, first, last, cap_notional)
