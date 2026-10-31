import json
from datetime import UTC, datetime

import numpy as np
import pandas as pd

from trader.core.config import settings
from trader.quant import features, live, paper, why

HOUR = 3_600_000


def _hourly(seed: int, n: int = 900) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
    open_ = np.r_[close[0], close[:-1]]
    wick = np.abs(rng.normal(0, 0.004, n)) * close
    volume = rng.uniform(100, 1000, n)
    return pd.DataFrame({
        "open_time": 1_760_000_400_000 // HOUR * HOUR + np.arange(n, dtype=np.int64) * HOUR,
        "open": open_,
        "high": np.maximum(open_, close) + wick,
        "low": np.minimum(open_, close) - wick,
        "close": close,
        "volume": volume,
        "quote_volume": volume * close,
        "count": rng.integers(50, 500, n),
        "taker_buy_volume": volume * rng.uniform(0.3, 0.7, n),
        "funding": rng.normal(0, 1e-4, n),
    })


def test_every_model_feature_falls_into_a_named_factor_group():
    names = features.frame(_hourly(1), _hourly(2)).columns
    assert len(names) > 100
    assert [n for n in names if why.group(n) == "other"] == []


def test_explain_reads_rank_weight_and_history_of_the_last_decision(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(why, "factors", lambda symbol, at, spread: [{"group": "momentum", "value": 0.4, "top": []}])
    day, at = "2026-10-30", datetime(2026, 10, 30, 0, 15, tzinfo=UTC)
    paper.ledger_path().parent.mkdir(parents=True)
    paper.ledger_path().write_text(json.dumps({"history": [{"day": day, "rebalanced_at": at.isoformat()}]}))
    first, last = live._ms(datetime(2026, 10, 28, tzinfo=UTC)), live._ms(datetime(2026, 10, 29, tzinfo=UTC))
    why.root().mkdir(parents=True)
    pd.DataFrame({
        "decided": [first] * 3 + [last] * 3,
        "symbol": ["SOLUSDT", "ETHUSDT", "DOGEUSDT"] * 2,
        "blend": [0.1, 0.3, -0.2, 0.5, 0.2, -0.4],
        "rank": [2, 1, 3, 1, 2, 3],
        "of": [3] * 6,
        "edge": [0.0, 0.2, -0.1, 0.4, 0.1, -0.3],
        "xs": [0.1, 0.0, -0.1, 0.2, 0.3, -0.2],
        "weight": [0.0, 0.05, -0.02, 0.07, 0.03, -0.04],
    }).to_parquet(why.root() / f"{day}.parquet", index=False)
    got = why.explain("SOLUSDT", day)
    assert (got["rank"], got["of"], got["weight"]) == (1, 3, 0.07)
    assert (got["edge_pct"], got["xs_pct"]) == (round(2 / 3, 3), round(1 / 3, 3))
    assert [(h["rank"], h["weight"]) for h in got["history"]] == [(2, 0.0), (1, 0.07)]
    assert got["decided_at"] == "2026-10-29T23:00:00+00:00"
    assert got["factors"][0]["group"] == "momentum"
    assert why.explain("XRPUSDT", day)["rank"] is None
