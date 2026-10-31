import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from trader.core.config import settings
from trader.quant import neutral, paper, trend
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
    assert row["trades"] == pytest.approx({"AUSDT": -0.05, "BUSDT": 0.55, "CUSDT": -0.5})
    assert row["book"] == pytest.approx({s: v["weight"] for s, v in state["positions"].items()}, abs=1e-6)
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


def test_a_short_caught_in_a_sixfold_pump_loses_the_whole_move(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    closes = {"PUMPUSDT": [10, 10, 60, 60, 60], "FLATUSDT": [10] * 5}
    rows = [{"day": i * DAY, "symbol": s, "open": c, "high": c, "low": c, "close": c, "qv": 1e8, "funding": 0.0} for s, cs in closes.items() for i, c in enumerate(cs)]
    (tmp_path / "quant").mkdir()
    pd.DataFrame(rows).to_parquet(tmp_path / "quant" / "daily.parquet", index=False)
    p = trend.load_panel()
    ret = neutral.weights_returns(p, pd.DataFrame({"PUMPUSDT": -0.04, "FLATUSDT": 0.04}, index=p.c.index))
    assert ret.loc[2 * DAY] == pytest.approx(-0.04 * 5)


def test_the_backtest_trades_from_drifted_weights_and_skips_drifts_inside_the_band():
    days = pd.RangeIndex(0, 4 * DAY, DAY)
    p = _panel(pd.DataFrame({"AUSDT": [10.0, 10, 20, 20], "BUSDT": [10.0] * 4}, index=days))
    w = pd.DataFrame({"AUSDT": 0.5, "BUSDT": -0.5}, index=days)
    ret, book = neutral.drift(p, w, band=0.01)
    a = 0.5 / (1 - COST)
    grown = 1 + a
    assert ret.loc[DAY] == pytest.approx(-COST)
    assert book.loc[DAY, "AUSDT"] == pytest.approx(a)
    assert ret.loc[2 * DAY] == pytest.approx(a)
    assert ret.loc[3 * DAY] == pytest.approx(-COST * (2 * a / grown - 0.5 + 0.5 - a / grown))
    wide, held = neutral.drift(p, w, band=0.5)
    assert wide.loc[3 * DAY] == pytest.approx(0.0)
    assert held.loc[2 * DAY, "AUSDT"] == pytest.approx(2 * a / grown)


def test_the_pump_guard_keeps_a_token_that_rose_past_the_limit_out_of_the_shorts_only():
    days = pd.RangeIndex(0, 20 * DAY, DAY)
    rise = [10.0] * 10 + [16.0] * 10
    close = pd.DataFrame({"PUMPUSDT": rise, "CALMUSDT": [10.0] * 20, "HOTUSDT": rise}, index=days)
    score = pd.DataFrame({"PUMPUSDT": 0.1, "CALMUSDT": 0.5, "HOTUSDT": 0.9}, index=days)
    out = neutral.pump_guard(_panel(close), score, 7, 0.5)
    assert out.loc[12 * DAY].isna().tolist() == [True, False, False]
    assert out.loc[18 * DAY].notna().all()


def test_a_disk_full_during_the_ledger_write_leaves_the_previous_ledger_intact(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    path = paper.ledger_path()
    path.parent.mkdir(parents=True)
    state = {"start_equity": 1000.0, "equity": 1000.0, "positions": {}, "history": []}
    path.write_text(json.dumps(state))
    monkeypatch.setattr(paper, "target_book", lambda now: ({"AUSDT": 0.5}, {"AUSDT": 10.0}, {}))
    monkeypatch.setattr(paper, "marks", lambda symbols: {})
    write = Path.write_text

    def full(self, text, *args, **kwargs):
        if self.suffix == ".tmp":
            write(self, text[:10], *args, **kwargs)
            raise OSError(28, "No space left on device")
        return write(self, text, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", full)
    now = datetime(2026, 10, 29, 0, 15, tzinfo=UTC)
    with pytest.raises(OSError):
        paper.step(now=now)
    assert json.loads(path.read_text()) == state
    monkeypatch.setattr(Path, "write_text", write)
    assert paper.step(now=now)["trades"] == {"AUSDT": 0.5}
    assert len(json.loads(path.read_text())["history"]) == 1
