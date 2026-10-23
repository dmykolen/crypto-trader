import asyncio
import time
from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd
from sqlmodel import Session, select
from test_trading import SYMBOLS, FakeBroker, FakeREST

from trader.core.db import create_db_and_tables, engine
from trader.models import Trade
from trader.services import fast, ticks, trading
from trader.services.events import EventType, Notice
from trader.services.fast import FastPlaybook


def synthetic_frame(n: int = 12, move: float = -0.1) -> pd.DataFrame:
    rows = []
    for i in range(n):
        row = {"type": "binance_monitoring_tag", "symbol": "WIFUSDT", "ts": 1_700_000_000_000 + i * 86_400_000, "pre_1": 0.0}
        for hold in ticks.HOLDS_S:
            key = f"1_{hold}"
            up, down = max(move, 0.0), min(move, 0.0)
            row |= {f"rl_{key}": move, f"rs_{key}": move, f"mfel_{key}": up, f"mael_{key}": down, f"mfes_{key}": up, f"maes_{key}": down}
        rows.append(row)
    return pd.DataFrame(rows)


def test_fit_learns_to_short_a_notice_that_dumps_the_price():
    fitted = fast.fit(synthetic_frame(n=30), latency=1.0)
    pb = fitted["binance_monitoring_tag"]["playbook"]
    assert pb["side"] == -1
    assert fitted["binance_monitoring_tag"]["oos_mean_ret"] > 0


def test_a_trade_never_loses_more_than_its_margin():
    matrix = ticks.outcome_matrix(synthetic_frame(n=1, move=0.5), 1)
    shorts_10x_no_stop = [j for j, c in enumerate(ticks.CANDIDATES) if c[0] == -1 and c[2] == 10.0 and c[3] == 0.0]
    assert np.all(matrix[0, shorts_10x_no_stop] == -1.0)
    assert np.nanmin(matrix) >= -1.0


def make_fast_trader() -> trading.Trader:
    create_db_and_tables()
    with Session(engine) as session:
        for t in session.exec(select(Trade)).all():
            session.delete(t)
        session.commit()
    trader = trading.Trader(FakeBroker(dict.fromkeys(SYMBOLS, 1.0)), rest=FakeREST())
    trader.playbooks = {}
    trader.fast = {EventType.BINANCE_MONITORING_TAG: [(3.0, FastPlaybook(-1, 30, 2.0, 0.0, 0.0))]}
    return trader


def notice(seconds_old: float, title: str = "Binance Will Extend the Monitoring Tag to Include WIF") -> tuple[Notice, float]:
    received = time.time()
    return Notice("binance", f"ws-{received}", title, datetime.fromtimestamp(received - seconds_old, UTC)), received


def test_fast_notice_opens_at_once_and_only_once():
    trader = make_fast_trader()
    trades = asyncio.run(trader.on_fast_notice(*notice(0.4)))
    assert [(t.symbol, t.side) for t in trades] == [("WIFUSDT", -1)]
    assert timedelta(seconds=25) < trades[0].exit_due.replace(tzinfo=UTC) - datetime.now(UTC) <= timedelta(seconds=30)
    assert asyncio.run(trader.on_fast_notice(*notice(0.6))) == []


def test_fast_notice_seen_too_late_is_not_traded():
    trader = make_fast_trader()
    assert asyncio.run(trader.on_fast_notice(*notice(10.0, "Binance Will Extend the Monitoring Tag to Include PEPE"))) == []


def test_fast_trade_is_closed_when_its_hold_expires():
    trader = make_fast_trader()

    async def scenario():
        [trade] = await trader.on_fast_notice(*notice(0.2))
        await trader._exit_at(trade.id, datetime.now(UTC))
        with Session(engine) as session:
            return session.get(Trade, trade.id)

    closed = asyncio.run(scenario())
    assert (closed.status, closed.exit_reason) == ("closed", "time")


def test_the_playbook_matches_how_late_the_notice_was_seen():
    quick, slow = FastPlaybook(-1, 30, 10.0, 0.02, 0.0), FastPlaybook(-1, 300, 2.0, 0.05, 0.0)
    options = [(1.0, quick), (3.0, slow)]
    assert fast.for_latency(options, 0.4) == quick
    assert fast.for_latency(options, 2.5) == slow
    assert fast.for_latency(options, 4.0) is None
