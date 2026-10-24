import numpy as np
import pandas as pd
from numba import njit

from trader.quant.indicators import div, lag, rmax, rmin

PIVOTS = 6


@njit(cache=True)
def zigzag(h: np.ndarray, low: np.ndarray, a: np.ndarray, k: float, depth: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    n = len(h)
    price = np.full((n, depth), np.nan)
    index = np.full((n, depth), -1.0)
    kind = np.zeros((n, depth))
    cur_p = np.full(depth, np.nan)
    cur_i = np.full(depth, -1.0)
    cur_k = np.zeros(depth)
    direction = 1
    hi, hi_i, lo, lo_i = h[0], 0, low[0], 0
    for t in range(n):
        thr = k * a[t] if a[t] == a[t] else np.inf
        pushed = False
        pp, pi, pk = 0.0, 0.0, 0.0
        if direction == 1:
            if h[t] > hi:
                hi, hi_i = h[t], t
            elif hi - low[t] >= thr:
                pp, pi, pk, pushed = hi, hi_i, 1.0, True
                direction, lo, lo_i = -1, low[t], t
        else:
            if low[t] < lo:
                lo, lo_i = low[t], t
            elif h[t] - lo >= thr:
                pp, pi, pk, pushed = lo, lo_i, -1.0, True
                direction, hi, hi_i = 1, h[t], t
        if pushed:
            for j in range(depth - 1, 0, -1):
                cur_p[j], cur_i[j], cur_k[j] = cur_p[j - 1], cur_i[j - 1], cur_k[j - 1]
            cur_p[0], cur_i[0], cur_k[0] = pp, pi, pk
        price[t], index[t], kind[t] = cur_p, cur_i, cur_k
    return price, index, kind


def _pick(price: np.ndarray, kind: np.ndarray, want: float, nth: int) -> tuple[np.ndarray, np.ndarray]:
    n = len(price)
    out = np.full(n, np.nan)
    col = np.full(n, -1)
    seen = np.zeros(n, dtype=np.int64)
    for j in range(price.shape[1]):
        hit = (kind[:, j] == want) & (col < 0)
        take = hit & (seen == nth)
        out[take], col[take] = price[take, j], j
        seen += hit & ~take
    return out, col


def _gather(values: np.ndarray, index: np.ndarray, col: np.ndarray) -> np.ndarray:
    rows = np.arange(len(col))
    idx = np.where(col >= 0, index[rows, np.clip(col, 0, None)], -1).astype(np.int64)
    return np.where(idx >= 0, values[np.clip(idx, 0, None)], np.nan)


def candles(o: np.ndarray, h: np.ndarray, low: np.ndarray, c: np.ndarray, a: np.ndarray) -> dict[str, np.ndarray]:
    body, rng = c - o, np.maximum(h - low, 1e-12)
    upper, lower = h - np.maximum(o, c), np.minimum(o, c) - low
    po, pc, ph, pl = lag(o), lag(c), lag(h), lag(low)
    big = np.abs(body) > 0.6 * a
    bull, bear = c > o, c < o
    doji = np.abs(body) / rng < 0.1
    hammer = (lower >= 2 * np.abs(body)) & (upper / rng < 0.15) & (rng > 0.8 * a)
    star = (upper >= 2 * np.abs(body)) & (lower / rng < 0.15) & (rng > 0.8 * a)
    engulf_bull = bull & (pc < po) & (c >= po) & (o <= pc)
    engulf_bear = bear & (pc > po) & (c <= po) & (o >= pc)
    three_white = bull & lag(bull.astype(float)).astype(bool) & lag(bull.astype(float), 2).astype(bool) & (c > pc) & (pc > lag(c, 2))
    three_black = bear & lag(bear.astype(float)).astype(bool) & lag(bear.astype(float), 2).astype(bool) & (c < pc) & (pc < lag(c, 2))
    o2, c2 = lag(o, 2), lag(c, 2)
    small_mid = np.abs(pc - po) < 0.3 * np.abs(c2 - o2)
    morning = (c2 < o2) & (np.abs(c2 - o2) > 0.6 * a) & small_mid & bull & (c > (o2 + c2) / 2)
    evening = (c2 > o2) & (np.abs(c2 - o2) > 0.6 * a) & small_mid & bear & (c < (o2 + c2) / 2)
    return {
        "cdl_body": div(body, rng),
        "cdl_upper": div(upper, rng),
        "cdl_lower": div(lower, rng),
        "cdl_range_atr": div(rng, a),
        "cdl_doji": doji.astype(float),
        "cdl_hammer": hammer.astype(float) - star.astype(float),
        "cdl_engulf": engulf_bull.astype(float) - engulf_bear.astype(float),
        "cdl_three": three_white.astype(float) - three_black.astype(float),
        "cdl_star": morning.astype(float) - evening.astype(float),
        "cdl_big": big * np.sign(body),
        "cdl_inside": ((h < ph) & (low > pl)).astype(float),
        "cdl_outside": ((h > ph) & (low < pl)).astype(float) * np.sign(body),
    }


def chart(h: np.ndarray, low: np.ndarray, c: np.ndarray, a: np.ndarray, osc: np.ndarray, k: float = 2.0) -> dict[str, np.ndarray]:
    price, index, kind = zigzag(h, low, a, k, PIVOTS)
    t = np.arange(len(c), dtype=np.float64)
    h1, ch1 = _pick(price, kind, 1.0, 0)
    h2, ch2 = _pick(price, kind, 1.0, 1)
    h3, _ = _pick(price, kind, 1.0, 2)
    l1, cl1 = _pick(price, kind, -1.0, 0)
    l2, cl2 = _pick(price, kind, -1.0, 1)
    l3, _ = _pick(price, kind, -1.0, 2)
    rows = np.arange(len(c))
    i_h1 = np.where(ch1 >= 0, index[rows, np.clip(ch1, 0, None)], np.nan)
    i_l1 = np.where(cl1 >= 0, index[rows, np.clip(cl1, 0, None)], np.nan)
    tol = 0.6 * a
    hh, hl = np.sign(h1 - h2), np.sign(l1 - l2)
    structure = np.where((hh > 0) & (hl > 0), 1.0, np.where((hh < 0) & (hl < 0), -1.0, 0.0))
    double_top = (np.abs(h1 - h2) < tol) & (l1 < np.fmin(h1, h2) - 2 * a)
    double_bottom = (np.abs(l1 - l2) < tol) & (h1 > np.fmax(l1, l2) + 2 * a)
    hs = (h2 > h1 + tol) & (h2 > h3 + tol) & (np.abs(h1 - h3) < 1.5 * a)
    ihs = (l2 < l1 - tol) & (l2 < l3 - tol) & (np.abs(l1 - l3) < 1.5 * a)
    neck_hs, neck_ihs = np.fmin(l1, l2), np.fmax(h1, h2)
    falling_highs, rising_lows = (h1 < h2 - 0.3 * a) & (h2 < h3 - 0.3 * a), (l1 > l2 + 0.3 * a) & (l2 > l3 + 0.3 * a)
    flat_highs, flat_lows = (np.abs(h1 - h2) < tol) & (np.abs(h2 - h3) < tol), (np.abs(l1 - l2) < tol) & (np.abs(l2 - l3) < tol)
    triangle = (falling_highs & rising_lows) | (flat_highs & rising_lows) | (falling_highs & flat_lows)
    osc_h1, osc_h2 = _gather(osc, index, ch1), _gather(osc, index, ch2)
    osc_l1, osc_l2 = _gather(osc, index, cl1), _gather(osc, index, cl2)
    bear_div = (h1 > h2) & (osc_h1 < osc_h2 - 3)
    bull_div = (l1 < l2) & (osc_l1 > osc_l2 + 3)
    swing = h1 - l1
    fib = div(c - l1, swing)
    up_leg = i_l1 < i_h1
    retrace = np.where(up_leg, div(h1 - c, swing), div(c - l1, swing))
    return {
        "zz_dist_high": div(c - h1, a),
        "zz_dist_low": div(c - l1, a),
        "zz_age_high": t - i_h1,
        "zz_age_low": t - i_l1,
        "zz_structure": structure,
        "zz_bos_up": ((structure <= 0) & (c > h1)).astype(float),
        "zz_bos_down": ((structure >= 0) & (c < l1)).astype(float),
        "zz_double": double_bottom.astype(float) - double_top.astype(float),
        "zz_double_break": (double_bottom & (c > h1)).astype(float) - (double_top & (c < l1)).astype(float),
        "zz_hs": ihs.astype(float) - hs.astype(float),
        "zz_hs_break": (ihs & (c > neck_ihs)).astype(float) - (hs & (c < neck_hs)).astype(float),
        "zz_triangle": triangle.astype(float),
        "zz_triangle_break": (triangle & (c > h1)).astype(float) - (triangle & (c < l1)).astype(float),
        "zz_divergence": bull_div.astype(float) - bear_div.astype(float),
        "zz_swing_atr": div(swing, a),
        "zz_fib_position": fib,
        "zz_retrace": retrace * np.where(up_leg, 1.0, -1.0),
    }


def levels(h: np.ndarray, low: np.ndarray, c: np.ndarray, a: np.ndarray, n: int = 48) -> dict[str, np.ndarray]:
    hi, lo = lag(rmax(h, n)), lag(rmin(low, n))
    width = div(hi - lo, a)
    squeeze = (pd.Series(width).rolling(500, min_periods=100).rank(pct=True) < 0.2).to_numpy()
    impulse = div(c - lag(c, 12), a)
    calm = div(rmax(h, 6) - rmin(low, 6), a)
    return {
        "lvl_break": (c > hi).astype(float) - (c < lo).astype(float),
        "lvl_break_squeeze": ((c > hi) & squeeze).astype(float) - ((c < lo) & squeeze).astype(float),
        "lvl_width_atr": width,
        "lvl_flag": ((lag(impulse, 6) > 4) & (calm < 2.5)).astype(float) - ((lag(impulse, 6) < -4) & (calm < 2.5)).astype(float),
    }
