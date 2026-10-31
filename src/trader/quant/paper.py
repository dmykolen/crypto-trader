import json
import logging
import time
from datetime import UTC, datetime, timedelta

import pandas as pd

from trader.core.config import settings
from trader.integrations import binance
from trader.quant import limit_test, live, neutral
from trader.quant.trend import COST, DAY

log = logging.getLogger(__name__)
HOUR = 3_600_000


def ledger_path():
    return settings.data_dir / "quant" / "paper" / "ledger.json"


def _load(capital: float) -> dict:
    path = ledger_path()
    if path.exists():
        return json.loads(path.read_text())
    return {"start_equity": capital, "equity": capital, "positions": {}, "history": []}


def target_book(now: datetime) -> tuple[dict[str, float], dict[str, float], dict[str, pd.DataFrame]]:
    """The book decided at yesterday's 23:00 UTC close from fresh quotes: target weights, last prices, the quotes."""
    today = datetime(now.year, now.month, now.day, tzinfo=UTC)
    bars = live.collect(today - timedelta(days=62), now)
    p = live.panel(bars)
    raw = live.scores(bars, live._ms(today))
    edge = neutral.daily_scores(raw, live.DECISION_HOUR)["edge"]
    xs7 = raw.pivot_table(index=(raw.open_time // DAY * DAY), columns="symbol", values="xs", aggfunc="last")
    w = neutral.production_weights(p, {"blend": neutral.blend(xs7, edge), "edge": edge})
    decided = w.loc[w.index < live._ms(today)].iloc[-1]
    last = {sym: float(b.close.iloc[-1]) for sym, b in bars.items()}
    return {s: float(v) for s, v in decided.items()}, last, bars


def marks(symbols: list[str]) -> dict[str, float]:
    rest, out = binance.FuturesREST(), {}
    for sym in symbols:
        try:
            out[sym] = rest.last_price(sym)
        except Exception:
            log.warning("no price for held %s, marking it at its last rebalance price", sym)
    return out


def step(capital: float = 1000.0, now: datetime | None = None) -> dict:
    now = now or datetime.now(UTC)
    today = datetime(now.year, now.month, now.day, tzinfo=UTC)
    state = _load(capital)
    if state["history"] and state["history"][-1]["day"] == f"{today:%Y-%m-%d}":
        return {"skipped": "already rebalanced today", **state["history"][-1]}
    target, last, bars = target_book(now)
    last |= marks([s for s in state["positions"] if s not in last])
    since = live._ms(datetime.fromisoformat(state["history"][-1]["rebalanced_at"])) if state["history"] else live._ms(now)
    funding = {sym: float(b.funding[b.open_time >= since].sum()) for sym, b in bars.items() if sym in state["positions"]}
    row = rebalance(state, target, last, today, now, funding, neutral.ENSEMBLE["band"])
    path = ledger_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2))
    tmp.replace(path)
    return row


def rebalance(state: dict, target: dict[str, float], last: dict[str, float], today: datetime, now: datetime, funding: dict[str, float] | None = None, band: float = 0.0) -> dict:
    """Mark the held book to `last` prices and charge its funding, then trade each name whose target drifted past `band` from its held weight."""
    before = state["equity"]
    pnl = 0.0
    paid = 0.0
    notional = {}
    for sym, pos in state["positions"].items():
        price = last.get(sym, pos["entry"])
        notional[sym] = pos["weight"] * before * price / pos["entry"]
        pnl += pos["weight"] * before * (price / pos["entry"] - 1)
        paid += pos["weight"] * before * (funding or {}).get(sym, 0.0)
    pnl -= paid
    equity = before + pnl
    held = {s: n / equity for s, n in notional.items()}
    new = {}
    for sym, tgt in target.items():
        if abs(tgt) <= 1e-9 or sym not in last:
            continue
        cur = held.get(sym, 0.0)
        new[sym] = cur if cur and abs(tgt - cur) <= band else tgt
    trades = {s: new.get(s, 0.0) - held.get(s, 0.0) for s in sorted(set(held) | set(new))}
    turnover = sum(map(abs, trades.values()))
    cost = COST * turnover * equity
    state["equity"] = equity - cost
    state["positions"] = {s: {"weight": v * equity / state["equity"], "entry": last[s]} for s, v in new.items()}
    row = {
        "day": f"{today:%Y-%m-%d}",
        "rebalanced_at": now.isoformat(timespec="seconds"),
        "equity": round(state["equity"], 2),
        "pnl_since_last": round(pnl, 2),
        "funding_paid": round(paid, 2),
        "cost": round(cost, 2),
        "turnover": round(turnover, 3),
        "longs": sum(v > 0 for v in new.values()),
        "shorts": sum(v < 0 for v in new.values()),
        "gross": round(sum(abs(v) for v in new.values()), 3),
        "return_since_start_pct": round(100 * (state["equity"] / state["start_equity"] - 1), 2),
        "trades": {s: round(v, 6) for s, v in trades.items() if abs(v) > 1e-9},
        "book": {s: round(p["weight"], 6) for s, p in state["positions"].items()},
    }
    state["history"].append(row)
    return row


def loop(capital: float = 1000.0, at_minute: int = 15, retry_minutes: int = 15) -> None:
    while True:
        now = datetime.now(UTC)
        due = datetime(now.year, now.month, now.day, 0, at_minute, tzinfo=UTC)
        if now >= due:
            row = {}
            try:
                row = step(capital, now)
                log.warning("quant paper rebalance: %s", {k: v for k, v in row.items() if k not in ("trades", "book")})
                due += timedelta(days=1)
            except Exception:
                log.exception("quant paper rebalance failed, retrying in %d minutes", retry_minutes)
                due = datetime.now(UTC) + timedelta(minutes=retry_minutes)
            if row.get("day") and "skipped" not in row:
                try:
                    from trader.quant import why

                    why.build(row["day"])
                except Exception:
                    log.exception("quant ranking record failed")
            if row.get("trades") and "skipped" not in row:
                try:
                    rows = limit_test.measure(row["trades"], row["equity"])
                    log.warning("quant limit-order test: %d orders, %d filled through the limit", len(rows), sum(r["filled_through"] for r in rows))
                except Exception:
                    log.exception("quant limit-order test failed")
        time.sleep(max(30.0, (due - datetime.now(UTC)).total_seconds()))
