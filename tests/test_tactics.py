import json

import numpy as np
import pandas as pd
import pytest

from trader.core.config import settings
from trader.quant import day, tactics
from trader.services.engine import Costs, backtest

HOUR = 3_600_000
T0 = 1_760_000_000_000 // (24 * HOUR) * 24 * HOUR


def _walk(n: int, seed: int = 5) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    c = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
    o = np.r_[c[0], c[:-1]]
    spread = np.abs(rng.normal(0, 0.004, n))
    return pd.DataFrame({
        "open_time": T0 + np.arange(n, dtype=np.int64) * HOUR,
        "open": o,
        "high": np.maximum(o, c) * (1 + spread),
        "low": np.minimum(o, c) * (1 - spread),
        "close": c,
        "volume": rng.uniform(1e3, 5e3, n),
        "quote_volume": rng.uniform(1e5, 5e5, n),
        "taker_buy_volume": rng.uniform(4e2, 2.5e3, n),
        "funding": np.where(np.arange(n) % 8 == 0, 1e-4, 0.0),
    })


def test_no_tactic_signal_changes_when_later_bars_are_added():
    bars = _walk(1400)
    full = tactics.signals(tactics.inputs(bars), tactics.catalog())
    cut = tactics.signals(tactics.inputs(bars.iloc[:1100].reset_index(drop=True)), tactics.catalog())
    moved = [k for k in full if not np.array_equal(full[k][:1100], cut[k])]
    assert len(full) == 61
    assert moved == []


def test_a_held_event_keeps_its_side_for_the_hold_and_an_opposite_event_flips_it():
    event = np.array([0, 1, 0, 0, 0, 0, -1, 0, 0, 0], dtype=float)
    assert tactics._hold(event, 3).tolist() == [0, 1, 1, 1, 0, 0, -1, -1, -1, 0]


def test_a_band_fades_the_extremes_and_exits_at_the_middle():
    x = np.array([0.5, -0.1, 0.2, 0.6, 1.2, 0.8, 0.4, np.nan, 0.5])
    assert tactics._band(x, 0.0, 1.0, 0.5).tolist() == [0, 1, 1, 0, -1, -1, 0, 0, 0]


def test_signals_decided_on_a_close_trade_from_the_next_open_and_start_flat_in_the_window():
    side = np.array([1, 1, -1, -1, 0])
    assert tactics.targets(side).tolist() == [0, 1, 1, -1, -1]
    assert tactics.targets(side, start=2).tolist() == [0, 0, 1, -1, -1]


def test_after_a_stop_the_cooldown_reopens_the_same_side_while_the_signal_holds():
    rows = [(100, 100, 100, 100), (100, 100, 89, 90), (90, 91, 90, 91), (91, 92, 91, 92), (92, 93, 92, 93), (93, 94, 93, 94)]
    df = pd.DataFrame({"open_time": np.arange(6) * HOUR, "open": [r[0] for r in rows], "high": [r[1] for r in rows], "low": [r[2] for r in rows], "close": [r[3] for r in rows]})
    free = Costs(fee=0.0, slip=0.0, stop_slip=0.0, mmr=0.0)
    waits = backtest(df, np.zeros(6), np.ones(6, dtype=int), leverage=1, sl=0.05, costs=free)
    reopens = backtest(df, np.zeros(6), np.ones(6, dtype=int), leverage=1, sl=0.05, cooldown=2, costs=free)
    assert waits.trades.reason.tolist() == ["stop"]
    assert reopens.trades.reason.tolist() == ["stop", "end"]
    assert int(reopens.trades.entry_bar.iat[1]) == 4


