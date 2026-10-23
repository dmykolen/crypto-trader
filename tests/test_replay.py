import asyncio
from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd
import pytest
from sqlmodel import Session

from trader.core.db import create_db_and_tables, engine
from trader.models import NewsItem
from trader.services import news, replay
from trader.services.events import EventType, Notice
from trader.services.fast import FastPlaybook

T0 = datetime(2026, 10, 19, 7, 40, tzinfo=UTC)
MS = int(T0.timestamp() * 1000)


def _tape() -> replay.Tape:
    tape = replay.Tape()
    minutes = np.arange(MS - 3_600_000, MS + 7_200_000, 60_000)
    tape.add_bars(pd.DataFrame({"open_time": minutes, "open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0}))
    after = np.arange(MS + 2_000, MS + 2_400_000, 1000)
    t = np.concatenate([np.arange(MS - 60_000, MS, 1000), MS + np.array([1_100, 1_200, 1_400]), after])
    p = np.concatenate([np.full(60, 100.0), [110.0, 112.0, 111.0], np.full(len(after), 120.0)])
    tape.add_ticks(pd.DataFrame({"price": p, "quantity": 1.0, "transact_time": t, "is_buyer_maker": False}))
    return tape


def _replay(latency: float) -> list:
    create_db_and_tables()
    notice = Notice("upbit", f"replay-{latency}", "콘크리트(CT) 신규 거래지원 안내 (KRW, BTC, USDT 마켓)", T0)
    with Session(engine) as session:
        news.store_new(session, [news.to_item(notice)])
    quick = {EventType.UPBIT_KRW_LISTING: [(1.0, FastPlaybook(side=1, hold_s=120, leverage=5.0, stop=0.0, take_profit=0.0))]}
    trades = asyncio.run(replay.run(T0 - timedelta(hours=1), T0 + timedelta(hours=1), {"upbit": latency, "binance": latency}, {}, quick, {"CTUSDT"}, {"CTUSDT": _tape()}))
    with Session(engine) as session:
        session.delete(session.get(NewsItem, f"upbit:replay-{latency}"))
        session.commit()
    return trades


def test_the_replayed_trader_buys_a_listing_at_the_worst_price_after_its_reaction_time_and_sells_when_the_hold_ends():
    [trade] = _replay(1.0)
    assert trade.entry_price == pytest.approx(112.0 * (1 + replay.FAST_SLIPPAGE))
    assert trade.exit_reason == "time"
    assert trade.exit_price == pytest.approx(120.0 * (1 - replay.FAST_SLIPPAGE))
    assert replay._aware(trade.exit_time) - replay._aware(trade.entry_time) == timedelta(seconds=120)
    assert trade.pnl == pytest.approx(trade.quantity * (trade.exit_price - trade.entry_price) - trade.fees)


def test_the_replayed_trader_stays_out_when_it_would_see_the_notice_too_late_for_its_playbooks():
    assert _replay(5.0) == []
