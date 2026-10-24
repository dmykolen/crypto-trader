import numpy as np
import pandas as pd
from numba import njit


def _s(x: np.ndarray) -> pd.Series:
    return pd.Series(x, copy=False)


def sma(x: np.ndarray, n: int) -> np.ndarray:
    return _s(x).rolling(n, min_periods=n).mean().to_numpy()


def rstd(x: np.ndarray, n: int) -> np.ndarray:
    return _s(x).rolling(n, min_periods=n).std().to_numpy()


def rsum(x: np.ndarray, n: int) -> np.ndarray:
    return _s(x).rolling(n, min_periods=n).sum().to_numpy()


def rmax(x: np.ndarray, n: int) -> np.ndarray:
    return _s(x).rolling(n, min_periods=n).max().to_numpy()


def rmin(x: np.ndarray, n: int) -> np.ndarray:
    return _s(x).rolling(n, min_periods=n).min().to_numpy()


def ema(x: np.ndarray, span: int) -> np.ndarray:
    return _s(x).ewm(span=span, adjust=False, min_periods=span).mean().to_numpy()


def wilder(x: np.ndarray, n: int) -> np.ndarray:
    return _s(x).ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean().to_numpy()


def lag(x: np.ndarray, k: int = 1) -> np.ndarray:
    out = np.full_like(x, np.nan, dtype=np.float64)
    if k < len(x):
        out[k:] = x[:-k] if k else x
    return out


