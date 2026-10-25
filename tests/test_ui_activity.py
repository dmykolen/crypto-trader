from datetime import UTC, datetime, timedelta

import pytest
from sqlmodel import Session

from trader.core.db import create_db_and_tables, engine
from trader.models import NewsItem, Trade
from trader.services import processes
from trader.transports.http import ui

AT = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)


@pytest.fixture
def quiet_desk(monkeypatch, tmp_path):
    monkeypatch.setattr(processes, "_ps", lambda: [])
    monkeypatch.setattr(ui.jobs, "listing", lambda limit: [])
    monkeypatch.setattr(ui.paper, "ledger_path", lambda: tmp_path / "no-ledger.json")


def _trade(mode: str, symbol: str, entry: datetime, **extra) -> Trade:
    return Trade(
        mode=mode,
        symbol=symbol,
        side=1,
        leverage=2,
        margin=10,
        quantity=1,
        entry_price=1.0,
        entry_time=entry,
        best_price=1.0,
        exit_due=entry + timedelta(hours=1),
        trigger="upbit_krw_listing: LONG 2x, enter +1m, hold ≤60m",
        **extra,
    )


def test_the_tape_and_trade_list_carry_only_the_bots_own_trades_as_utc_facts(client, quiet_desk):
    create_db_and_tables()
    with Session(engine) as session:
        session.add(_trade("paper", "TAPEPAPERUSDT", AT, status="closed", exit_time=AT + timedelta(minutes=30), exit_price=1.1, exit_reason="take_profit", pnl=2.0))
        session.add(_trade("replay", "TAPEREPLAYUSDT", AT + timedelta(minutes=5)))
        session.commit()

    events = [e for e in client.get("/api/v1/overview").json()["events"] if e.get("symbol", "").startswith("TAPE")]
    assert [(e["kind"], e["symbol"]) for e in events] == [("trade_close", "TAPEPAPERUSDT"), ("trade_open", "TAPEPAPERUSDT")]
    closed = events[0]
    assert closed["pnl"] == 2.0 and closed["exit_reason"] == "take_profit" and closed["side"] == "long" and closed["mode"] == "paper"
    assert datetime.fromisoformat(closed["at"]) == AT + timedelta(minutes=30)

    listed = [t for t in client.get("/api/v1/notice/trades").json() if t["symbol"].startswith("TAPE")]
    assert [t["symbol"] for t in listed] == ["TAPEPAPERUSDT"]
    assert datetime.fromisoformat(listed[0]["entry_time"]) == AT


def test_notices_are_counted_per_utc_day_with_their_tradable_share(client):
    create_db_and_tables()
    today = datetime.now(UTC).replace(hour=0, minute=30, second=0, microsecond=0)
    with Session(engine) as session:
        session.add(NewsItem(id="binance:daily-1", source="binance", title="listing", published_at=today, events=[{"type": "binance_perp_listing", "symbols": ["NEWUSDT"]}]))
        session.add(NewsItem(id="upbit:daily-2", source="upbit", title="notice", published_at=today + timedelta(minutes=10), events=[]))
        session.add(NewsItem(id="binance:daily-3", source="binance", title="old", published_at=today - timedelta(days=30), events=[]))
        session.commit()

    days = client.get("/api/v1/notice/daily", params={"days": 3}).json()
    assert [d["day"] for d in days] == [(today - timedelta(days=n)).date().isoformat() for n in (2, 1, 0)]
    assert days[-1]["total"] >= 2 and days[-1]["events"] >= 1
    assert days[-1]["total"] - days[-1]["events"] >= 1
