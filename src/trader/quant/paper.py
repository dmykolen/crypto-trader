import json
import logging
import time
from datetime import UTC, datetime, timedelta

from trader.core.config import settings
from trader.quant import live, neutral
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


def step(capital: float = 1000.0, now: datetime | None = None) -> dict:
    now = now or datetime.now(UTC)
    today = datetime(now.year, now.month, now.day, tzinfo=UTC)
    state = _load(capital)
    if state["history"] and state["history"][-1]["day"] == f"{today:%Y-%m-%d}":
        return {"skipped": "already rebalanced today", **state["history"][-1]}
    bars = live.collect(today - timedelta(days=62), now)
    p = live.panel(bars)
    raw = live.scores(bars, live._ms(today))
    edge = neutral.daily_scores(raw, live.DECISION_HOUR)["edge"]
    xs7 = raw.pivot_table(index=(raw.open_time // DAY * DAY), columns="symbol", values="xs", aggfunc="last")
    w = neutral.production_weights(p, {"blend": neutral.blend(xs7, edge), "edge": edge})
    decided = w.loc[w.index < live._ms(today)].iloc[-1]
    last = {sym: float(b.close.iloc[-1]) for sym, b in bars.items()}
    row = rebalance(state, {s: float(v) for s, v in decided.items()}, last, today, now)
    path = ledger_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2))
    return row


def rebalance(state: dict, target: dict[str, float], last: dict[str, float], today: datetime, now: datetime) -> dict:
    """Mark the held book to `last` prices, move it to `target` weights paying costs on the traded notional, append the day to the ledger."""
    pnl = 0.0
    for sym, pos in state["positions"].items():
        price = last.get(sym)
        if price:
            pnl += pos["weight"] * state["equity"] * (price / pos["entry"] - 1)
    equity = state["equity"] + pnl
    old = {s: pos["weight"] for s, pos in state["positions"].items()}
    new = {s: v for s, v in target.items() if abs(v) > 1e-9 and s in last}
    turnover = sum(abs(new.get(s, 0.0) - old.get(s, 0.0)) for s in set(old) | set(new))
    cost = COST * turnover * equity
    equity -= cost
    state["equity"] = equity
    state["positions"] = {s: {"weight": v, "entry": last[s]} for s, v in new.items()}
    row = {
        "day": f"{today:%Y-%m-%d}",
        "rebalanced_at": now.isoformat(timespec="seconds"),
        "equity": round(equity, 2),
        "pnl_since_last": round(pnl, 2),
        "cost": round(cost, 2),
        "turnover": round(turnover, 3),
        "longs": sum(v > 0 for v in new.values()),
        "shorts": sum(v < 0 for v in new.values()),
        "gross": round(sum(abs(v) for v in new.values()), 3),
        "return_since_start_pct": round(100 * (equity / state["start_equity"] - 1), 2),
    }
    state["history"].append(row)
    return row


def loop(capital: float = 1000.0, at_minute: int = 15) -> None:
    while True:
        now = datetime.now(UTC)
        due = datetime(now.year, now.month, now.day, 0, at_minute, tzinfo=UTC)
        if now >= due:
            try:
                log.warning("quant paper rebalance: %s", step(capital, now))
            except Exception:
                log.exception("quant paper rebalance failed")
            due += timedelta(days=1)
        time.sleep(max(30.0, (due - datetime.now(UTC)).total_seconds()))