def div(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    with np.errstate(divide="ignore", invalid="ignore"):
        out = np.asarray(a, dtype=np.float64) / np.asarray(b, dtype=np.float64)
    out[~np.isfinite(out)] = np.nan
    return out


def true_range(h: np.ndarray, low: np.ndarray, c: np.ndarray) -> np.ndarray:
    pc = lag(c)
    pc[0] = c[0]
    return np.maximum(h - low, np.maximum(np.abs(h - pc), np.abs(low - pc)))


def atr(h: np.ndarray, low: np.ndarray, c: np.ndarray, n: int = 14) -> np.ndarray:
    return wilder(true_range(h, low, c), n)


def rsi(c: np.ndarray, n: int = 14) -> np.ndarray:
    d = np.diff(c, prepend=c[0])
    up, dn = wilder(np.maximum(d, 0.0), n), wilder(np.maximum(-d, 0.0), n)
    return 100.0 * div(up, up + dn)


def macd(c: np.ndarray, fast: int = 12, slow: int = 26, signal: int = 9) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    line = ema(c, fast) - ema(c, slow)
    sig = ema(np.nan_to_num(line), signal)
    return line, sig, line - sig


def stochastic(h: np.ndarray, low: np.ndarray, c: np.ndarray, n: int = 14, d: int = 3) -> tuple[np.ndarray, np.ndarray]:
    lo, hi = rmin(low, n), rmax(h, n)
    k = 100.0 * div(c - lo, hi - lo)
    return k, sma(k, d)


def williams_r(h: np.ndarray, low: np.ndarray, c: np.ndarray, n: int = 14) -> np.ndarray:
    lo, hi = rmin(low, n), rmax(h, n)
    return -100.0 * div(hi - c, hi - lo)


def cci(h: np.ndarray, low: np.ndarray, c: np.ndarray, n: int = 20) -> np.ndarray:
    tp = (h + low + c) / 3.0
    return div(tp - sma(tp, n), 0.015 * 0.7979 * rstd(tp, n))


def adx(h: np.ndarray, low: np.ndarray, c: np.ndarray, n: int = 14) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    up, dn = h - lag(h), lag(low) - low
    plus = np.where((up > dn) & (up > 0), up, 0.0)
    minus = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = wilder(true_range(h, low, c), n)
    pdi, mdi = 100.0 * div(wilder(plus, n), tr), 100.0 * div(wilder(minus, n), tr)
    dx = 100.0 * div(np.abs(pdi - mdi), pdi + mdi)
    return wilder(np.nan_to_num(dx), n), pdi, mdi


def mfi(h: np.ndarray, low: np.ndarray, c: np.ndarray, v: np.ndarray, n: int = 14) -> np.ndarray:
    tp = (h + low + c) / 3.0
    flow = tp * v
    rising = tp > lag(tp)
    pos, neg = rsum(np.where(rising, flow, 0.0), n), rsum(np.where(~rising, flow, 0.0), n)
    return 100.0 * div(pos, pos + neg)


def obv(c: np.ndarray, v: np.ndarray) -> np.ndarray:
    return np.cumsum(np.sign(np.diff(c, prepend=c[0])) * v)


def cmf(h: np.ndarray, low: np.ndarray, c: np.ndarray, v: np.ndarray, n: int = 20) -> np.ndarray:
    mfm = div((c - low) - (h - c), h - low)
    return div(rsum(np.nan_to_num(mfm) * v, n), rsum(v, n))


def bollinger(c: np.ndarray, n: int = 20, k: float = 2.0) -> tuple[np.ndarray, np.ndarray]:
    m, s = sma(c, n), rstd(c, n)
    return div(c - (m - k * s), 2 * k * s), div(2 * k * s, m)


def keltner_position(h: np.ndarray, low: np.ndarray, c: np.ndarray, a: np.ndarray, n: int = 20, k: float = 1.5) -> np.ndarray:
    mid = ema(c, n)
    return div(c - mid, k * a)


def donchian_position(h: np.ndarray, low: np.ndarray, c: np.ndarray, n: int) -> np.ndarray:
    lo, hi = rmin(low, n), rmax(h, n)
    return div(c - lo, hi - lo)


def tsi(c: np.ndarray, r: int = 25, s: int = 13) -> np.ndarray:
    m = np.diff(c, prepend=c[0])
    return 100.0 * div(ema(np.nan_to_num(ema(m, r)), s), ema(np.nan_to_num(ema(np.abs(m), r)), s))


def vwap_distance(h: np.ndarray, low: np.ndarray, c: np.ndarray, v: np.ndarray, a: np.ndarray, n: int = 24) -> np.ndarray:
    tp = (h + low + c) / 3.0
    return div(c - div(rsum(tp * v, n), rsum(v, n)), a)


def ichimoku(h: np.ndarray, low: np.ndarray, c: np.ndarray, a: np.ndarray) -> dict[str, np.ndarray]:
    tenkan = (rmax(h, 9) + rmin(low, 9)) / 2
    kijun = (rmax(h, 26) + rmin(low, 26)) / 2
    span_a, span_b = lag((tenkan + kijun) / 2, 26), lag((rmax(h, 52) + rmin(low, 52)) / 2, 26)
    top, bottom = np.fmax(span_a, span_b), np.fmin(span_a, span_b)
    return {
        "ichi_tk": div(tenkan - kijun, a),
        "ichi_kijun": div(c - kijun, a),
        "ichi_above_cloud": div(c - top, a),
        "ichi_below_cloud": div(c - bottom, a),
        "ichi_cloud_width": div(span_a - span_b, a),
    }


@njit(cache=True)
def bars_since_extreme(x: np.ndarray, n: int, highest: bool) -> np.ndarray:
    out = np.full(len(x), np.nan)
    for i in range(n - 1, len(x)):
        best = i - n + 1
        for j in range(i - n + 1, i + 1):
            if (x[j] >= x[best]) if highest else (x[j] <= x[best]):
                best = j
        out[i] = i - best
    return out


def aroon(h: np.ndarray, low: np.ndarray, n: int = 25) -> tuple[np.ndarray, np.ndarray]:
    up = 100.0 * (n - bars_since_extreme(h, n, True)) / n
    dn = 100.0 * (n - bars_since_extreme(low, n, False)) / n
    return up, dn


@njit(cache=True)
def supertrend(h: np.ndarray, low: np.ndarray, c: np.ndarray, a: np.ndarray, mult: float) -> tuple[np.ndarray, np.ndarray]:
    n = len(c)
    direction = np.zeros(n)
    band = np.full(n, np.nan)
    upper, lower, d = np.nan, np.nan, 1.0
    for i in range(n):
        if a[i] != a[i]:
            continue
        mid = (h[i] + low[i]) / 2
        bu, bl = mid + mult * a[i], mid - mult * a[i]
        if upper != upper:
            upper, lower = bu, bl
        else:
            upper = bu if (bu < upper or c[i - 1] > upper) else upper
            lower = bl if (bl > lower or c[i - 1] < lower) else lower
        if d > 0 and c[i] < lower:
            d = -1.0
        elif d < 0 and c[i] > upper:
            d = 1.0
        direction[i] = d
        band[i] = lower if d > 0 else upper
    return direction, band


@njit(cache=True)
def psar(h: np.ndarray, low: np.ndarray, step: float, top: float) -> tuple[np.ndarray, np.ndarray]:
    n = len(h)
    sar = np.full(n, np.nan)
    direction = np.zeros(n)
    if n < 3:
        return direction, sar
    up = True
    af, ep, s = step, h[0], low[0]
    for i in range(1, n):
        s = s + af * (ep - s)
        if up:
            s = min(s, low[i - 1], low[i - 2] if i > 1 else low[i - 1])
            if low[i] < s:
                up, s, ep, af = False, ep, low[i], step
            elif h[i] > ep:
                ep, af = h[i], min(af + step, top)
        else:
            s = max(s, h[i - 1], h[i - 2] if i > 1 else h[i - 1])
            if h[i] > s:
                up, s, ep, af = True, ep, h[i], step
            elif low[i] < ep:
                ep, af = low[i], min(af + step, top)
        sar[i] = s
        direction[i] = 1.0 if up else -1.0
    return direction, sar


@njit(cache=True)
def heikin_ashi_streak(o: np.ndarray, h: np.ndarray, low: np.ndarray, c: np.ndarray) -> np.ndarray:
    n = len(c)
    out = np.zeros(n)
    ha_open = (o[0] + c[0]) / 2
    prev_close = ha_open
    streak = 0.0
    for i in range(n):
        ha_close = (o[i] + h[i] + low[i] + c[i]) / 4
        if i > 0:
            ha_open = (ha_open + prev_close) / 2
        prev_close = ha_close
        up = ha_close >= ha_open
        streak = (streak + 1 if streak > 0 else 1.0) if up else (streak - 1 if streak < 0 else -1.0)
        out[i] = streak
    return out