def test_the_pair_lab_runs_offline_on_your_own_csv(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    monkeypatch.setattr(settings, "reports_dir", tmp_path / "reports")
    bars = _walk(24 * 40)
    t = pd.to_datetime(bars.open_time, unit="ms", utc=True).dt.strftime("%Y-%m-%d %H:%M:%S")
    path = tmp_path / "quotes.csv"
    bars.assign(time=t)[["time", "open", "high", "low", "close", "volume"]].to_csv(path, index=False)
    doc = day.run("TESTUSDT", None, 2, path, leverage=3)
    assert doc["days"] == 2 and doc["bars_in_window"] == 48
    assert doc["leverage"] == 3
    assert doc["summary"]["tactics"] == len(tactics.catalog()) == len(doc["tactics"])
    assert doc["summary"]["positive"] + doc["summary"]["negative"] + doc["summary"]["flat"] == doc["summary"]["tactics"]
    pnl = [r["pnl"] for r in doc["tactics"]]
    assert pnl == sorted(pnl, reverse=True)
    for d in doc["detail"]:
        for trade in d["trades"]:
            assert trade["entry_time"] >= int(bars.open_time.iat[-48])
        assert sum(t["pnl"] for t in d["trades"]) == pytest.approx(d["pnl"], abs=0.02 * max(1, len(d["trades"])))
        assert d["about"] and d["title"] in d["label"]
        for trade in d["trades"]:
            t = tactics.by_key(d["key"])
            assert (trade["stop"] is None) == (t.overlay.sl == 0) and (trade["take"] is None) == (t.overlay.tp == 0)
            if trade["stop"] is not None:
                assert (trade["stop"] < trade["entry"]) == (trade["side"] == "LONG")
    roles = [d["role"] for d in doc["detail"]]
    assert roles[0] == "best" and doc["detail"][0]["key"] == doc["tactics"][0]["key"]
    assert doc["detail"][roles.index("worst")]["key"] == doc["tactics"][-1]["key"]
    top = [d for d in doc["detail"] if d["role"] in ("best", "second", "third")]
    assert len({tactics.by_key(d["key"]).rule for d in top}) == len(top)
    assert doc["bot"] is None
    assert doc["book"] == [] and doc["book_known"] is False
    assert doc["candles"][-1]["time"] == int(bars.open_time.iat[-1]) // 1000


def test_every_tactic_reads_in_plain_words_with_its_exits():
    catalog = tactics.catalog()
    assert len({t.title for t in catalog}) == len({t.signal for t in catalog})
    text = tactics.by_key("three_soldiers(hold=12)|sl1.5_tp3_reopen").explain(0.008)
    assert "12 год" in text and "1,5 ATR (≈ 1,2 % ціни)" in text and "3 ATR (≈ 2,4 % ціни)" in text and "через 6 год" in text
    assert all("{" not in t.explain(0.01) and "=" not in t.title for t in catalog)


def test_the_pair_lab_reports_the_paper_bot_day_from_the_ledger(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    path = day.paper.ledger_path()
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"history": [{"day": "2026-10-29", "equity": 972.04}, {"day": "2026-10-30", "equity": 993.51}]}))
    lo = int(pd.Timestamp("2026-10-29", tz="UTC").timestamp() * 1000)
    assert day._bot(lo, lo + 24 * HOUR) == {"source": "paper", "pnl": 21.47, "return_pct": 2.21}
    assert day._bot(lo, lo + 48 * HOUR) is None


def test_the_pair_lab_reads_the_paper_book_and_says_when_it_has_no_book_for_a_day(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    path = day.paper.ledger_path()
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"history": [{"day": "2026-10-29", "equity": 972.04}, {"day": "2026-11-01", "equity": 980.0, "book": {"SOLUSDT": 0.0684, "BTCUSDT": 0.29}}]}))
    nov = int(pd.Timestamp("2026-11-01", tz="UTC").timestamp() * 1000)
    assert day._book("SOLUSDT", nov, nov + 24 * HOUR) == ([{"day": "2026-11-01", "weight": 0.0684}], True)
    assert day._book("ETHUSDT", nov, nov + 24 * HOUR) == ([], True)
    assert day._book("SOLUSDT", nov - 3 * 24 * HOUR, nov - 2 * 24 * HOUR) == ([], False)


def test_uploaded_quotes_are_checked_before_a_job_can_use_them(client):
    good = "time,open,high,low,close\n2026-10-01 00:00,1,2,0.5,1.5\n2026-10-01 01:00,1.5,2,1,1.8\n"
    r = client.post("/api/v1/uploads", content=good, headers={"Content-Type": "text/csv"})
    assert r.status_code == 201 and r.json()["bars"] == 2
    bad = client.post("/api/v1/uploads", content="a,b\n1,2\n", headers={"Content-Type": "text/csv"})
    assert bad.status_code == 422
    assert client.post("/api/v1/jobs", json={"kind": "quant_day", "params": {"symbol": "SOL/USDT"}}).status_code == 422
