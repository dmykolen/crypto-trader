import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from itertools import product

import numpy as np
import pandas as pd
from numba import njit

from trader.core.config import settings
from trader.quant import indicators as ind
from trader.quant.model import STABLES, root, universe_dir

DAY = 86_400_000
FEE = 0.0005
SLIP = 0.0003
COST = FEE + SLIP


def _ms(text: str) -> int:
    return int(datetime.fromisoformat(text).replace(tzinfo=UTC).timestamp() * 1000)


DEV_START, DEV_END, END = _ms("2023-07-01"), _ms("2025-01-01"), _ms("2026-10-01")


def _daily(symbol: str) -> pd.DataFrame | None:
    h = pd.read_parquet(universe_dir() / f"{symbol}.parquet", columns=["open_time", "open", "high", "low", "close", "quote_volume", "funding"])
    if len(h) < 24 * 150:
        return None
    g = h.groupby(h.open_time // DAY * DAY)
    d = pd.DataFrame({
        "open": g.open.first(),
        "high": g.high.max(),
        "low": g.low.min(),
        "close": g.close.last(),
        "qv": g.quote_volume.sum(),
        "funding": g.funding.sum(),
        "hours": g.size(),
    })
    d = d[d.hours >= 20].drop(columns="hours")
    d["symbol"] = symbol
    return d.rename_axis("day").reset_index()


def build_daily() -> pd.DataFrame:
    symbols = [p.stem for p in sorted(universe_dir().glob("*.parquet")) if p.stem.removesuffix("USDT") not in STABLES]
    with ThreadPoolExecutor(12) as pool:
        frames = [f for f in pool.map(_daily, symbols) if f is not None]
    df = pd.concat(frames, ignore_index=True)
    root().mkdir(parents=True, exist_ok=True)
    df.to_parquet(root() / "daily.parquet", index=False)
    return df


@dataclass
class Panel:
    days: np.ndarray
    symbols: np.ndarray
    o: pd.DataFrame
    h: pd.DataFrame
    low: pd.DataFrame
    c: pd.DataFrame
    qv: pd.DataFrame
    funding: pd.DataFrame
    r: pd.DataFrame


def load_panel() -> Panel:
    path = root() / "daily.parquet"
    df = pd.read_parquet(path) if path.exists() else build_daily()
    wide = {k: df.pivot(index="day", columns="symbol", values=k).sort_index() for k in ("open", "high", "low", "close", "qv", "funding")}
    full = pd.RangeIndex(int(wide["close"].index.min()), int(wide["close"].index.max()) + DAY, DAY)
    wide = {k: v.reindex(full) for k, v in wide.items()}
    r = wide["close"].pct_change(fill_method=None)
    r = r.where((r > -0.95) & (r < 3.0))
    return Panel(full.to_numpy(), wide["close"].columns.to_numpy(), wide["open"], wide["high"], wide["low"], wide["close"], wide["qv"], wide["funding"].fillna(0.0), r)


def universe(p: Panel, top: int, min_volume: float = 20e6, min_age: int = 120) -> pd.DataFrame:
    liquidity = p.qv.rolling(30, min_periods=20).mean()
    age = p.c.notna().cumsum()
    ok = (liquidity >= min_volume) & (age >= min_age) & p.c.notna()
    rank = liquidity.where(ok).rank(axis=1, ascending=False)
    return (rank <= top) & ok


@njit(cache=True)
def _donchian(c: np.ndarray, hi_in: np.ndarray, lo_in: np.ndarray, hi_out: np.ndarray, lo_out: np.ndarray) -> np.ndarray:
    t_len, n = c.shape
    pos = np.zeros((t_len, n))
    for j in range(n):
        p = 0.0
        for t in range(t_len):
            x = c[t, j]
            if x != x:
                p = 0.0
            elif p >= 0 and x > hi_in[t, j]:
                p = 1.0
            elif p <= 0 and x < lo_in[t, j]:
                p = -1.0
            elif (p > 0 and x < lo_out[t, j]) or (p < 0 and x > hi_out[t, j]):
                p = 0.0
            pos[t, j] = p
    return pos


def _supertrend(p: Panel, mult: float) -> pd.DataFrame:
    out = np.zeros(p.c.shape)
    for j in range(p.c.shape[1]):
        c = p.c.iloc[:, j].to_numpy(np.float64)
        ok = np.isfinite(c)
        if ok.sum() < 30:
            continue
        idx = np.flatnonzero(ok)
        h, low, cc = p.h.iloc[idx, j].to_numpy(np.float64), p.low.iloc[idx, j].to_numpy(np.float64), c[idx]
        direction, _ = ind.supertrend(h, low, cc, ind.atr(h, low, cc, 14), mult)
        out[idx, j] = direction
    return pd.DataFrame(out, index=p.c.index, columns=p.c.columns)


def signals(p: Panel) -> dict[str, pd.DataFrame]:
    c = p.c
    out: dict[str, pd.DataFrame] = {}
    for n in (7, 14, 30, 60, 90):
        out[f"tsmom_{n}"] = np.sign(c / c.shift(n) - 1)
    for fast, slow in ((5, 20), (10, 50), (20, 100), (50, 200)):
        out[f"ema_{fast}_{slow}"] = np.sign(c.ewm(span=fast, adjust=False, min_periods=fast).mean() - c.ewm(span=slow, adjust=False, min_periods=slow).mean())
    for n in (20, 55):
        k = n // 2
        hi_in, lo_in = p.h.rolling(n, min_periods=n).max().shift(1), p.low.rolling(n, min_periods=n).min().shift(1)
        hi_out, lo_out = p.h.rolling(k, min_periods=k).max().shift(1), p.low.rolling(k, min_periods=k).min().shift(1)
        arrays = [x.to_numpy(np.float64) for x in (c, hi_in, lo_in, hi_out, lo_out)]
        out[f"donchian_{n}"] = pd.DataFrame(_donchian(*arrays), index=c.index, columns=c.columns)
    for mult in (2.0, 3.0):
        out[f"supertrend_{mult:g}"] = _supertrend(p, mult)
    clean = {k: v.where(c.notna()).fillna(0.0) for k, v in out.items()}
    fast_keys = ("tsmom_7", "tsmom_14", "ema_5_20", "donchian_20", "supertrend_2")
    slow_keys = ("tsmom_60", "tsmom_90", "ema_20_100", "ema_50_200", "donchian_55")
    clean["ensemble_fast"] = sum(clean[k] for k in fast_keys) / len(fast_keys)
    clean["ensemble_slow"] = sum(clean[k] for k in slow_keys) / len(slow_keys)
    clean["ensemble_all"] = sum(v for k, v in clean.items() if not k.startswith("ensemble")) / 13
    return clean


@dataclass(frozen=True)
class Sizing:
    top: int = 40
    target_vol: float = 0.03
    max_gross: float = 3.0
    side: str = "both"
    band: float = 0.25

    def describe(self) -> str:
        sides = {"both": "long+short", "long": "long only", "short": "short only"}[self.side]
        return f"{sides}, top {self.top} by liquidity, target {self.target_vol:.0%}/day vol, gross ≤ {self.max_gross:g}x"


def returns(p: Panel, sig: pd.DataFrame, sizing: Sizing, eligible: pd.DataFrame) -> pd.Series:
    s = sig.where(eligible, 0.0)
    if sizing.side == "long":
        s = s.clip(lower=0)
    elif sizing.side == "short":
        s = s.clip(upper=0)
    vol = p.r.rolling(30, min_periods=20).std().clip(lower=0.01)
    base = (s / vol).fillna(0.0)
    active = (base != 0).sum(axis=1).replace(0, np.nan)
    base = base.div(active, axis=0).fillna(0.0)
    r_next = p.r.shift(-1).fillna(0.0)
    unscaled = (base * r_next).sum(axis=1).shift(1)
    realized = unscaled.rolling(30, min_periods=10).std()
    gross_base = base.abs().sum(axis=1)
    scale = (sizing.target_vol / realized).clip(upper=sizing.max_gross / gross_base.replace(0, np.nan)).fillna(0.0)
    w = base.mul(scale, axis=0)
    w = _banded(w.to_numpy(), sizing.band)
    w = pd.DataFrame(w, index=base.index, columns=base.columns)
    pnl = (w * r_next).sum(axis=1)
    turnover = (w - w.shift(1).fillna(0.0)).abs().sum(axis=1)
    funding = (w * p.funding.shift(-1).fillna(0.0)).sum(axis=1)
    return (pnl - COST * turnover - funding).shift(1).fillna(0.0)


@njit(cache=True)
def _banded(w: np.ndarray, band: float) -> np.ndarray:
    out = np.zeros_like(w)
    t_len, n = w.shape
    for j in range(n):
        held = 0.0
        for t in range(t_len):
            target = w[t, j]
            if target == 0.0 or held == 0.0 or np.sign(target) != np.sign(held) or abs(target - held) > band * abs(held):
                held = target
            out[t, j] = held
    return out


def stats(ret: pd.Series, start: int, end: int) -> dict:
    r = ret[(ret.index >= start) & (ret.index < end)]
    if r.empty:
        return {}
    eq = (1 + r).cumprod()
    dd = eq / eq.cummax() - 1
    return {
        "final_equity": round(1000 * float(eq.iloc[-1]), 2),
        "return_pct": round(100 * (float(eq.iloc[-1]) - 1), 1),
        "mean_daily_pct": round(100 * float(r.mean()), 3),
        "sharpe": round(float(r.mean() / r.std() * np.sqrt(365)) if r.std() > 0 else 0.0, 2),
        "max_drawdown_pct": round(100 * float(dd.min()), 1),
        "positive_days_pct": round(100 * float((r > 0).mean()), 1),
        "days_10pct_plus": int((r >= 0.10).sum()),
        "worst_day_pct": round(100 * float(r.min()), 1),
        "days": len(r),
    }


def walk_forward_pick(streams: dict[str, pd.Series], lookback: int = 365, top: int = 1) -> tuple[pd.Series, list[dict]]:
    frame = pd.DataFrame(streams)
    months = pd.to_datetime(frame.index, unit="ms", utc=True).to_period("M")
    out = pd.Series(0.0, index=frame.index)
    picks = []
    for month in months.unique():
        here = months == month
        first = int(frame.index[here][0])
        past = frame[(frame.index < first) & (frame.index >= first - lookback * DAY)]
        if len(past) < 120:
            continue
        sharpe = past.mean() / past.std().replace(0, np.nan)
        best = sharpe.sort_values(ascending=False).index[:top]
        out[here] = frame.loc[here, best].mean(axis=1)
        picks.append({"month": str(month), "picked": list(best), "trailing_sharpe": round(float(sharpe[best].mean() * np.sqrt(365)), 2)})
    return out, picks


def study() -> dict:
    p = load_panel()
    sigs = signals(p)
    sizings = [Sizing(top=t, target_vol=v, max_gross=g, side=s) for t, v, g, s in product((20, 40), (0.02, 0.04), (3.0, 5.0), ("both", "long", "short"))]
    eligible = {t: universe(p, t) for t in (20, 40)}
    streams: dict[str, pd.Series] = {}
    table = []
    for (name, sig), sz in product(sigs.items(), sizings):
        key = f"{name} | {sz.describe()}"
        ret = returns(p, sig, sz, eligible[sz.top])
        streams[key] = ret
        table.append({
            "config": key,
            "rule": name,
            **asdict(sz),
            "dev": stats(ret, DEV_START, DEV_END),
            "holdout": stats(ret, DEV_END, END),
            "y2022": stats(ret, _ms("2022-07-01"), DEV_START),
        })
    picked, picks = walk_forward_pick(streams)
    picked3, _ = walk_forward_pick(streams, top=3)
    best_dev = max(table, key=lambda x: x["dev"].get("sharpe", -9))
    doc = {
        "universe_days": len(p.days),
        "symbols": len(p.symbols),
        "configs": len(table),
        "costs": {"per_unit_turnover": COST, "funding": "charged daily from the archive"},
        "best_on_dev": {"config": best_dev["config"], "dev": best_dev["dev"], "holdout": best_dev["holdout"], "y2022": best_dev["y2022"]},
        "walk_forward_top1": {"dev": stats(picked, DEV_START, DEV_END), "holdout": stats(picked, DEV_END, END), "y2022": stats(picked, _ms("2022-07-01"), DEV_START)},
        "walk_forward_top3": {"dev": stats(picked3, DEV_START, DEV_END), "holdout": stats(picked3, DEV_END, END)},
        "picks": picks,
        "holdout_share_positive": round(float(np.mean([row["holdout"].get("return_pct", 0) > 0 for row in table])), 3),
        "table": table,
    }
    pd.DataFrame({"walk_forward_top1": picked, "walk_forward_top3": picked3}).to_parquet(root() / "trend_streams.parquet")
    out = settings.reports_dir / "quant"
    out.mkdir(parents=True, exist_ok=True)
    (out / "trend.json").write_text(json.dumps(doc, indent=2, default=str))
    return doc
