"""Trading loop: playbook entries, exits, risk rails — against a fake broker, no network."""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlmodel import Session, select

from trader.core.config import settings
from trader.core.db import create_db_and_tables, engine
from trader.models import Trade
from trader.services import trading
from trader.services.broker import Fill
from trader.services.events import Event, EventType, Notice
from trader.services.playbooks import Playbook

SYMBOLS = ["WIFUSDT", "1000PEPEUSDT", "AAAUSDT", "BBBUSDT", "CCCUSDT", "DDDUSDT"]


class FakeBroker:
    mode = "paper"

    def __init__(self, prices: dict[str, float]) -> None:
        self.prices = prices

    async def price(self, symbol):
        return self.prices[symbol]

    async def equity(self):
        return None

    async def open(self, symbol, side, qty, leverage):
        return Fill(self.prices[symbol], qty, 0.0)

    async def protect(self, symbol, side, qty, stop):
        return None

    async def close(self, symbol, side, qty):
        return Fill(self.prices[symbol], qty, 0.0)

    async def aclose(self):
        return None


class FakeREST:
    def exchange_info(self):
        return {"symbols": [{"symbol": s, "status": "TRADING", "contractType": "PERPETUAL"} for s in SYMBOLS]}


@pytest.fixture(autouse=True)
def _empty_journal():
    create_db_and_tables()
    with Session(engine) as session:
        for t in session.exec(select(Trade)).all():
            session.delete(t)
        session.commit()


def make_trader(**prices: float) -> trading.Trader:
    trader = trading.Trader(FakeBroker(dict.fromkeys(SYMBOLS, 1.0) | prices), rest=FakeREST())
    trader.playbooks = {}
    return trader


def open_(trader, symbol="WIFUSDT", side=1, leverage=2.0, *, stop=0.0, take_profit=0.0, trail=0.0, hold=timedelta(hours=4)):
    return trader.open_position(symbol, side, leverage, stop=stop, take_profit=take_profit, trail=trail, hold=hold, trigger="test")


def reload(trade_id: int) -> Trade:
    with Session(engine) as session:
        return session.get(Trade, trade_id)


def test_short_is_stopped_out():
    async def scenario():
        trader = make_trader(WIFUSDT=2.0)
        trade = await open_(trader, side=-1, leverage=3.0, stop=0.1, take_profit=0.2)
        assert trade.margin == pytest.approx(200.0) and trade.quantity == pytest.approx(300.0)
        assert trade.stop_price == pytest.approx(2.2) and trade.take_profit_price == pytest.approx(1.6)
        trader.broker.prices["WIFUSDT"] = 2.25
        await trader.monitor()
        return trade.id

    closed = reload(asyncio.run(scenario()))
    assert (closed.status, closed.exit_reason) == ("closed", "stop")
    assert closed.pnl == pytest.approx(-75.0)


def test_trailing_stop_locks_in_profit():
    async def scenario():
        trader = make_trader()
        trade = await open_(trader, stop=0.05, trail=0.1)
        for price in (1.2, 1.5):
            trader.broker.prices["WIFUSDT"] = price
            await trader.monitor()
        assert reload(trade.id).stop_price == pytest.approx(1.35)
        trader.broker.prices["WIFUSDT"] = 1.34
        await trader.monitor()
        return trade.id

    closed = reload(asyncio.run(scenario()))
    assert closed.exit_reason == "stop" and closed.pnl == pytest.approx(400 * 0.34)


def test_take_profit_time_exit_and_liquidation():
    async def scenario():
        trader = make_trader()
        tp = await open_(trader, "AAAUSDT", take_profit=0.1)
        timed = await open_(trader, "BBBUSDT", hold=timedelta(0))
        liq = await open_(trader, "CCCUSDT", leverage=10.0)
        trader.broker.prices.update(AAAUSDT=1.12, CCCUSDT=0.85)
        await trader.monitor()
        return tp.id, timed.id, liq.id

    tp, timed, liq = (reload(i) for i in asyncio.run(scenario()))
    assert tp.exit_reason == "take_profit" and tp.pnl == pytest.approx(400 * 0.12)
    assert timed.exit_reason == "time" and timed.pnl == pytest.approx(0.0)
    assert liq.exit_reason == "liquidation" and liq.pnl == pytest.approx(-200.0)


def test_risk_rails():
    async def scenario():
        trader = make_trader()
        assert await open_(trader, "WIFUSDT") is not None
        assert await open_(trader, "WIFUSDT") is None
        for symbol in SYMBOLS[1:5]:
            assert await open_(trader, symbol) is not None
        assert await open_(trader, SYMBOLS[5]) is None

    asyncio.run(scenario())


def test_daily_loss_limit_blocks_new_positions():
    async def scenario():
        trader = make_trader()
        await open_(trader, leverage=10.0)
        trader.broker.prices["WIFUSDT"] = 0.85
        await trader.monitor()
        return await open_(trader, "AAAUSDT")

    assert asyncio.run(scenario()) is None


def test_one_announcement_is_capped_as_one_bet():
    async def scenario():
        trader = make_trader()
        kw = {"stop": 0.0, "take_profit": 0.0, "trail": 0.0, "hold": timedelta(hours=4), "trigger": "delisting basket", "news_id": "binance:42"}
        first = await trader.open_position("AAAUSDT", -1, 2.0, **kw)
        second = await trader.open_position("BBBUSDT", -1, 2.0, **kw)
        third = await trader.open_position("CCCUSDT", -1, 2.0, **kw)
        other = await trader.open_position("DDDUSDT", -1, 2.0, **kw | {"news_id": "binance:43"})
        return first, second, third, other

    first, second, third, other = asyncio.run(scenario())
    assert (first.margin, second.margin) == (pytest.approx(200.0), pytest.approx(100.0))
    assert third is None and other.margin == pytest.approx(200.0)


def test_event_enters_with_its_playbook_at_the_backtested_time(monkeypatch):
    monkeypatch.setattr(settings, "entry_latency_s", 60)
    short = Playbook(side=-1, delay_min=0, stop=0.1, take_profit=0.0, trail=0.0, hold_min=240, leverage=3.0)

    async def scenario():
        trader = make_trader()
        trader.playbooks = {EventType.BINANCE_SPOT_DELISTING: short}
        fresh = Notice("binance", "n1", "Binance Will Delist PEPE on 2026-11-01", datetime.now(UTC) - timedelta(seconds=61))
        task = await trader.on_event(Event(EventType.BINANCE_SPOT_DELISTING, "PEPE", fresh))
        assert task is not None
        await task
        stale = Notice("binance", "n2", "Binance Will Delist WIF on 2026-11-01", datetime.now(UTC) - timedelta(hours=2))
        assert await trader.on_event(Event(EventType.BINANCE_SPOT_DELISTING, "WIF", stale)) is None
        assert await trader.on_event(Event(EventType.UPBIT_WARNING, "WIF", fresh)) is None

    asyncio.run(scenario())
    with Session(engine) as session:
        (trade,) = session.exec(select(Trade)).all()
    assert (trade.symbol, trade.side, trade.leverage) == ("1000PEPEUSDT", -1, 3.0)
    assert trade.trigger.startswith("binance_spot_delisting: SHORT 3x")
