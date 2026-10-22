"""Features and strategy signals are causal: the value at bar i never changes when later bars change."""

import numpy as np
import pandas as pd
import pytest

from trader.services import strategies
from trader.services.features import feature_frame


@pytest.fixture(scope="module")
def bars() -> pd.DataFrame:
    rng = np.random.default_rng(7)
    n = 1200
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
    open_ = np.r_[close[0], close[:-1]]
    spread = np.abs(rng.normal(0, 0.004, n)) * close
    volume = rng.uniform(100, 1000, n)
    return pd.DataFrame({
        "open_time": np.arange(n, dtype=np.int64) * 900_000,
        "open": open_,
        "high": np.maximum(open_, close) + spread,
        "low": np.minimum(open_, close) - spread,
        "close": close,
        "volume": volume,
        "quote_volume": volume * close,
        "count": rng.integers(50, 500, n),
        "taker_buy_volume": volume * rng.uniform(0.3, 0.7, n),
    })


@pytest.mark.parametrize("k", [300, 700, 1199])
def test_features_are_causal(bars, k):
    prefix = feature_frame(bars.iloc[: k + 1]).iloc[-1]
    pd.testing.assert_series_equal(prefix, feature_frame(bars).iloc[k], check_names=False, rtol=1e-9)


def test_strategy_targets_are_causal(bars):
    cut = 900
    future_rewritten = bars.copy()
    future_rewritten.loc[cut:, ["open", "high", "low", "close"]] *= 1.5
    for spec in {strategies.Spec(s.name, s.params, 1.0, 0.0, 0.0) for s in strategies.specs()}:
        original, rewritten = strategies.signal(spec, bars), strategies.signal(spec, future_rewritten)
        assert (original[: cut + 1] == rewritten[: cut + 1]).all(), spec
