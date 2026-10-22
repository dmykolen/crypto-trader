"""Technical features — causal by construction: the value at bar i uses bars ≤ i only.

Strategies shift decisions by one bar (decide on close i, fill at open i+1), so nothing here may peek ahead.
"""

import numpy as np
import pandas as pd


def ema(x: pd.Series, span: int) -> pd.Series:
    return x.ewm(span=span, adjust=False, min_periods=span).mean()


def atr(bars: pd.DataFrame, n: int = 14) -> pd.Series:
    prev = bars.close.shift()
    tr = pd.concat([bars.high - bars.low, (bars.high - prev).abs(), (bars.low - prev).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    delta = close.diff()
    up = delta.clip(lower=0).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    down = (-delta.clip(upper=0)).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    return 100 - 100 / (1 + up / down.replace(0, np.nan))


def zscore(x: pd.Series, n: int) -> pd.Series:
    return (x - x.rolling(n).mean()) / x.rolling(n).std()


def adx(bars: pd.DataFrame, n: int = 14) -> pd.Series:
    up, down = bars.high.diff(), -bars.low.diff()
    plus = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=bars.index)
    minus = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=bars.index)
    rng = atr(bars, n)
    pdi = 100 * plus.ewm(alpha=1 / n, adjust=False).mean() / rng
    mdi = 100 * minus.ewm(alpha=1 / n, adjust=False).mean() / rng
    return (100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)).ewm(alpha=1 / n, adjust=False).mean()


def realized_vol(close: pd.Series, n: int) -> pd.Series:
    return np.log(close).diff().rolling(n).std()


def efficiency_ratio(close: pd.Series, n: int) -> pd.Series:
    """Kaufman: |net move| / path length over n bars — 1 = straight trend, 0 = pure noise."""
    return close.diff(n).abs() / close.diff().abs().rolling(n).sum()


def hurst(close: pd.Series, n: int = 256) -> pd.Series:
    """Rolling Hurst exponent from the variance of lagged differences (>0.5 trending, <0.5 mean-reverting)."""
    logp = np.log(close)
    lags = np.array([2, 4, 8, 16, 32])
    cols = [np.log(logp.diff(lag).rolling(n).std()) for lag in lags]
    stacked = np.vstack([c.to_numpy() for c in cols])
    x = np.log(lags) - np.log(lags).mean()
    slope = (x[:, None] * (stacked - stacked.mean(axis=0))).sum(axis=0) / (x**2).sum()
    return pd.Series(slope, index=close.index)


def feature_frame(bars: pd.DataFrame, funding: np.ndarray | None = None) -> pd.DataFrame:
    """The model's feature set: returns, trend, volatility, order flow, regime, funding, calendar."""
    c, v = bars.close, bars.quote_volume
    logc = np.log(c)
    f = pd.DataFrame(index=bars.index)
    for n in (1, 3, 6, 12, 24, 48, 96, 192):
        f[f"ret_{n}"] = logc.diff(n)
    for n in (12, 48, 192):
        f[f"vol_{n}"] = realized_vol(c, n)
        f[f"z_{n}"] = zscore(c, n)
        f[f"er_{n}"] = efficiency_ratio(c, n)
    a = atr(bars, 14)
    f["atr_pct"] = a / c
    f["range_pct"] = (bars.high - bars.low) / c
    f["close_pos"] = ((c - bars.low) / (bars.high - bars.low).replace(0, np.nan)).fillna(0.5)
    for fast, slow in ((12, 48), (48, 192)):
        f[f"ema_gap_{fast}_{slow}"] = (ema(c, fast) - ema(c, slow)) / a
    f["rsi_14"] = rsi(c, 14)
    f["adx_14"] = adx(bars, 14)
    f["vol_ratio"] = realized_vol(c, 12) / realized_vol(c, 192)
    f["volume_z"] = zscore(np.log1p(v), 96)
    taker = bars.taker_buy_volume / bars.volume.replace(0, np.nan)
    f["taker_imb"] = (taker - 0.5).fillna(0)
    f["taker_imb_12"] = f.taker_imb.rolling(12).mean()
    f["trades_z"] = zscore(np.log1p(bars["count"].astype(float)), 96)
    f["hurst"] = hurst(c, 256)
    f["dd_192"] = c / c.rolling(192).max() - 1
    f["du_192"] = c / c.rolling(192).min() - 1
    if funding is not None:
        fr = pd.Series(funding, index=bars.index).replace(0, np.nan).ffill().fillna(0)
        f["funding"] = fr
        f["funding_z"] = zscore(fr, 90)
    hours = pd.to_datetime(bars.open_time, unit="ms", utc=True).dt.hour
    f["hour_sin"], f["hour_cos"] = np.sin(2 * np.pi * hours / 24), np.cos(2 * np.pi * hours / 24)
    return f.replace([np.inf, -np.inf], np.nan)


def regime(bars: pd.DataFrame) -> dict[str, float]:
    """Point-in-time regime of a market (last bar): what the strategy selector and the analyst read."""
    tail = feature_frame(bars).iloc[-1]
    return {
        "trend_strength_adx": round(float(tail.adx_14), 1),
        "efficiency_ratio_48": round(float(tail.er_48), 3),
        "hurst": round(float(tail.hurst), 3),
        "vol_ratio_short_long": round(float(tail.vol_ratio), 2),
        "realized_vol_per_bar_pct": round(float(tail.vol_48) * 100, 3),
        "rsi_14": round(float(tail.rsi_14), 1),
        "ema_gap_48_192_atr": round(float(tail.ema_gap_48_192), 2),
        "drawdown_from_high_pct": round(float(tail.dd_192) * 100, 2),
    }
