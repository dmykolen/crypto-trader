import json

import pandas as pd
import pytest

from trader.core.config import settings
from trader.quant import limit_test
from trader.quant.limit_test import MAKER, TAKER

T0 = 1_793_300_000_000


def _bars(low: list[float], high: list[float]) -> pd.DataFrame:
    return pd.DataFrame({"low": [str(v) for v in low], "high": [str(v) for v in high]})


def test_a_buy_resting_at_the_bid_fills_once_the_price_trades_below_it():
    row = limit_test.order("AUSDT", 100.0, 1000.0, (99.9, 100.1), (100.0, 100.2), _bars([100.0, 99.8], [100.2, 100.1]), T0)
    assert row["side"] == "buy" and row["filled_through"] and row["filled_touch"]
    assert row["market_cost"] == pytest.approx(0.001 + TAKER)
    assert row["limit_cost_through"] == pytest.approx(-0.001 + MAKER)


def test_a_sell_that_was_only_touched_counts_as_missed_and_pays_the_later_bid_at_market():
    row = limit_test.order("AUSDT", -50.0, 1000.0, (99.9, 100.1), (99.0, 99.1), _bars([99.5, 99.2], [100.1, 99.8]), T0)
    assert row["side"] == "sell" and not row["filled_through"] and row["filled_touch"]
    assert row["market_cost"] == pytest.approx(0.001 + TAKER)
    assert row["limit_cost_through"] == pytest.approx(0.01 + TAKER)
    assert row["limit_cost_touch"] == pytest.approx(-0.001 + MAKER)


class FakeRest:
    def __init__(self):
        self.books = [[{"symbol": "AUSDT", "bidPrice": "99.9", "askPrice": "100.1"}, {"symbol": "BUSDT", "bidPrice": "9.99", "askPrice": "10.01"}]] * 2

    def book_tickers(self):
        return self.books.pop(0)

    def klines(self, symbol, interval, start_ms, end_ms):
        assert interval == "1m" and start_ms <= end_ms
        return _bars([99.8], [100.0]) if symbol == "AUSDT" else _bars([9.995], [10.0])


def test_each_rebalance_order_is_journaled_and_summarised(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    assert limit_test.summary()["verdict"] == "collecting"
    rows = limit_test.measure({"AUSDT": 0.1, "BUSDT": 0.05, "CUSDT": -0.1}, 1000.0, wait_s=0, rest=FakeRest())
    assert [r["symbol"] for r in rows] == ["AUSDT", "BUSDT"]
    assert [json.loads(line)["symbol"] for line in limit_test.path().read_text().splitlines()] == ["AUSDT", "BUSDT"]
    s = limit_test.summary()
    assert s["orders"] == 2 and s["days"] == 1 and s["verdict"] == "collecting" and s["saving_se"] is None
    assert s["filled_through"] == pytest.approx(100 / 150)


def test_the_verdict_needs_enough_orders_and_a_saving_beyond_two_standard_errors(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    base = {"symbol": "AUSDT", "side": "buy", "notional": 10.0, "equity": 1000.0, "bid": 1.0, "ask": 1.0, "late": 1.0, "filled_through": True, "filled_touch": True}
    costs = {"market_cost": 0.0008, "limit_cost_touch": 0.0002}
    rows = [{**base, **costs, "decided_at": T0 + i // 50, "limit_cost_through": 0.0002 + 0.0001 * (i % 2)} for i in range(limit_test.ENOUGH)]
    limit_test.path().parent.mkdir(parents=True)
    limit_test.path().write_text("".join(json.dumps(r) + "\n" for r in rows))
    s = limit_test.summary()
    assert s["verdict"] == "cheaper"
    assert s["saving"] == pytest.approx(0.00055)
    assert s["saving_per_day_pct"] == pytest.approx(100 * 50 * 10 * 0.00055 / 1000)


def test_orders_of_one_day_move_with_the_market_so_the_error_is_counted_per_day(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    base = {"symbol": "AUSDT", "side": "buy", "notional": 10.0, "equity": 1000.0, "late": 1.0, "filled_through": False, "filled_touch": False, "market_cost": 0.0008}
    days = [(T0, 0.001), (T0 + 1, -0.0008)]
    stamps = [(t + i, s) for t, s in days for i in range(0, 2 * limit_test.MIN_DAYS, 2)]
    rows = [{**base, "decided_at": t, "limit_cost_through": 0.0008 - s, "limit_cost_touch": 0.0008 - s} for t, s in stamps for _ in range(limit_test.ENOUGH // 20)]
    limit_test.path().parent.mkdir(parents=True)
    limit_test.path().write_text("".join(json.dumps(r) + "\n" for r in rows))
    s = limit_test.summary()
    assert s["saving"] == pytest.approx(0.0001)
    assert s["saving_se"] == pytest.approx(0.0009 / 20**0.5 * (20 / 19) ** 0.5)
    assert s["verdict"] == "unclear"
