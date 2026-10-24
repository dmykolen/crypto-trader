"""Intel study mechanics on synthetic data: a planted signal is found on both periods, noise is not, the test
period never informs the sign, and statistics helpers behave."""

import math

import numpy as np
import pandas as pd
import pytest

from trader.core.config import settings
from trader.intel import study

HOUR = study.HOUR_MS
SYMBOLS = [f"S{i}USDT" for i in range(10)]


def synthetic_universe(monkeypatch, hours: int = 24 * 400, seed: int = 7):
    """Prices whose next-hour market-relative return follows a per-symbol 'oi_chg_1h' feature; everything else is noise."""
    monkeypatch.setattr(study, "TRAIN", ("2022-01-01", "2022-07-01"))
    monkeypatch.setattr(study, "TEST", ("2022-07-01", "2023-02-05"))
    rng = np.random.default_rng(seed)
    start = study._ms("2022-01-01")
    index = np.arange(start, start + hours * HOUR, HOUR, dtype="int64")
    signal = rng.normal(size=(hours, len(SYMBOLS)))
    noise = rng.normal(scale=0.01, size=(hours, len(SYMBOLS)))
    returns = np.vstack([np.zeros(len(SYMBOLS)), 0.004 * signal[:-1] + noise[1:]])
    root = settings.data_dir / "universe" / "1h"
    root.mkdir(parents=True, exist_ok=True)
    feats = {}
    for j, symbol in enumerate(SYMBOLS):
        close = 100 * np.exp(np.cumsum(returns[:, j]))
        pd.DataFrame({"open_time": index, "close": close, "funding": 0.0001}).to_parquet(root / f"{symbol}.parquet", index=False)
        frame = pd.DataFrame(index=pd.Index(index, name="open_time"))
        for col in ("news_mentions", "news_burst_z", "news_polarity", "mkt_mentions", "mkt_polarity", "mkt_burst_z", "wiki_z", "gdelt_z"):
            frame[col] = 0.0
        frame["news_mentions"] = (rng.random(hours) < 0.02).astype(float)
        frame["news_polarity"] = rng.choice([-0.5, 0.0, 0.5], size=hours) * frame["news_mentions"]
        frame["fear_greed"] = 50 + rng.normal(size=hours).cumsum() / 10
        frame["oi_chg_1h"] = signal[:, j]
        frame["oi_chg_24h"] = rng.normal(size=hours)
        for col in ("top_position_ratio", "top_account_ratio", "global_account_ratio", "taker_ratio"):
            frame[col] = 1 + rng.random(hours)
        for cat in study.EVENT_CATEGORIES:
            frame[f"news_cat_{cat}"] = 0
        frame["news_cat_listing"] = (frame["news_mentions"] > 0).astype(int)
        feats[symbol] = frame
    return lambda symbol, start_ms, end_ms: feats[symbol][(feats[symbol].index >= start_ms) & (feats[symbol].index < end_ms)]


def test_derive_has_no_look_ahead():
    index = pd.Index(np.arange(10, dtype="int64") * HOUR, name="open_time")
    prices = pd.DataFrame({"close": np.arange(1.0, 11.0), "funding": 0.0}, index=index)
    feats = pd.DataFrame(index=index, data={c: 0.0 for c in ("news_mentions", "news_burst_z", "news_polarity", "mkt_mentions", "mkt_polarity", "wiki_z", "gdelt_z", "fear_greed")})
    for col in ("oi_chg_1h", "oi_chg_24h", "top_position_ratio", "top_account_ratio", "global_account_ratio", "taker_ratio"):
        feats[col] = 1.0
    for cat in study.EVENT_CATEGORIES:
        feats[f"news_cat_{cat}"] = 0
    feats.loc[5 * HOUR, "news_mentions"] = 1.0
    out = study.derive(prices, feats)
    assert out.loc[4 * HOUR, "news_mentions_24h"] == 0 and out.loc[5 * HOUR, "news_mentions_24h"] == 1
    assert out.loc[3 * HOUR, "fwd_1"] == pytest.approx(math.log(5 / 4))
    assert math.isnan(out.loc[9 * HOUR, "fwd_1"])


def test_row_rank_corr_and_holm():
    x = pd.DataFrame([[1, 2, 3, 4], [1, 2, 3, 4], [1, np.nan, 3, 4]], dtype=float)
    y = pd.DataFrame([[10, 20, 30, 40], [40, 30, 20, 10], [1, 2, 3, 4]], dtype=float)
    corr = study._row_rank_corr(x, y, min_n=4)
    assert corr.iloc[0] == pytest.approx(1.0) and corr.iloc[1] == pytest.approx(-1.0) and math.isnan(corr.iloc[2])
    adjusted = study.holm({"a": 0.01, "b": 0.04, "c": 0.03, "d": math.nan})
    assert adjusted["a"] == pytest.approx(0.03) and adjusted["c"] == pytest.approx(0.06) and adjusted["b"] == pytest.approx(0.06)
    assert math.isnan(adjusted["d"])


def test_study_finds_the_planted_signal_and_rejects_noise(monkeypatch):
    feature_fn = synthetic_universe(monkeypatch)
    doc = study.run(SYMBOLS, feature_fn, write=True)
    ic = {(r["feature"], r["horizon_h"]): r for r in doc["ic"]}
    planted = ic[("oi_chg_1h", 1)]
    assert planted["sign"] == 1 and planted["ic_test_signed"] > 0.2 and planted["p_test_holm"] < 0.01
    assert doc["verdicts"]["oi_chg_24h"] in ("fails", "weak")
    assert doc["verdicts"]["news_burst_z"] in ("fails", "no-data", "weak")
    assert ic[("oi_chg_24h", 1)]["p_test_holm"] > 0.05
    events = {(r["event"], r["period"]): r for r in doc["events"]}
    assert events[("cat_listing", "train")]["n"] > 0
    assert study.report_path().exists() and study.report_path().with_suffix(".json").exists()
    assert "out-of-sample" in study.report_path().read_text()


def test_sign_is_chosen_on_train_only(monkeypatch):
    feature_fn = synthetic_universe(monkeypatch, seed=11)

    def flipped(symbol, start_ms, end_ms):
        frame = feature_fn(symbol, start_ms, end_ms).copy()
        test_start = study._ms(study.TEST[0])
        frame.loc[frame.index >= test_start, "oi_chg_1h"] *= -1
        return frame

    doc = study.run(SYMBOLS, flipped, write=False)
    row = next(r for r in doc["ic"] if r["feature"] == "oi_chg_1h" and r["horizon_h"] == 1)
    assert row["sign"] == 1
    assert row["ic_test_signed"] < -0.2
    assert doc["verdicts"]["oi_chg_1h"] == "fails"
