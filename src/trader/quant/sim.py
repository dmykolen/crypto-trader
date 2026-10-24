from collections import defaultdict, deque
from dataclasses import asdict, dataclass, field

import numpy as np
import pandas as pd

from trader.quant.labels import Geometry

HOUR = 3_600_000


@dataclass(frozen=True)
class Policy:
    theta: float = 0.15
    max_positions: int = 8
    risk: float = 0.01
    max_leverage: float = 20.0
    max_gross: float = 10.0
    fee: float = 0.0005
    slip: float = 0.0003
    reverse: bool = True
    gate: bool = False
    gate_days: int = 60
    gate_min_trades: int = 4
    breakeven_at_r: float = 0.0
    side: str = "both"
    quantile: float | None = None
    theta_long: float | None = None
    theta_short: float | None = None

    def thresholds(self) -> tuple[float, float]:
        tl = self.theta if self.theta_long is None else self.theta_long
        ts = self.theta if self.theta_short is None else self.theta_short
        return (tl if self.side in ("both", "long") else np.inf), (ts if self.side in ("both", "short") else np.inf)

    def describe(self) -> str:
        extra = (" + per-token gate" if self.gate else "") + (" + reverse" if self.reverse else "") + (f" + BE at {self.breakeven_at_r:g}R" if self.breakeven_at_r else "")
        sides = {"both": "long+short", "short": "short only", "long": "long only"}[self.side]
        entry = f"top {100 * (1 - self.quantile):.1f}% of predictions" if self.quantile is not None else f"expected R > {self.theta:g}"
        return f"{sides}, enter on {entry}, risk {self.risk:.1%} per trade, ≤{self.max_positions} positions{extra}"


@dataclass
class Bars:
    t: np.ndarray
    o: np.ndarray
    h: np.ndarray
    low: np.ndarray
    c: np.ndarray
    atr: np.ndarray
    funding: np.ndarray

    @classmethod
    def of(cls, df: pd.DataFrame) -> "Bars":
        df = df.sort_values("open_time")
        return cls(*(df[k].to_numpy(np.int64 if k == "open_time" else np.float64) for k in ("open_time", "open", "high", "low", "close", "atr", "funding")))


@dataclass
class Position:
    symbol: str
    side: int
    entry_i: int
    entry: float
    qty: float
    leverage: float
    stop: float
    take: float
    risk_px: float
    expiry_i: int
    score: float
    fees: float = 0.0
    funding: float = 0.0


@dataclass
class Result:
    equity: pd.Series
    trades: pd.DataFrame
    policy: Policy
    geometry: Geometry
    stats: dict = field(default_factory=dict)


def _liq_distance(leverage: float) -> float:
    return 1.0 / leverage - 0.005


