import numpy as np
import pandas as pd

from trader.integrations import binance
from trader.quant import model, retrain
from trader.services import universe

HOUR = 3_600_000


def _month_frame(month: str) -> pd.DataFrame:
    start = int(pd.Timestamp(f"{month}-01", tz="UTC").timestamp() * 1000)
    t = start + HOUR * np.arange(24 * 3)
    close = 100 + np.arange(len(t), dtype=float)
    return pd.DataFrame({
        "open_time": t,
        "open": close,
        "high": close + 1,
        "low": close - 1,
        "close": close,
        "volume": 1.0,
        "close_time": t + HOUR - 1,
        "quote_volume": 1e6,
        "count": 10,
        "taker_buy_volume": 0.5,
        "taker_buy_quote_volume": 5e5,
        "ignore": 0,
    })


def test_updating_the_universe_appends_only_the_archive_months_after_what_is_stored(monkeypatch):
    fetched = []
    monkeypatch.setattr(binance, "archive_months", lambda symbol, interval: ["2026-08", "2026-09", "2026-10"])
    monkeypatch.setattr(binance, "archive_klines", lambda symbol, interval, month: fetched.append(month) or _month_frame(month))
    monkeypatch.setattr(binance, "archive_funding", lambda symbol, month: None)
    path = universe._root("1h") / "UPDTUSDT.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    stored = _month_frame("2026-08").assign(funding=0.0)[universe.COLUMNS]
    stored = pd.concat([stored, _month_frame("2026-09").assign(funding=0.0)[universe.COLUMNS]], ignore_index=True)
    stored.to_parquet(path, index=False)

    added = retrain.extend_symbol("UPDTUSDT")

    assert fetched == ["2026-10"]
    assert added == 72
    merged = pd.read_parquet(path)
    assert merged.open_time.is_monotonic_increasing and merged.open_time.is_unique
    assert len(merged) == 3 * 72
    assert retrain.extend_symbol("UPDTUSDT") == 0
    assert fetched == ["2026-10"]


def test_a_retrain_keeps_the_replaced_finals_as_the_models_of_the_quarter_they_served():
    folders = (model.root() / "models", model.root() / "xs_models")
    for folder in folders:
        folder.mkdir(parents=True, exist_ok=True)
    for name in ("long_final.txt", "short_final.txt"):
        (folders[0] / name).write_text(f"old {name}")
    (folders[1] / "xs_final.txt").write_text("old xs")
    cutoff = retrain.FIRST_CUTOFF

    kept = retrain.archive_finals(cutoff)

    assert sorted(kept) == sorted([f"long_{cutoff}.txt", f"short_{cutoff}.txt", f"xs_{cutoff}.txt"])
    assert (folders[0] / f"long_{cutoff}.txt").read_text() == "old long_final.txt"
    assert retrain.archive_finals(cutoff) == []
