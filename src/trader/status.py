import json
from datetime import UTC

from sqlmodel import Session, select

from trader.core.db import create_db_and_tables, engine
from trader.models.trade import Trade
from trader.quant import paper


def notice_bot(mode: str = "paper") -> dict:
    create_db_and_tables()
    with Session(engine) as session:
        trades = list(session.exec(select(Trade).where(Trade.mode == mode)).all())
    closed = [t for t in trades if t.status == "closed"]
    wins = sum((t.pnl or 0.0) > 0 for t in closed)
    latest = sorted(trades, key=lambda t: t.entry_time, reverse=True)[:5]
    return {
        "trades": len(trades),
        "open": sum(t.status == "open" for t in trades),
        "closed": len(closed),
        "win_rate_pct": round(100 * wins / len(closed), 1) if closed else None,
        "realized_pnl": round(sum(t.pnl or 0.0 for t in closed), 2),
        "latest": [
            {
                "symbol": t.symbol,
                "side": "LONG" if t.side > 0 else "SHORT",
                "trigger": t.trigger,
                "entry_time": (t.entry_time if t.entry_time.tzinfo else t.entry_time.replace(tzinfo=UTC)).isoformat(timespec="seconds"),
                "status": t.status,
                "pnl": None if t.pnl is None else round(t.pnl, 2),
            }
            for t in latest
        ],
    }


def quant_bot() -> dict:
    path = paper.ledger_path()
    if not path.exists():
        return {"status": "not started — run `trader quant paper --loop`"}
    state = json.loads(path.read_text())
    history = state["history"]
    return {
        "since": history[0]["day"] if history else None,
        "rebalances": len(history),
        "start_equity": state["start_equity"],
        "equity": round(state["equity"], 2),
        "return_pct": round(100 * (state["equity"] / state["start_equity"] - 1), 2),
        "positions": len(state["positions"]),
        "equity_by_day": {h["day"]: h["equity"] for h in history},
        "last_rebalance": history[-1] if history else None,
    }


def summary() -> dict:
    return {"#1 Анонси (paper)": notice_bot(), "#2 Квант (paper)": quant_bot()}
