import json
import time

import numpy as np
import pandas as pd

from trader.core.config import settings
from trader.integrations import binance

TAKER, MAKER, WAIT_S, ENOUGH, MIN_DAYS = 0.0005, 0.0002, 1800, 800, 10


def path():
    return settings.data_dir / "quant" / "paper" / "limit_orders.jsonl"


def book(rest, symbols) -> dict[str, tuple[float, float]]:
    return {r["symbol"]: (float(r["bidPrice"]), float(r["askPrice"])) for r in rest.book_tickers() if r["symbol"] in symbols}


def order(symbol: str, notional: float, equity: float, before: tuple[float, float], after: tuple[float, float], bars: pd.DataFrame, t0: int) -> dict:
    side = 1 if notional > 0 else -1
    (bid, ask), mid = before, sum(before) / 2
    limit, market, late = (bid, ask, after[1]) if side > 0 else (ask, bid, after[0])
    reach = bars.low.astype(float) if side > 0 else -bars.high.astype(float)
    through, touch = bool((reach < side * limit).any()), bool((reach <= side * limit).any())
    miss = side * (late / mid - 1) + TAKER
    return {
        "symbol": symbol,
        "decided_at": t0,
        "side": "buy" if side > 0 else "sell",
        "notional": abs(notional),
        "equity": equity,
        "bid": bid,
        "ask": ask,
        "late": late,
        "filled_through": through,
        "filled_touch": touch,
        "market_cost": side * (market / mid - 1) + TAKER,
        "limit_cost_through": side * (limit / mid - 1) + MAKER if through else miss,
        "limit_cost_touch": side * (limit / mid - 1) + MAKER if touch else miss,
    }


def measure(trades: dict[str, float], equity: float, wait_s: float = WAIT_S, rest=None) -> list[dict]:
    rest = rest or binance.FuturesREST()
    t0, first = int(time.time() * 1000), book(rest, trades)
    time.sleep(wait_s)
    last, t1 = book(rest, trades), int(time.time() * 1000)
    rows = [order(s, w * equity, equity, first[s], last[s], rest.klines(s, "1m", t0, t1), t0) for s, w in trades.items() if s in first and s in last]
    path().parent.mkdir(parents=True, exist_ok=True)
    with path().open("a") as f:
        f.writelines(json.dumps(r) + "\n" for r in rows)
    return rows


def summary() -> dict:
    if not path().exists():
        return {"orders": 0, "enough": ENOUGH, "min_days": MIN_DAYS, "verdict": "collecting"}
    d = pd.DataFrame([json.loads(line) for line in path().read_text().splitlines()])
    w, x = d.notional, d.market_cost - d.limit_cost_through
    saving = float(np.average(x, weights=w))
    days = d.decided_at.nunique()
    se = float(np.sqrt(((w * (x - saving)).groupby(d.decided_at).sum() ** 2).sum() * days / (days - 1)) / w.sum()) if days > 1 else None
    daily = (d.notional * x / d.equity).groupby(d.decided_at).sum()
    verdict = "collecting" if len(d) < ENOUGH or days < MIN_DAYS else "cheaper" if saving - 2 * se > 0 else "dearer" if saving + 2 * se < 0 else "unclear"
    return {
        "orders": len(d),
        "days": int(days),
        "enough": ENOUGH,
        "min_days": MIN_DAYS,
        "first": int(d.decided_at.min()),
        "last": int(d.decided_at.max()),
        "filled_through": float(np.average(d.filled_through, weights=w)),
        "filled_touch": float(np.average(d.filled_touch, weights=w)),
        "market_cost": float(np.average(d.market_cost, weights=w)),
        "market_slippage": float(np.average(d.market_cost, weights=w)) - TAKER,
        "limit_cost_through": float(np.average(d.limit_cost_through, weights=w)),
        "limit_cost_touch": float(np.average(d.limit_cost_touch, weights=w)),
        "saving": saving,
        "saving_se": se,
        "saving_touch": float(np.average(d.market_cost - d.limit_cost_touch, weights=w)),
        "saving_per_day_pct": 100 * float(daily.mean()),
        "verdict": verdict,
    }
