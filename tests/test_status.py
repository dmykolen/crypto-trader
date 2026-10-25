import json
from datetime import UTC, datetime, timedelta

from sqlmodel import Session

from trader.core.db import create_db_and_tables, engine
from trader.models.trade import Trade
from trader.quant import paper
from trader.status import notice_bot, quant_bot


def _trade(symbol: str, pnl: float | None, status: str, minutes_ago: int) -> Trade:
    at = datetime.now(UTC) - timedelta(minutes=minutes_ago)
    return Trade(
        mode="paper",
        symbol=symbol,
        side=1,
        leverage=5,
        margin=100,
        quantity=1,
        entry_price=10,
        entry_time=at,
        best_price=10,
        exit_due=at + timedelta(minutes=30),
        trigger="upbit_krw_listing",
        status=status,
        pnl=pnl,
    )


def test_status_reports_the_notice_bot_paper_record_and_the_quant_ledger():
    create_db_and_tables()
    before = notice_bot()
    with Session(engine) as session:
        session.add_all([_trade("STATUSAUSDT", 12.5, "closed", 30), _trade("STATUSBUSDT", -2.5, "closed", 20), _trade("STATUSCUSDT", None, "open", 10)])
        session.commit()
    after = notice_bot()
    assert after["trades"] - before["trades"] == 3
    assert after["open"] - before["open"] == 1
    assert after["closed"] - before["closed"] == 2
    assert after["realized_pnl"] - before["realized_pnl"] == 10.0
    path = paper.ledger_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [{"day": "2026-10-24", "equity": 998.46}, {"day": "2026-10-25", "equity": 1010.0}]
    path.write_text(json.dumps({"start_equity": 1000.0, "equity": 1010.0, "positions": {"BTCUSDT": {"weight": 0.2, "entry": 1.0}}, "history": rows}))
    bot2 = quant_bot()
    assert bot2["return_pct"] == 1.0
    assert bot2["since"] == "2026-10-24" and bot2["rebalances"] == 2
    assert bot2["equity_by_day"] == {"2026-10-24": 998.46, "2026-10-25": 1010.0}
