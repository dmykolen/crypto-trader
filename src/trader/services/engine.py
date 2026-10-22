"""Leveraged backtest engine for USDⓈ-M perpetuals (numba).

One trade walker (`_walk`) implements the execution rules, and every backtest in the app — continuous
strategies and event playbooks — goes through it, so they all fill and get liquidated the same way.

Execution model (conservative on purpose):
  * decisions use data up to the close of bar i-1 and fill at the OPEN of bar i (no look-ahead);
  * market fills pay `slip` per side, stop-market exits `stop_slip`, every fill pays the taker `fee` on notional;
  * isolated margin: the position is liquidated as soon as the bar's ADVERSE extreme reaches the liquidation price
    (maintenance-margin rate `mmr`, funding drains the margin), and liquidation forfeits the whole margin;
  * inside a bar the adverse extreme is assumed to come first: when stop and take-profit both fit in one bar,
    the stop wins; a gap through the stop fills at the open, not at the stop;
  * funding is charged on notional at mark (bar close) for every settlement the position is open through;
  * the trailing stop only ratchets with extremes of COMPLETED bars.

Returns are expressed per unit of margin: +0.25 means the trade made 25 % of the margin committed to it.
"""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from numba import njit

from trader.core.config import settings

SIGNAL, STOP, TAKE_PROFIT, TIME, LIQUIDATION, END, REVERSAL = range(7)
EXIT_REASONS = ("signal", "stop", "take_profit", "time", "liquidation", "end", "reversal")


@dataclass(frozen=True)
class Costs:
    fee: float = settings.taker_fee
    slip: float = settings.slippage
    stop_slip: float = settings.slippage * settings.stop_slippage_mult
    mmr: float = settings.maintenance_margin

    @classmethod
    def for_events(cls) -> "Costs":
        """Small caps minutes after an announcement: wider spreads, thinner books."""
        return cls(slip=settings.event_slippage, stop_slip=settings.event_slippage * settings.stop_slippage_mult)


def liquidation_distance(leverage: float, side: int, mmr: float = settings.maintenance_margin) -> float:
    """Adverse move (fraction of entry) that liquidates a fresh isolated position — same formula as `_walk`."""
    liq = (leverage - side) / (leverage * (1.0 - side * mmr))
    return abs(1.0 - liq)


@njit(cache=True, nogil=True)
def _walk(o, h, lo, c, fr, i, side, sl, tp, trail, max_bars, lev, fee, slip, stop_slip, mmr, target, mtm):
    """Hold one isolated position opened at the open of bar `i`. Returns (exit_bar, return_on_margin, reason).

    `target[j]` is the strategy's desired side at the open of bar j (an exit when it differs from `side`, a
    reversal when it is `-side`); event trades pass all-`side` targets. `mtm[j]` receives the mark-to-market
    return at the close of every bar the trade spans (NaN-free; caller owns the array).
    """
    n = len(o)
    entry = o[i] * (1.0 + side * slip)
    ret = -fee * lev  # entry fee
    margin = 1.0  # isolated margin left, in units of the initial margin (funding drains it)
    stop = entry * (1.0 - side * sl) if sl > 0 else (0.0 if side > 0 else np.inf)
    take = entry * (1.0 + side * tp) if tp > 0 else (np.inf if side > 0 else 0.0)
    best = entry
    for j in range(i, n):
        if j > i and target[j] != side:  # strategy exit / reversal, filled at this open
            px = o[j] * (1.0 - side * slip)
            mtm[j] = ret + side * lev * (px / entry - 1.0) - fee * lev * px / entry
            return j, mtm[j], (REVERSAL if target[j] == -side else SIGNAL)
        if fr[j] != 0.0:  # settlement at (or inside) this bar while the position is open
            pay = side * lev * (o[j] / entry) * fr[j]
            ret -= pay
            margin -= pay
        # liquidation price for the margin left: margin + side·lev·(P/E - 1) = mmr·lev·P/E
        liq = entry * (lev - side * margin) / (lev * (1.0 - side * mmr))
        if trail > 0:
            trail_stop = best * (1.0 - side * trail)
            stop = max(stop, trail_stop) if side > 0 else min(stop, trail_stop)
        adverse, favorable = (lo[j], h[j]) if side > 0 else (h[j], lo[j])
        liq_first = (liq >= stop) if side > 0 else (liq <= stop)
        hit_liq = (adverse <= liq) if side > 0 else (adverse >= liq)
        hit_stop = (adverse <= stop) if side > 0 else (adverse >= stop)
        gap_liq = (o[j] <= liq) if side > 0 else (o[j] >= liq)
        if hit_liq and (liq_first or not hit_stop or gap_liq):
            mtm[j] = -1.0 - fee * lev
            return j, mtm[j], LIQUIDATION
        if hit_stop:
            gap = (o[j] <= stop) if side > 0 else (o[j] >= stop)
            px = (o[j] if gap else stop) * (1.0 - side * stop_slip)
            mtm[j] = max(ret + side * lev * (px / entry - 1.0) - fee * lev * px / entry, -1.0 - fee * lev)
            return j, mtm[j], STOP
        if (favorable >= take) if side > 0 else (favorable <= take):
            px = take * (1.0 - side * slip)  # never better than the TP level, even when the bar gaps through it
            mtm[j] = ret + side * lev * (px / entry - 1.0) - fee * lev * px / entry
            return j, mtm[j], TAKE_PROFIT
        best = max(best, h[j]) if side > 0 else min(best, lo[j])
        mtm[j] = ret + side * lev * (c[j] / entry - 1.0)
        if j - i + 1 >= max_bars or j == n - 1:
            px = c[j] * (1.0 - side * slip)
            mtm[j] = ret + side * lev * (px / entry - 1.0) - fee * lev * px / entry
            return j, mtm[j], (TIME if j - i + 1 >= max_bars else END)
    return n - 1, ret, END


