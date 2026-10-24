import numpy as np
import pandas as pd
import pytest

from trader.quant import indicators as ind
from trader.quant import labels, patterns, sim
from trader.quant.day import from_csv
from trader.quant.labels import Geometry
from trader.quant.sim import Bars, Policy

HOUR = 3_600_000
T0 = 1_760_000_000_000 // HOUR * HOUR


def _bars(prices: np.ndarray, spread: float = 0.001) -> Bars:
    t = T0 + np.arange(len(prices), dtype=np.int64) * HOUR
    return Bars(t, prices.copy(), prices * (1 + spread), prices * (1 - spread), prices.copy(), np.full(len(prices), 1.0), np.zeros(len(prices)))


def _signal(bars: Bars, i: int, long: float, short: float) -> pd.DataFrame:
    return pd.DataFrame({"symbol": ["X"], "open_time": [int(bars.t[i])], "pred_long": [long], "pred_short": [short]})


def test_rsi_reads_100_when_price_only_rises_and_0_when_it_only_falls():
    rising = np.linspace(1.0, 2.0, 200)
    assert ind.rsi(rising, 14)[-1] == pytest.approx(100.0)
    assert ind.rsi(rising[::-1], 14)[-1] == pytest.approx(0.0)


def test_zigzag_confirms_a_top_only_once_price_has_fallen_by_the_threshold():
    h = np.array([1, 2, 3, 4, 5, 4.5, 4.0, 3.0, 2.0])
    price, index, kind = patterns.zigzag(h, h - 0.1, np.ones_like(h), 2.0, 3)
    confirmed = [t for t in range(len(h)) if not np.isnan(price[t, 0])]
    assert confirmed[0] == 7
    assert (price[7, 0], index[7, 0], kind[7, 0]) == (5.0, 4.0, 1.0)


def test_triple_barrier_assumes_the_stop_came_first_when_one_bar_spans_both_barriers():
    o = np.array([100.0, 100.0, 100.0, 100.0])
    h, low = np.array([100.0, 100.0, 110.0, 100.0]), np.array([100.0, 100.0, 90.0, 100.0])
    y_long, y_short = labels.triple_barrier(o, h, low, o.copy(), np.full(4, 2.0), 1.5, 3.0, 2, 0.0)
    assert (y_long[0], y_short[0]) == (-1.0, -1.0)


def test_triple_barrier_pays_reward_over_risk_minus_costs_on_a_take_profit():
    o = np.array([100.0, 100.0, 104.0, 107.0, 107.0])
    y_long, _ = labels.triple_barrier(o, o + 0.5, o - 0.5, o.copy(), np.full(5, 2.0), 1.5, 3.0, 3, 0.0016)
    assert y_long[0] == pytest.approx(2.0 - 0.0016 * 100 / 3.0)


def test_a_long_signal_in_a_rising_market_takes_profit_and_the_equity_books_it():
    bars = _bars(100 + np.arange(60) * 0.5)
    result = sim.simulate(_signal(bars, 10, 0.5, -0.5), {"X": bars}, Geometry(1.5, 3.0, 48), Policy(theta=0.1, fee=0.0, slip=0.0), int(bars.t[0]), int(bars.t[-1]) + HOUR)
    [trade] = result.trades.to_dict("records")
    assert trade["reason"] == "take_profit"
    assert trade["entry"] == pytest.approx(bars.o[11])
    assert trade["exit"] == pytest.approx(bars.o[11] + 3.0)
    assert trade["r"] == pytest.approx(2.0)
    assert result.equity.iloc[-1] == pytest.approx(1000.0 + trade["pnl"])


def test_a_position_never_loses_more_than_its_margin_even_through_a_price_gap():
    bars = _bars(np.r_[np.full(15, 100.0), np.full(10, 50.0)])
    result = sim.simulate(_signal(bars, 10, 0.5, -0.5), {"X": bars}, Geometry(1.5, 3.0, 48), Policy(theta=0.1), int(bars.t[0]), int(bars.t[-1]) + HOUR)
    [trade] = result.trades.to_dict("records")
    assert trade["reason"] == "liquidation"
    assert trade["pnl"] >= -trade["margin"] - trade["fees"] - 1e-9


def test_quotes_from_a_csv_in_15_minute_bars_become_hourly_bars(tmp_path):
    times = pd.date_range("2026-10-22 00:00", periods=12, freq="15min", tz="UTC")
    prices = np.arange(12, dtype=float) + 100
    path = tmp_path / "quotes.csv"
    pd.DataFrame({"timestamp": times.strftime("%Y-%m-%d %H:%M:%S"), "Open": prices, "High": prices + 1, "Low": prices - 1, "Close": prices + 0.5, "Volume": 1.0}).to_csv(
        path, index=False
    )
    bars = from_csv(path)
    assert len(bars) == 3
    first = bars.iloc[0]
    assert (first.open, first.high, first.low, first.close, first.volume) == (100.0, 104.0, 99.0, 103.5, 4.0)
    assert int(bars.open_time.iat[1]) - int(bars.open_time.iat[0]) == HOUR
