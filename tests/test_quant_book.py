from datetime import UTC, datetime

import numpy as np
import pandas as pd
import pytest

from trader.quant import neutral, paper
from trader.quant.trend import COST, Panel

DAY = 86_400_000


def _panel(close: pd.DataFrame) -> Panel:
    return Panel(close.index.to_numpy(), close.columns.to_numpy(), close, close * 1.01, close * 0.99, close, close * 0 + 1e8, close * 0, close.pct_change(fill_method=None))


def test_the_beta_hedge_leaves_the_book_with_no_exposure_to_bitcoin():
    rng = np.random.default_rng(3)
    btc = rng.normal(0, 0.03, 200)
    rets = pd.DataFrame({"BTCUSDT": btc, "HIGHUSDT": 2.0 * btc, "LOWUSDT": 0.5 * btc}, index=pd.RangeIndex(0, 200 * DAY, DAY))
    p = _panel(100 * (1 + rets).cumprod())
    w = pd.DataFrame({"BTCUSDT": 0.0, "HIGHUSDT": 0.5, "LOWUSDT": -0.5}, index=rets.index)
    hedged = neutral.beta_hedge(p, w, lookback=60)
    last = hedged.iloc[-1]
    assert last["BTCUSDT"] == pytest.approx(-(0.5 * 2.0 - 0.5 * 0.5), abs=1e-6)
    book = (hedged.shift(1) * p.r).sum(axis=1).iloc[-100:]
    assert book.abs().max() < 1e-9


def test_compressing_a_book_keeps_the_strongest_names_and_the_gross_of_each_side():
    w = pd.DataFrame([[0.4, 0.3, 0.2, 0.1, -0.05, -0.15, -0.3, -0.5]], columns=list("ABCDEFGH"))
    out = neutral.compress(w, per_side=2).iloc[0]
    assert set(out[out > 0].index) == {"A", "B"}
    assert set(out[out < 0].index) == {"G", "H"}
    assert out[out > 0].sum() == pytest.approx(1.0)
    assert out[out < 0].sum() == pytest.approx(-1.0)


def test_the_production_book_caps_every_short_before_hedging():
    days = pd.RangeIndex(0, 60 * DAY, DAY)
    symbols = ["BTCUSDT"] + [f"S{i}USDT" for i in range(40)]
    rng = np.random.default_rng(11)
    close = pd.DataFrame(100 * np.cumprod(1 + rng.normal(0, 0.02, (60, 41)), axis=0), index=days, columns=symbols)
    score = pd.DataFrame(np.tile(np.arange(41, dtype=float), (60, 1)), index=days, columns=symbols)
    w = neutral.production_weights(_panel(close), {"blend": score})
    alts = w.drop(columns="BTCUSDT")
    assert alts.min().min() >= -0.04 - 1e-12
    last = alts.iloc[-1]
    assert 0 < (last > 0).sum() <= 30
    assert set(last[last > 0].index) <= {f"S{i}USDT" for i in range(20, 40)}
    assert set(last[last < 0].index) <= {f"S{i}USDT" for i in range(0, 19)}


def test_the_paper_ledger_marks_the_book_to_market_and_pays_costs_on_what_it_trades():
    state = {"start_equity": 1000.0, "equity": 1000.0, "positions": {"AUSDT": {"weight": 0.5, "entry": 10.0}, "BUSDT": {"weight": -0.5, "entry": 20.0}}, "history": []}
    day = datetime(2026, 10, 25, tzinfo=UTC)
    row = paper.rebalance(state, {"AUSDT": 0.5, "CUSDT": -0.5}, {"AUSDT": 11.0, "BUSDT": 22.0, "CUSDT": 5.0}, day, day)
    assert row["pnl_since_last"] == pytest.approx(0.5 * 1000 * 0.1 - 0.5 * 1000 * 0.1)
    assert row["turnover"] == pytest.approx(0.05 + 0.55 + 0.5)
    assert state["equity"] == pytest.approx(1000.0 - COST * 1.1 * 1000.0)
    assert set(state["positions"]) == {"AUSDT", "CUSDT"}
    assert state["positions"]["AUSDT"]["entry"] == 11.0
    assert state["positions"]["CUSDT"]["weight"] * state["equity"] == pytest.approx(-500.0)
    assert state["history"] == [row]


def test_longs_pay_and_shorts_receive_positive_funding_and_small_drifts_stay_inside_the_band():
    state = {"start_equity": 1000.0, "equity": 1000.0, "positions": {"AUSDT": {"weight": 0.5, "entry": 10.0}, "BUSDT": {"weight": -0.5, "entry": 20.0}}, "history": []}
    day = datetime(2026, 10, 26, tzinfo=UTC)
    row = paper.rebalance(state, {"AUSDT": 0.5, "BUSDT": -0.5}, {"AUSDT": 10.0, "BUSDT": 20.0}, day, day, {"AUSDT": 0.001, "BUSDT": 0.003}, band=0.01)
    assert row["funding_paid"] == pytest.approx(0.5 * 1000 * 0.001 - 0.5 * 1000 * 0.003)
    assert row["pnl_since_last"] == pytest.approx(-row["funding_paid"])
    assert row["turnover"] == pytest.approx(0.0)
    row = paper.rebalance(state, {"AUSDT": 0.6, "BUSDT": -0.5}, {"AUSDT": 10.0, "BUSDT": 20.0}, day, day, band=0.01)
    assert row["turnover"] == pytest.approx(0.6 - 500 / 1001, abs=1e-3)
    assert state["positions"]["AUSDT"]["weight"] == pytest.approx(0.6, rel=1e-3)
