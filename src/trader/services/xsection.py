import itertools
import logging
import math

import numpy as np
import pandas as pd

from trader.services import universe

log = logging.getLogger(__name__)

HOUR_MS = 3_600_000


def stats(ret: pd.Series, capital: float = 1000.0) -> dict:
    ret = ret.fillna(0.0)
    equity = capital * (1 + ret.clip(lower=-1.0)).cumprod()
    curve = np.concatenate([[capital], equity.to_numpy()])
    final = float(equity.iloc[-1]) if len(equity) else capital
    std = float(ret.std()) if len(ret) > 1 else 0.0
    return {
        "days": len(ret),
        "final_equity": round(final, 2),
        "geo_daily_pct": round(((final / capital) ** (1 / max(len(ret), 1)) - 1) * 100, 4) if final > 0 else -100.0,
        "mean_daily_pct": round(float(ret.mean()) * 100, 4),
        "median_daily_pct": round(float(ret.median()) * 100, 4),
        "sharpe_annual": round(float(ret.mean()) / std * math.sqrt(365), 2) if std > 0 else None,
        "share_days_positive": round(float((ret > 0).mean()), 3),
        "share_days_ge_10pct": round(float((ret >= 0.1).mean()), 4),
        "share_days_le_minus_10pct": round(float((ret <= -0.1).mean()), 4),
        "best_day_pct": round(float(ret.max()) * 100, 2),
        "worst_day_pct": round(float(ret.min()) * 100, 2),
        "max_drawdown_pct": round(float((curve / np.maximum.accumulate(curve) - 1).min()) * 100, 2),
    }


class Matrices:
    def __init__(self, panel: dict[str, pd.DataFrame]) -> None:
        self.close = universe.wide(panel, "close").ffill()
        self.qv = universe.wide(panel, "quote_volume")
        self.fund = universe.wide(panel, "funding").fillna(0.0)
        self.liquid24 = self.qv.rolling(24, min_periods=24).sum()
        self.fund24 = self.fund.rolling(24, min_periods=1).sum()
        self.vratio = self.qv / self.qv.rolling(168, min_periods=48).median().shift(1)

    def forward(self, hold: int) -> tuple[pd.DataFrame, pd.DataFrame]:
        fwd = self.close.shift(-hold) / self.close - 1
        paid = self.fund[::-1].rolling(hold, min_periods=1).sum()[::-1].shift(-1)
        return fwd, paid


SIGNALS = {
    "ret1": lambda m: m.close / m.close.shift(1) - 1,
    "ret4": lambda m: m.close / m.close.shift(4) - 1,
    "ret24": lambda m: m.close / m.close.shift(24) - 1,
    "ret72": lambda m: m.close / m.close.shift(72) - 1,
    "ret168": lambda m: m.close / m.close.shift(168) - 1,
    "fund24": lambda m: m.fund24,
    "vratio": lambda m: m.vratio,
}


def portfolio(m: Matrices, signal: pd.DataFrame, hold: int, k: int, sign: int, min_qv24: float = 5e6, cost: float = 0.0008) -> pd.Series:
    fwd, paid = m.forward(hold)
    times = m.close.index[(m.close.index // HOUR_MS) % hold == hold - 1]
    sig, f, p, liq = signal.loc[times], fwd.loc[times], paid.loc[times], m.liquid24.loc[times] >= min_qv24
    rows = {}
    for t in times:
        ok = liq.loc[t] & sig.loc[t].notna() & f.loc[t].notna()
        if int(ok.sum()) < 4 * k:
            continue
        ranked = sig.loc[t][ok].sort_values()
        low, high = ranked.index[:k], ranked.index[-k:]
        longs, shorts = (high, low) if sign > 0 else (low, high)
        r_long = float((f.loc[t, longs] - p.loc[t, longs]).mean())
        r_short = float((-f.loc[t, shorts] + p.loc[t, shorts]).mean())
        rows[t + HOUR_MS] = 0.5 * (r_long + r_short) - 2 * cost
    return pd.Series(rows, dtype="float64")


def to_daily(period_returns: pd.Series) -> pd.Series:
    days = pd.to_datetime(period_returns.index, unit="ms", utc=True).strftime("%Y-%m-%d")
    return (1 + period_returns).groupby(days).prod() - 1


def configs() -> list[tuple[str, int, int, int]]:
    return list(itertools.product(SIGNALS, (8, 24), (5, 10, 20), (1, -1)))


def run_all(panel: dict[str, pd.DataFrame]) -> dict[tuple, pd.Series]:
    m = Matrices(panel)
    out = {}
    cache = {name: fn(m) for name, fn in SIGNALS.items()}
    for name, hold, k, sign in configs():
        out[(name, hold, k, sign)] = to_daily(portfolio(m, cache[name], hold, k, sign))
        log.info("xs %s hold=%d k=%d sign=%+d mean=%.4f", name, hold, k, sign, out[(name, hold, k, sign)].mean())
    return out


def walk_forward(daily: dict[tuple, pd.Series], lookback_days: int = 90, min_days: int = 60) -> tuple[pd.Series, list]:
    frame = pd.DataFrame(daily).sort_index().fillna(0.0)
    chosen, picks = [], []
    for i, day in enumerate(frame.index):
        past = frame.iloc[max(0, i - lookback_days) : i]
        if len(past) < min_days:
            continue
        score = past.mean() / past.std().replace(0, np.nan)
        best = score.idxmax()
        if not np.isfinite(score[best]) or score[best] <= 0:
            chosen.append((day, 0.0))
            picks.append((day, None))
            continue
        chosen.append((day, float(frame.loc[day, best])))
        picks.append((day, best))
    return pd.Series(dict(chosen), dtype="float64"), picks


def study(panel: dict[str, pd.DataFrame], holdout: str = "2026-07-01", leverages: tuple[float, ...] = (1.0, 2.0, 3.0, 5.0)) -> dict:
    daily = run_all(panel)
    frame = pd.DataFrame(daily).sort_index().fillna(0.0)
    dev_mask = frame.index < holdout
    in_sample = {f"{n}|h{h}|k{k}|{'mom' if s > 0 else 'rev'}": stats(frame.loc[dev_mask, (n, h, k, s)]) for n, h, k, s in frame.columns}
    best = sorted(in_sample.items(), key=lambda kv: -(kv[1]["sharpe_annual"] or -99))[:8]
    out = {"configs": len(frame.columns), "dev_in_sample_top8_NOT_tradable": dict(best), "walk_forward": {}}
    for lookback in (30, 90, 180):
        wf, picks = walk_forward(daily, lookback_days=lookback, min_days=min(60, lookback))
        dev, hold = wf[wf.index < holdout], wf[wf.index >= holdout]
        out["walk_forward"][f"lookback{lookback}"] = {f"lev{lev:g}": {"dev": stats((lev * dev).clip(lower=-1)), "holdout": stats((lev * hold).clip(lower=-1))} for lev in leverages}
        out["walk_forward"][f"lookback{lookback}"]["last_picks"] = [str(p) for p in picks[-5:]]
    return out