@njit(cache=True)
def _simulate(o, h, lo, c, fr, target, sl, tp, trail, max_bars, lev, margin_frac, fee, slip, stop_slip, mmr):
    """Run a target-position series. Returns (equity curve per bar close, trades[k] = entry, exit, side, ret, reason).

    After a stop / take-profit / time exit the strategy re-enters only once its target changes, so a persistent
    signal does not immediately re-open the trade that was just stopped out.
    """
    n = len(o)
    equity = np.ones(n)
    trades = np.zeros((n, 5))
    mtm = np.zeros(n)
    k = 0
    cash = 1.0
    blocked = 0
    i = 0
    while i < n:
        side = target[i]
        if side == 0 or side == blocked:
            if side != blocked:
                blocked = 0
            equity[i] = cash
            i += 1
            continue
        blocked = 0
        stake = cash * margin_frac
        j, ret, reason = _walk(o, h, lo, c, fr, i, side, sl[i], tp[i], trail[i], max_bars[i], lev, fee, slip, stop_slip, mmr, target, mtm)
        for b in range(i, j + 1):
            equity[b] = cash + stake * mtm[b]
        cash = max(cash + stake * ret, 0.0)
        trades[k, 0], trades[k, 1], trades[k, 2], trades[k, 3], trades[k, 4] = i, j, side, ret, reason
        k += 1
        if cash <= 0.0:
            equity[j:] = 0.0
            break
        if reason in (REVERSAL, SIGNAL):
            i = j  # the open of bar j already belongs to the next decision
        else:
            blocked = side
            i = j + 1
    return equity, trades[:k]


@njit(cache=True, nogil=True)
def event_grid(o, h, lo, c, fr, base, delays, sides, sls, tps, trails, holds, levs, fee, slip, stop_slip, mmr):
    """Return-on-margin and exit bar of one event for every playbook in the grid (one row per playbook).

    `base` is the first bar our reaction can fill at; `delays` (bars) wait further before entering. Each
    playbook holds at most `holds` bars, so the caller bounds the window (e.g. 24h after the announcement).
    A playbook that cannot start inside the window gets NaN / -1.
    """
    m = len(sides)
    out = np.full(m, np.nan)
    exits = np.full(m, -1, dtype=np.int64)
    mtm = np.zeros(len(o))
    target = np.zeros(len(o), dtype=np.int64)
    for p in range(m):
        i = base + delays[p]
        if i >= len(o):
            continue
        target[:] = sides[p]
        exits[p], out[p], _ = _walk(o, h, lo, c, fr, i, sides[p], sls[p], tps[p], trails[p], holds[p], levs[p], fee, slip, stop_slip, mmr, target, mtm)
    return out, exits


