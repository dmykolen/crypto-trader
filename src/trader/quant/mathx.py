import numpy as np
from numba import njit

from trader.quant.indicators import _s, div, lag, rstd, sma


def log_returns(c: np.ndarray) -> np.ndarray:
    return np.diff(np.log(c), prepend=np.nan)


def parkinson(h: np.ndarray, low: np.ndarray, n: int) -> np.ndarray:
    x = np.log(div(h, low)) ** 2
    return np.sqrt(_s(x).rolling(n, min_periods=n).mean().to_numpy() / (4 * np.log(2)))


def garman_klass(o: np.ndarray, h: np.ndarray, low: np.ndarray, c: np.ndarray, n: int) -> np.ndarray:
    x = 0.5 * np.log(div(h, low)) ** 2 - (2 * np.log(2) - 1) * np.log(div(c, o)) ** 2
    return np.sqrt(np.clip(_s(x).rolling(n, min_periods=n).mean().to_numpy(), 0, None))


def rolling_skew(r: np.ndarray, n: int) -> np.ndarray:
    return _s(r).rolling(n, min_periods=n).skew().to_numpy()


def rolling_kurt(r: np.ndarray, n: int) -> np.ndarray:
    return _s(r).rolling(n, min_periods=n).kurt().to_numpy()


def autocorr(r: np.ndarray, n: int, k: int = 1) -> np.ndarray:
    return _s(r).rolling(n, min_periods=n).corr(_s(lag(r, k))).to_numpy()


def variance_ratio(r: np.ndarray, n: int, q: int = 4) -> np.ndarray:
    rq = _s(r).rolling(q, min_periods=q).sum().to_numpy()
    return div(_s(rq).rolling(n, min_periods=n).var().to_numpy(), q * _s(r).rolling(n, min_periods=n).var().to_numpy())


def hurst(c: np.ndarray, n: int = 192, lags: tuple[int, ...] = (2, 4, 8, 16, 32)) -> np.ndarray:
    y = np.log(c)
    logs = np.log(np.array(lags, dtype=np.float64))
    stds = np.stack([np.log(rstd(y - lag(y, k), n)) for k in lags])
    lx = logs - logs.mean()
    return (lx[:, None] * (stds - stds.mean(axis=0))).sum(axis=0) / (lx**2).sum()


def zscore(x: np.ndarray, n: int) -> np.ndarray:
    return div(x - sma(x, n), rstd(x, n))


def trend_fit(y: np.ndarray, n: int) -> tuple[np.ndarray, np.ndarray]:
    t = _s(np.arange(len(y), dtype=np.float64))
    corr = _s(y).rolling(n, min_periods=n).corr(t).to_numpy()
    slope = corr * div(rstd(y, n), rstd(t.to_numpy(), n))
    return slope, corr**2


def beta_residual(r: np.ndarray, rb: np.ndarray, n: int) -> tuple[np.ndarray, np.ndarray]:
    sr, sb = _s(r), _s(rb)
    beta = div(sr.rolling(n, min_periods=n).cov(sb).to_numpy(), sb.rolling(n, min_periods=n).var().to_numpy())
    return beta, r - beta * rb


def ou_half_life(c: np.ndarray, n: int) -> np.ndarray:
    y = np.log(c)
    dy, yl = _s(y - lag(y)), _s(lag(y))
    beta = div(dy.rolling(n, min_periods=n).cov(yl).to_numpy(), yl.rolling(n, min_periods=n).var().to_numpy())
    hl = div(-np.log(2.0) * np.ones_like(beta), np.log1p(np.clip(beta, -0.999, None)))
    return np.where(beta < 0, np.log1p(np.clip(hl, 0, 10_000)), np.log1p(10_000.0))


def ffd_weights(d: float, threshold: float = 1e-4, limit: int = 2000) -> np.ndarray:
    w = [1.0]
    for k in range(1, limit):
        nxt = -w[-1] * (d - k + 1) / k
        if abs(nxt) < threshold:
            break
        w.append(nxt)
    return np.array(w)


def frac_diff(c: np.ndarray, d: float = 0.4) -> np.ndarray:
    w = ffd_weights(d)
    y = np.log(c)
    out = np.full(len(y), np.nan)
    if len(y) >= len(w):
        out[len(w) - 1 :] = np.convolve(y, w, mode="valid")
    return out


@njit(cache=True)
def permutation_entropy(x: np.ndarray, m: int, n: int) -> np.ndarray:
    size = len(x)
    out = np.full(size, np.nan)
    fact = 1
    for k in range(2, m + 1):
        fact *= k
    codes = np.full(size, -1)
    for t in range(m - 1, size):
        ok = True
        for j in range(m):
            if x[t - j] != x[t - j]:
                ok = False
        if not ok:
            continue
        code = 0
        for i in range(m):
            smaller = 0
            for j in range(i + 1, m):
                if x[t - m + 1 + j] < x[t - m + 1 + i]:
                    smaller += 1
            f = 1
            for k in range(2, m - i):
                f *= k
            code += smaller * f
        codes[t] = code
    counts = np.zeros(fact)
    valid = 0
    norm = np.log(fact)
    for t in range(size):
        if codes[t] >= 0:
            counts[codes[t]] += 1
            valid += 1
        if t - n >= 0 and codes[t - n] >= 0:
            counts[codes[t - n]] -= 1
            valid -= 1
        if t >= n - 1 and valid >= n // 2:
            h = 0.0
            for k in range(fact):
                if counts[k] > 0:
                    p = counts[k] / valid
                    h -= p * np.log(p)
            out[t] = h / norm
    return out


@njit(cache=True)
def kalman_trend(y: np.ndarray, span: int) -> tuple[np.ndarray, np.ndarray]:
    n = len(y)
    level_out = np.full(n, np.nan)
    slope_out = np.full(n, np.nan)
    alpha = 2.0 / (span + 1)
    level, slope = y[0], 0.0
    p00, p01, p11 = 1.0, 0.0, 1.0
    var = 1e-4
    for t in range(1, n):
        r = y[t] - y[t - 1]
        if r == r:
            var = (1 - alpha) * var + alpha * r * r
        q_level, q_slope, obs = 0.01 * var, 0.0001 * var, var
        level_p = level + slope
        p00_p = p00 + 2 * p01 + p11 + q_level
        p01_p = p01 + p11
        p11_p = p11 + q_slope
        innov = y[t] - level_p
        s = p00_p + obs
        k0, k1 = p00_p / s, p01_p / s
        level = level_p + k0 * innov
        slope = slope + k1 * innov
        p00, p01, p11 = (1 - k0) * p00_p, (1 - k0) * p01_p, p11_p - k1 * p01_p
        level_out[t] = level
        slope_out[t] = slope / np.sqrt(var) if var > 0 else 0.0
    return level_out, slope_out
