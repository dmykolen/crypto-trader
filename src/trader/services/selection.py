"""Per-token strategy selection — walk-forward over the continuous strategy library.

For a token, every strategy x parameter set x risk overlay (leverage, ATR stop/take-profit) is backtested with
the shared engine. Time is cut into consecutive folds; at the start of each fold the selector picks the spec
with the best lower confidence bound of daily log-growth over the preceding `train_days`, and that spec trades
the fold. Concatenating the folds gives an equity curve that is entirely out-of-sample — the number to trust.

The same procedure run up to "now" yields the spec live trading should use for the token.
"""

import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from trader.services import features as fx
from trader.services import forecast, market_data, strategies
from trader.services.engine import BacktestResult, backtest, summarize

log = logging.getLogger(__name__)
LCB_Z = 1.0


@dataclass
class TokenStudy:
    symbol: str
    interval: str
    oos: BacktestResult
    folds: list[dict]
    current: dict
    regime: dict


def _daily_log_growth(equity: pd.Series) -> pd.Series:
    daily = equity.resample("1D").last().ffill()
    return np.log(daily.clip(lower=1e-9)).diff().dropna()


def _score(equity: pd.Series) -> float:
    g = _daily_log_growth(equity)
    if len(g) < 5 or equity.iloc[-1] <= 0:
        return -np.inf
    return float(g.mean() - LCB_Z * g.std(ddof=1) / np.sqrt(len(g)))


def _run(spec: strategies.Spec, bars: pd.DataFrame, funding: np.ndarray, target: np.ndarray, atr_pct: np.ndarray, margin_frac: float) -> BacktestResult:
    return backtest(bars, funding, target, leverage=spec.leverage, margin_frac=margin_frac, sl=spec.sl_atr * atr_pct, tp=spec.tp_atr * atr_pct)


def study(
    symbol: str,
    start: datetime,
    end: datetime,
    *,
    interval: str = "15m",
    train_days: int = 60,
    fold_days: int = 7,
    margin_frac: float = 1.0,
    with_ml: bool = True,
) -> TokenStudy:
    """Walk-forward strategy selection for one token between `start` and `end` (warm-up included in `start`)."""
    bars, funding = market_data.load_bars(symbol, interval, start, end)
    if len(bars) < 2000:
        raise ValueError(f"{symbol}: not enough {interval} bars ({len(bars)})")
    atr_pct = (fx.atr(bars, 14) / bars.close).shift(1).bfill().to_numpy()
    specs = strategies.specs()
    targets = {s: strategies.signal(s, bars) for s in {strategies.Spec(s.name, s.params, 1, 0, 0) for s in specs}}
    if with_ml:
        bars_per_day = int(86_400_000 / market_data.binance.INTERVAL_MS[interval])
        pred = forecast.walk_forward(bars, funding, horizon=bars_per_day // 4, train_bars=bars_per_day * train_days, step_bars=bars_per_day * fold_days)
        for th in (0.04, 0.08):
            base = strategies.Spec("ml_forecast", (("threshold", th), ("horizon", bars_per_day // 4)), 1, 0, 0)
            targets[base] = forecast.ml_signal(pred, th)
            specs += [strategies.Spec(base.name, base.params, lev, sl, tp) for lev, sl, tp in strategies.RISK_GRID]
    results = {s: _run(s, bars, funding, targets[strategies.Spec(s.name, s.params, 1, 0, 0)], atr_pct, margin_frac) for s in specs}
    idx = results[specs[0]].equity.index
    returns = {s: r.equity.pct_change().fillna(0.0).to_numpy() for s, r in results.items()}

    first = idx[0] + pd.Timedelta(days=train_days)
    stitched = np.zeros(len(idx))
    folds = []
    cursor = first
    while cursor < idx[-1]:
        fold_end = cursor + pd.Timedelta(days=fold_days)
        train = (idx >= cursor - pd.Timedelta(days=train_days)) & (idx < cursor)
        test = (idx >= cursor) & (idx < fold_end)
        scores = {s: _score(pd.Series(np.cumprod(1 + returns[s][train]), index=idx[train])) for s in specs}
        best = max(scores, key=lambda s: scores[s])
        if scores[best] > 0:
            stitched[test] = returns[best][test]
        fold_equity = pd.Series(np.cumprod(1 + (returns[best][test] if scores[best] > 0 else np.zeros(test.sum()))), index=idx[test])
        folds.append({
            "from": str(cursor.date()),
            "to": str(min(fold_end, idx[-1]).date()),
            "spec": best.describe() if scores[best] > 0 else "flat (no positive edge in training window)",
            "train_score": round(scores[best], 5),
            "fold_return_pct": round(float(fold_equity.iloc[-1] - 1) * 100, 2) if len(fold_equity) else 0.0,
        })
        cursor = fold_end
    oos_mask = idx >= first
    equity = pd.Series(1000 * np.cumprod(1 + stitched[oos_mask]), index=idx[oos_mask])
    trades = pd.DataFrame(columns=["ret", "reason"])
    oos = BacktestResult(equity, trades, 1000.0, summarize(equity, trades, 1000.0))
    recent = idx >= idx[-1] - pd.Timedelta(days=train_days)
    scores = {s: _score(pd.Series(np.cumprod(1 + returns[s][recent]), index=idx[recent])) for s in specs}
    best = max(scores, key=lambda s: scores[s])
    current = {"spec": asdict(best), "describe": best.describe(), "score": round(scores[best], 5), "tradable": scores[best] > 0}
    return TokenStudy(symbol, interval, oos, folds, current, fx.regime(bars))


def default_window(days: int = 365, warmup_days: int = 60) -> tuple[datetime, datetime]:
    end = (datetime.now(tz=market_data.UTC) - market_data.ARCHIVE_LAG).replace(hour=0, minute=0, second=0, microsecond=0)
    return end - timedelta(days=days + warmup_days), end