@dataclass
class BacktestResult:
    equity: pd.Series  # account equity per bar close, starting at `capital`
    trades: pd.DataFrame
    capital: float
    metrics: dict = field(default_factory=dict)


def _per_bar(value, n: int, dtype: type = np.float64) -> np.ndarray:
    return np.broadcast_to(np.asarray(value, dtype=dtype), (n,)).copy()


def backtest(
    bars: pd.DataFrame,
    funding: np.ndarray,
    target: np.ndarray,
    *,
    leverage: float,
    margin_frac: float = 1.0,
    sl: float | np.ndarray = 0.0,
    tp: float | np.ndarray = 0.0,
    trail: float | np.ndarray = 0.0,
    max_bars: int | np.ndarray = 10**9,
    costs: Costs | None = None,
    capital: float = 1000.0,
) -> BacktestResult:
    """Simulate a target-position series (`target[i]` ∈ {-1, 0, 1}, decided before the open of bar i)."""
    costs = costs or Costs()
    n = len(bars)
    o, h, lo, c = (bars[col].to_numpy(np.float64) for col in ("open", "high", "low", "close"))
    equity, trades = _simulate(
        o, h, lo, c, np.asarray(funding, np.float64), np.asarray(target, np.int64),
        _per_bar(sl, n), _per_bar(tp, n), _per_bar(trail, n), _per_bar(max_bars, n, np.int64),
        float(leverage), float(margin_frac), costs.fee, costs.slip, costs.stop_slip, costs.mmr,
    )  # fmt: skip
    index = pd.to_datetime(bars.open_time.to_numpy(), unit="ms", utc=True)
    curve = pd.Series(equity * capital, index=index, name="equity")
    t = pd.DataFrame(trades, columns=["entry_bar", "exit_bar", "side", "ret", "reason"]).astype({"entry_bar": int, "exit_bar": int, "side": int, "reason": int})
    if len(t):
        t["entry_time"] = index[t.entry_bar]
        t["exit_time"] = index[t.exit_bar]
        t["reason"] = [EXIT_REASONS[r] for r in t.reason]
    result = BacktestResult(curve, t, capital)
    result.metrics = summarize(curve, t, capital)
    return result


def summarize(equity: pd.Series, trades: pd.DataFrame, capital: float) -> dict:
    """Headline metrics: return, drawdown, daily Sharpe, trade stats, liquidations."""
    if equity.empty:
        return {"final_equity": capital, "return_pct": 0.0, "trades": 0}
    daily = equity.resample("1D").last().ffill()
    daily_ret = daily.pct_change().dropna()
    daily_pnl = daily.diff().fillna(daily.iloc[0] - capital)
    peak = equity.cummax()
    wins = trades.ret[trades.ret > 0].sum() if len(trades) else 0.0
    losses = -trades.ret[trades.ret < 0].sum() if len(trades) else 0.0
    return {
        "final_equity": round(float(equity.iloc[-1]), 2),
        "pnl": round(float(equity.iloc[-1] - capital), 2),
        "return_pct": round(float(equity.iloc[-1] / capital - 1) * 100, 2),
        "max_drawdown_pct": round(float((equity / peak - 1).min()) * 100, 2),
        "sharpe_daily": round(float(daily_ret.mean() / daily_ret.std() * np.sqrt(365)), 2) if len(daily_ret) > 2 and daily_ret.std() > 0 else 0.0,
        "trades": len(trades),
        "win_rate_pct": round(float((trades.ret > 0).mean()) * 100, 1) if len(trades) else 0.0,
        "profit_factor": round(float(wins / losses), 2) if losses > 0 else None,
        "liquidations": int((trades.reason == "liquidation").sum()) if len(trades) else 0,
        "best_day_pnl": round(float(daily_pnl.max()), 2),
        "worst_day_pnl": round(float(daily_pnl.min()), 2),
        "days_pnl_ge_100_per_1000": int((daily_pnl >= 100 * capital / 1000).sum()),
        "days": len(daily_pnl),
    }
