"""Continuous strategy library — each strategy maps bars to a target position series in {-1, 0, 1}.

`target[i]` is decided on data up to the close of bar i-1 and filled at the open of bar i (see engine.py),
which is why every signal is shifted by one bar before it is returned.

Strategies are deliberately few and orthogonal (trend, breakout, mean reversion, ML forecast); the selector
(`services/selection.py`) picks one — with its parameters and leverage — per token via walk-forward.
"""

import itertools
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import pandas as pd

from trader.services import features as fx


def _decided_on_close(signal: pd.Series) -> np.ndarray:
    return signal.shift(1).fillna(0).to_numpy(np.int64)


def trend_ema(bars: pd.DataFrame, fast: int, slow: int, adx_min: float) -> np.ndarray:
    """Ride the EMA cross while the market trends (ADX filter keeps it out of chop)."""
    c = bars.close
    side = np.sign(fx.ema(c, fast) - fx.ema(c, slow))
    return _decided_on_close(side.where(fx.adx(bars) >= adx_min, 0))


def donchian_breakout(bars: pd.DataFrame, entry: int, exit_: int) -> np.ndarray:
    """Turtle-style: enter on an `entry`-bar high/low break, exit on the opposite `exit_`-bar extreme."""
    hi, lo = bars.high.rolling(entry).max().shift(), bars.low.rolling(entry).min().shift()
    ex_hi, ex_lo = bars.high.rolling(exit_).max().shift(), bars.low.rolling(exit_).min().shift()
    c = bars.close.to_numpy()
    out = np.zeros(len(c))
    pos = 0
    for i in range(len(c)):
        if pos == 0:
            pos = 1 if c[i] > hi.iat[i] else -1 if c[i] < lo.iat[i] else 0
        elif (pos == 1 and c[i] < ex_lo.iat[i]) or (pos == -1 and c[i] > ex_hi.iat[i]):
            pos = 0
        out[i] = pos
    return _decided_on_close(pd.Series(out, index=bars.index))


def mean_reversion(bars: pd.DataFrame, window: int, z_in: float, er_max: float) -> np.ndarray:
    """Fade stretched moves in non-trending regimes; flat once price is back to its mean."""
    z = fx.zscore(bars.close, window)
    calm = fx.efficiency_ratio(bars.close, window) <= er_max
    zz, ok = z.to_numpy(), calm.to_numpy()
    out = np.zeros(len(zz))
    pos = 0
    for i in range(len(zz)):
        if np.isnan(zz[i]):
            pos = 0
        elif pos == 0 and ok[i]:
            pos = -1 if zz[i] > z_in else 1 if zz[i] < -z_in else 0
        elif (pos == 1 and zz[i] >= 0) or (pos == -1 and zz[i] <= 0):
            pos = 0
        out[i] = pos
    return _decided_on_close(pd.Series(out, index=bars.index))


@dataclass(frozen=True)
class Spec:
    """A strategy, its parameters and the risk overlay the engine applies."""

    name: str
    params: tuple[tuple[str, float], ...]
    leverage: float
    sl_atr: float  # stop distance in ATRs (0 = none)
    tp_atr: float

    def describe(self) -> str:
        p = ", ".join(f"{k}={v:g}" for k, v in self.params)
        return f"{self.name}({p}) {self.leverage:g}x SL {self.sl_atr:g}ATR TP {self.tp_atr:g}ATR"


STRATEGIES: dict[str, Callable[..., np.ndarray]] = {"trend_ema": trend_ema, "donchian": donchian_breakout, "mean_reversion": mean_reversion}

PARAM_GRID: dict[str, list[dict]] = {
    "trend_ema": [{"fast": f, "slow": s, "adx_min": a} for f, s in ((12, 48), (24, 96), (48, 192)) for a in (15, 25)],
    "donchian": [{"entry": e, "exit_": x} for e, x in ((48, 24), (96, 48), (192, 96))],
    "mean_reversion": [{"window": w, "z_in": z, "er_max": er} for w in (48, 96) for z in (2.0, 2.5) for er in (0.3, 0.5)],
}
RISK_GRID = [(lev, sl, tp) for lev, sl, tp in itertools.product((2.0, 5.0, 10.0), (0.0, 2.0, 4.0), (0.0, 4.0, 8.0)) if not (sl == 0 and lev >= 10)]


def specs() -> list[Spec]:
    return [Spec(name, tuple(sorted(p.items())), lev, sl, tp) for name, grid in PARAM_GRID.items() for p in grid for lev, sl, tp in RISK_GRID]


def signal(spec: Spec, bars: pd.DataFrame) -> np.ndarray:
    return STRATEGIES[spec.name](bars, **dict(spec.params))