def locate(b: Bars, now: int) -> int | None:
    i = int((now - b.t[0]) // HOUR)
    if 0 <= i < len(b.t) and b.t[i] == now:
        return i
    j = int(np.searchsorted(b.t, now))
    return j if j < len(b.t) and b.t[j] == now else None


def simulate(preds: pd.DataFrame, bars: dict[str, Bars], geometry: Geometry, policy: Policy, start: int, end: int, capital: float = 1000.0) -> Result:
    th_long, th_short = policy.thresholds()
    cand = preds[(preds.open_time >= start - HOUR) & (preds.open_time < end) & ((preds.pred_long > th_long) | (preds.pred_short > th_short))]
    signals: dict[int, list[tuple[float, str, int]]] = defaultdict(list)
    for sym, t, pl, ps in zip(cand.symbol.to_numpy(), cand.open_time.to_numpy(), cand.pred_long.to_numpy(), cand.pred_short.to_numpy(), strict=True):
        edge_long, edge_short = pl - th_long, ps - th_short
        if max(edge_long, edge_short) > 0:
            signals[int(t) + HOUR].append((float(max(edge_long, edge_short)), str(sym), 1 if edge_long >= edge_short else -1))
    cash = capital
    open_pos: dict[str, Position] = {}
    closed: list[dict] = []
    history: dict[str, deque] = defaultdict(deque)
    curve_t, curve_v = [], []

    def close(p: Position, i: int, px: float, reason: str) -> None:
        nonlocal cash
        b = bars[p.symbol]
        fill = px * (1 - p.side * policy.slip)
        fee = policy.fee * p.qty * fill
        gross = p.side * p.qty * (fill - p.entry)
        margin = p.qty * p.entry / p.leverage
        gross = max(gross, -margin)
        pnl = gross - p.fees - fee + p.funding
        cash += pnl
        r = pnl / (p.qty * p.risk_px)
        closed.append({
            "symbol": p.symbol,
            "side": "LONG" if p.side > 0 else "SHORT",
            "entry_time": int(b.t[p.entry_i]),
            "exit_time": int(b.t[i]),
            "entry": p.entry,
            "exit": fill,
            "qty": p.qty,
            "leverage": round(p.leverage, 2),
            "notional": p.qty * p.entry,
            "margin": margin,
            "fees": p.fees + fee,
            "funding": p.funding,
            "pnl": pnl,
            "r": r,
            "reason": reason,
            "score": p.score,
            "stop": p.stop,
            "take": p.take,
        })
        history[p.symbol].append((int(b.t[i]), r))
        del open_pos[p.symbol]

    def gated(symbol: str, now: int) -> bool:
        q = history[symbol]
        while q and q[0][0] < now - policy.gate_days * 24 * HOUR:
            q.popleft()
        return bool(policy.gate and len(q) >= policy.gate_min_trades and np.mean([r for _, r in q]) < 0)

    for now in range(start - start % HOUR, end, HOUR):
        for score, sym, side in sorted(signals.get(now, []), reverse=True):
            b = bars.get(sym)
            i = locate(b, now) if b is not None else None
            if i is None:
                continue
            held = open_pos.get(sym)
            if held is not None:
                if held.side == side or not policy.reverse:
                    continue
                close(held, i, b.o[i], "reverse")
            if len(open_pos) >= policy.max_positions or gated(sym, now):
                continue
            a = b.atr[i - 1] if i > 0 else np.nan
            if not (a > 0):
                continue
            entry = b.o[i] * (1 + side * policy.slip)
            risk_px = geometry.sl_atr * a
            stop_frac = risk_px / entry
            notional = min(policy.risk * cash / stop_frac, cash * policy.max_leverage * 0.5)
            gross_now = sum(p.qty * p.entry for p in open_pos.values())
            notional = min(notional, max(0.0, policy.max_gross * cash - gross_now))
            if notional < 10:
                continue
            leverage = float(np.clip(np.floor(0.8 / stop_frac), 1, policy.max_leverage))
            qty = notional / entry
            open_pos[sym] = Position(
                sym, side, i, entry, qty, leverage, entry - side * risk_px, entry + side * geometry.tp_atr * a, risk_px, i + geometry.horizon - 1, score, fees=policy.fee * notional
            )
        for sym, p in list(open_pos.items()):
            b = bars[sym]
            i = locate(b, now)
            if i is None or i < p.entry_i:
                continue
            if b.funding[i] and i > p.entry_i:
                p.funding -= p.side * b.funding[i] * p.qty * b.o[i]
            liq = p.entry * (1 - p.side * _liq_distance(p.leverage))
            adverse = b.low[i] if p.side > 0 else b.h[i]
            favorable = b.h[i] if p.side > 0 else b.low[i]
            if i > p.entry_i and (b.o[i] <= liq if p.side > 0 else b.o[i] >= liq):
                close(p, i, b.o[i], "liquidation")
                continue
            if (adverse <= p.stop) if p.side > 0 else (adverse >= p.stop):
                gap = (b.o[i] < p.stop) if p.side > 0 else (b.o[i] > p.stop)
                close(p, i, b.o[i] if gap and i > p.entry_i else p.stop, "stop")
                continue
            if (favorable >= p.take) if p.side > 0 else (favorable <= p.take):
                close(p, i, p.take, "take_profit")
                continue
            if policy.breakeven_at_r and p.side * (favorable - p.entry) >= policy.breakeven_at_r * p.risk_px:
                p.stop = p.entry
            if i >= p.expiry_i:
                close(p, i, b.c[i], "time")
        unrealized = 0.0
        for sym, p in open_pos.items():
            b = bars[sym]
            i = locate(b, now)
            px = b.c[i] if i is not None else p.entry
            unrealized += p.side * p.qty * (px - p.entry) - p.fees + p.funding
        curve_t.append(now)
        curve_v.append(cash + unrealized)
    trades = pd.DataFrame(closed)
    equity = pd.Series(curve_v, index=pd.to_datetime(curve_t, unit="ms", utc=True), name="equity")
    return Result(equity, trades, policy, geometry, stats(equity, trades, capital))


def stats(equity: pd.Series, trades: pd.DataFrame, capital: float) -> dict:
    if equity.empty:
        return {}
    daily = equity.resample("1D").last().ffill()
    prev = pd.concat([pd.Series([capital], index=[daily.index[0] - pd.Timedelta(days=1)]), daily]).shift(1).iloc[1:]
    ret = daily / prev - 1
    dd = equity / equity.cummax() - 1
    out = {
        "final_equity": round(float(equity.iloc[-1]), 2),
        "return_pct": round(100 * (float(equity.iloc[-1]) / capital - 1), 1),
        "days": len(daily),
        "mean_daily_pct": round(100 * float(ret.mean()), 3),
        "median_daily_pct": round(100 * float(ret.median()), 3),
        "geo_daily_pct": round(100 * float((equity.iloc[-1] / capital) ** (1 / max(len(daily), 1)) - 1), 3),
        "sharpe": round(float(ret.mean() / ret.std() * np.sqrt(365)) if ret.std() > 0 else 0.0, 2),
        "max_drawdown_pct": round(100 * float(dd.min()), 1),
        "positive_days_pct": round(100 * float((ret > 0).mean()), 1),
        "days_10pct_plus": int((ret >= 0.10).sum()),
        "trades": len(trades),
    }
    if len(trades):
        out |= {
            "win_rate": round(float((trades.pnl > 0).mean()), 3),
            "mean_r": round(float(trades.r.mean()), 3),
            "long_trades": int((trades.side == "LONG").sum()),
            "short_trades": int((trades.side == "SHORT").sum()),
            "fees_paid": round(float(trades.fees.sum()), 2),
            "funding_paid": round(float(-trades.funding.sum()), 2),
            "liquidations": int((trades.reason == "liquidation").sum()),
            "symbols_traded": int(trades.symbol.nunique()),
        }
    return out


def policy_dict(p: Policy) -> dict:
    return asdict(p)
