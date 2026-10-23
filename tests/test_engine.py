"""Engine execution rules, checked against hand-computed numbers."""

import numpy as np
import pandas as pd
import pytest

from trader.services.engine import Costs, backtest, event_grid, liquidation_distance

FREE = Costs(fee=0.0, slip=0.0, stop_slip=0.0, mmr=0.0)


def bars(rows: list[tuple[float, float, float, float]]) -> pd.DataFrame:
    o, h, lo, c = zip(*rows, strict=True)
    return pd.DataFrame({"open_time": np.arange(len(rows)) * 60_000, "open": o, "high": h, "low": lo, "close": c})


def run(rows, target, funding=None, **kw):
    df = bars(rows)
    kw.setdefault("costs", FREE)
    return backtest(df, np.zeros(len(df)) if funding is None else np.asarray(funding, float), np.asarray(target), **kw)


def test_long_fills_next_open_and_exits_on_signal():
    r = run([(100, 105, 99, 104), (104, 111, 103, 110), (110, 112, 109, 111)], [1, 1, 0], leverage=3)
    t = r.trades.iloc[0]
    assert (t.entry_bar, t.exit_bar, t.reason) == (0, 2, "signal")
    assert t.ret == pytest.approx(0.30)
    assert r.equity.iloc[-1] == pytest.approx(1300.0)


def test_fees_and_slippage_are_charged_on_notional():
    costs = Costs(fee=0.001, slip=0.001, stop_slip=0.001, mmr=0.0)
    r = run([(100, 100, 100, 100), (100, 100, 100, 100)], [1, 0], leverage=2, costs=costs)
    entry, exit_ = 100 * 1.001, 100 * 0.999
    expected = 2 * (exit_ / entry - 1) - 0.001 * 2 - 0.001 * 2 * exit_ / entry
    assert r.trades.ret.iloc[0] == pytest.approx(expected)


def test_stop_beats_take_profit_inside_one_bar():
    r = run([(100, 100, 100, 100), (100, 120, 80, 100)], [1, 1], leverage=1, sl=0.1, tp=0.1)
    t = r.trades.iloc[0]
    assert t.reason == "stop" and t.ret == pytest.approx(-0.10)


def test_gap_through_stop_fills_at_open():
    r = run([(100, 101, 99, 100), (85, 86, 84, 85)], [1, 1], leverage=1, sl=0.05)
    assert r.trades.ret.iloc[0] == pytest.approx(-0.15)


def test_short_liquidation_loses_the_whole_margin():
    r = run([(100, 101, 99, 100), (100, 115, 99, 112)], [-1, -1], leverage=10)
    t = r.trades.iloc[0]
    assert t.reason == "liquidation" and t.ret == pytest.approx(-1.0)
    assert r.equity.iloc[-1] == pytest.approx(0.0)


def test_maintenance_margin_liquidates_earlier():
    costs = Costs(fee=0.0, slip=0.0, stop_slip=0.0, mmr=0.02)
    survive = run([(100, 100, 100, 100), (100, 100, 82, 90), (90, 90, 90, 90)], [1, 1, 0], leverage=5, costs=costs)
    assert survive.trades.reason.iloc[0] == "signal"
    dead = run([(100, 100, 100, 100), (100, 100, 81.5, 90), (90, 90, 90, 90)], [1, 1, 0], leverage=5, costs=costs)
    assert dead.trades.reason.iloc[0] == "liquidation"


def test_funding_is_paid_by_longs_when_positive():
    r = run([(100, 100, 100, 100), (100, 100, 100, 100), (100, 100, 100, 100)], [1, 1, 0], funding=[0, 0.01, 0], leverage=2)
    assert r.trades.ret.iloc[0] == pytest.approx(-0.02)


def test_take_profit_and_trailing_stop():
    tp = run([(100, 101, 99, 100), (100, 112, 99, 111)], [1, 1], leverage=2, tp=0.1)
    assert tp.trades.reason.iloc[0] == "take_profit" and tp.trades.ret.iloc[0] == pytest.approx(0.2)
    gap = run([(100, 101, 99, 100), (130, 131, 129, 130)], [1, 1], leverage=2, tp=0.1)
    assert gap.trades.ret.iloc[0] == pytest.approx(0.2)
    tr = run([(100, 101, 99, 100), (100, 120, 100, 119), (119, 119, 110, 112)], [1, 1, 1], leverage=1, trail=0.05)
    assert tr.trades.reason.iloc[0] == "stop" and tr.trades.ret.iloc[0] == pytest.approx(0.14)


def test_no_reentry_until_signal_changes_after_stop():
    rows = [(100, 100, 100, 100), (100, 100, 90, 95), (95, 96, 94, 95), (95, 96, 94, 95)]
    r = run(rows, [1, 1, 1, 1], leverage=1, sl=0.05)
    assert len(r.trades) == 1


def test_reversal_flips_at_the_same_open():
    r = run([(100, 100, 100, 100), (110, 110, 110, 110), (100, 100, 100, 100)], [1, -1, -1], leverage=1)
    assert list(r.trades.reason) == ["reversal", "end"]
    assert r.trades.ret.iloc[0] == pytest.approx(0.10) and r.trades.ret.iloc[1] == pytest.approx(10 / 110)


def test_margin_fraction_scales_account_pnl():
    r = run([(100, 100, 100, 100), (110, 110, 110, 110)], [1, 0], leverage=2, margin_frac=0.25)
    assert r.equity.iloc[-1] == pytest.approx(1000 * (1 + 0.25 * 0.2))


def test_event_grid_matches_single_walk():
    df = bars([(100, 100, 100, 100), (100, 101, 95, 96), (96, 97, 90, 91), (91, 92, 88, 90)])
    o, h, lo, c = (df[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    out, exits = event_grid(
        o,
        h,
        lo,
        c,
        np.zeros(4),
        1,
        np.array([0, 1, 5]),
        np.array([-1, -1, -1]),
        np.array([0.2, 0.2, 0.2]),
        np.zeros(3),
        np.zeros(3),
        np.array([2, 2, 2]),
        np.array([2.0, 2.0, 2.0]),
        0.0,
        0.0,
        0.0,
        0.0,
    )
    assert out[0] == pytest.approx(-2 * (91 / 100 - 1))
    assert out[1] == pytest.approx(-2 * (90 / 96 - 1))
    assert list(exits) == [2, 3, -1] and np.isnan(out[2])


def test_liquidation_distance_matches_the_walker():
    costs = Costs(fee=0.0, slip=0.0, stop_slip=0.0, mmr=0.02)
    for lev, side in ((5.0, 1), (5.0, -1), (3.0, 1), (2.0, -1)):
        d = liquidation_distance(lev, side, mmr=0.02)
        px = 100 * (1 - side * d)
        just_safe = (100, max(100, px + side * 0.05), min(100, px + side * 0.05), 100)
        just_liq = (100, max(100, px - side * 0.05), min(100, px - side * 0.05), 100)
        assert run([(100,) * 4, just_safe, (100,) * 4], [side, side, 0], leverage=lev, costs=costs).metrics["liquidations"] == 0
        assert run([(100,) * 4, just_liq, (100,) * 4], [side, side, 0], leverage=lev, costs=costs).metrics["liquidations"] == 1
