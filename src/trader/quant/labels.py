from dataclasses import dataclass

import numpy as np
from numba import njit


@dataclass(frozen=True)
class Geometry:
    sl_atr: float = 1.5
    tp_atr: float = 3.0
    horizon: int = 48

    def describe(self) -> str:
        return f"SL {self.sl_atr:g}·ATR, TP {self.tp_atr:g}·ATR, ≤{self.horizon}h"


@njit(cache=True)
def triple_barrier(
    o: np.ndarray, h: np.ndarray, low: np.ndarray, c: np.ndarray, a: np.ndarray, sl_atr: float, tp_atr: float, horizon: int, cost: float
) -> tuple[np.ndarray, np.ndarray]:
    n = len(c)
    out_long = np.full(n, np.nan)
    out_short = np.full(n, np.nan)
    for t in range(n - horizon - 1):
        if not (a[t] > 0):
            continue
        entry = o[t + 1]
        risk = sl_atr * a[t]
        reward = tp_atr * a[t]
        rl, rs = np.nan, np.nan
        for j in range(t + 1, t + 1 + horizon):
            if rl != rl:
                if low[j] <= entry - risk:
                    rl = (min(o[j], entry - risk) - entry) / risk if j > t + 1 else -1.0
                elif h[j] >= entry + reward:
                    rl = reward / risk
            if rs != rs:
                if h[j] >= entry + risk:
                    rs = (entry - max(o[j], entry + risk)) / risk if j > t + 1 else -1.0
                elif low[j] <= entry - reward:
                    rs = reward / risk
            if rl == rl and rs == rs:
                break
        last = c[t + horizon]
        if rl != rl:
            rl = (last - entry) / risk
        if rs != rs:
            rs = (entry - last) / risk
        cost_r = cost * entry / risk
        out_long[t] = rl - cost_r
        out_short[t] = rs - cost_r
    return out_long, out_short
