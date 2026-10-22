"""Multi-horizon price forecaster — LightGBM on causal technical features, trained walk-forward.

For each horizon h (in bars) the model estimates P(close[i+h] > close[i]) and the expected log-return. Training
is strictly walk-forward: a model is fitted on bars that ended at least h bars before the first prediction
(an embargo, so overlapping labels never leak), then predicts the next block, then is refitted.

`forecast()` answers "where is this price going over the next hours/days" for the API and the AI analyst, with the
out-of-sample AUC / hit-rate of the same model on the same market next to every number; `ml_signal()` turns
out-of-sample probabilities into a target position for the strategy selector.
"""

from dataclasses import dataclass

import lightgbm as lgb
import numpy as np
import pandas as pd

from trader.services.features import feature_frame

PARAMS = {
    "n_estimators": 200,
    "learning_rate": 0.03,
    "num_leaves": 15,
    "min_child_samples": 200,
    "subsample": 0.7,
    "subsample_freq": 1,
    "colsample_bytree": 0.7,
    "reg_lambda": 5.0,
    "verbose": -1,
}


@dataclass
class OOSPrediction:
    horizon: int
    prob_up: pd.Series  # out-of-sample P(up over `horizon` bars), NaN where no model existed yet
    exp_ret: pd.Series  # out-of-sample expected log-return
    auc: float | None  # AUC of the out-of-sample probabilities
    hit_rate: float | None  # directional accuracy where |p - 0.5| > 0.05


def _labels(close: pd.Series, horizon: int) -> pd.Series:
    return np.log(close.shift(-horizon) / close)


def _auc(y: np.ndarray, p: np.ndarray) -> float | None:
    pos, neg = p[y == 1], p[y == 0]
    if len(pos) < 20 or len(neg) < 20:
        return None
    ranks = pd.Series(np.concatenate([pos, neg])).rank().to_numpy()
    return float((ranks[: len(pos)].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))


def _fit(x: pd.DataFrame, y: pd.Series) -> tuple[lgb.LGBMClassifier, lgb.LGBMRegressor]:
    cls = lgb.LGBMClassifier(**PARAMS).fit(x, (y > 0).astype(int))
    reg = lgb.LGBMRegressor(**PARAMS).fit(x, y.clip(y.quantile(0.01), y.quantile(0.99)))
    return cls, reg


def walk_forward(bars: pd.DataFrame, funding: np.ndarray, horizon: int, *, train_bars: int, step_bars: int) -> OOSPrediction:
    """Rolling-window training (`train_bars`), refit every `step_bars`, embargo of `horizon` bars."""
    x = feature_frame(bars, funding)
    y = _labels(bars.close, horizon)
    usable = x.notna().sum(axis=1).gt(len(x.columns) // 2)
    prob = pd.Series(np.nan, index=bars.index)
    exp = pd.Series(np.nan, index=bars.index)
    for t0 in range(train_bars, len(bars), step_bars):
        fit_end = t0 - horizon  # labels of rows < fit_end are known at t0
        window = slice(max(0, fit_end - train_bars), fit_end)
        ok = y.iloc[window].notna() & usable.iloc[window]
        if ok.sum() < 500:
            continue
        cls, reg = _fit(x.iloc[window][ok], y.iloc[window][ok])
        block = slice(t0, min(t0 + step_bars, len(bars)))
        prob.iloc[block] = cls.predict_proba(x.iloc[block])[:, 1]
        exp.iloc[block] = reg.predict(x.iloc[block])
    valid = prob.notna() & y.notna()
    yy, pp = (y[valid] > 0).astype(int).to_numpy(), prob[valid].to_numpy()
    confident = np.abs(pp - 0.5) > 0.05
    hit = float(((pp[confident] > 0.5) == yy[confident]).mean()) if confident.sum() > 50 else None
    return OOSPrediction(horizon, prob, exp, _auc(yy, pp) if valid.any() else None, hit)


def ml_signal(pred: OOSPrediction, threshold: float) -> np.ndarray:
    """Long when P(up) > 0.5 + threshold, short when < 0.5 - threshold; decided on close, filled next open."""
    p = pred.prob_up
    side = pd.Series(np.where(p > 0.5 + threshold, 1, np.where(p < 0.5 - threshold, -1, 0)), index=p.index)
    return side.shift(1).fillna(0).to_numpy(np.int64)


def forecast(bars: pd.DataFrame, funding: np.ndarray, horizons: dict[str, int], train_bars: int = 20_000) -> dict[str, dict]:
    """Fit on the most recent history and forecast from the last bar, per named horizon (in bars).

    Each horizon also reports the walk-forward AUC / hit-rate of the same model family on this market, so the
    forecast comes with an honest measure of how much it is worth (AUC 0.5 = coin flip).
    """
    x = feature_frame(bars, funding)
    usable = x.notna().sum(axis=1).gt(len(x.columns) // 2)
    train_bars = min(train_bars, len(bars) * 2 // 3)
    last_close = float(bars.close.iloc[-1])
    out = {}
    for name, h in horizons.items():
        y = _labels(bars.close, h)
        ok = y.notna() & usable
        cls, reg = _fit(x[ok].iloc[-train_bars:], y[ok].iloc[-train_bars:])
        oos = walk_forward(bars, funding, h, train_bars=train_bars // 2, step_bars=max(h, len(bars) // 15))
        last = x.iloc[[-1]]
        p, e = float(cls.predict_proba(last)[0, 1]), float(reg.predict(last)[0])
        out[name] = {
            "horizon_bars": h,
            "prob_up": round(p, 3),
            "expected_return_pct": round((np.exp(e) - 1) * 100, 3),
            "target_price": round(last_close * float(np.exp(e)), 8),
            "oos_auc": None if oos.auc is None else round(oos.auc, 3),
            "oos_hit_rate": None if oos.hit_rate is None else round(oos.hit_rate, 3),
        }
    return out
