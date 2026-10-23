"""Walk-forward playbook selection: only outcomes known before a notice may influence its trade."""

import numpy as np
import pytest

from trader.services import playbooks
from trader.services.engine import liquidation_distance
from trader.services.events import EventType
from trader.services.playbooks import Outcomes, Playbook

DAY = 86_400_000
GRID = [Playbook(1, 0, 0.1, 0.0, 0.0, 60, 1.0), Playbook(-1, 0, 0.1, 0.0, 0.0, 60, 1.0)]


def _sample(i: int, ts: int) -> playbooks.Sample:
    z = np.zeros(4)
    return playbooks.Sample(EventType.BINANCE_SPOT_DELISTING, f"T{i}", f"T{i}USDT", ts, "title", (ts + np.arange(4) * 60_000).astype(np.int64), np.ones((4, 4)), z, 0)


def _outcomes(r: np.ndarray) -> Outcomes:
    return Outcomes(r, np.full(r.shape, 2, dtype=np.int64), np.zeros(len(r), dtype=np.int64))


def test_walk_forward_sees_only_finished_outcomes():
    ts = [i * 2 * DAY for i in range(12)] + [22 * DAY + 3_600_000]
    samples = [_sample(i, t) for i, t in enumerate(ts)]
    r = np.tile([0.05, -0.05], (len(ts), 1))
    decisions = playbooks.walk_forward(samples, _outcomes(r), GRID)
    assert [d.history for d in decisions] == [*range(12), 11]
    assert all(d.playbook is None for d in decisions[: playbooks.MIN_HISTORY])
    first = decisions[playbooks.MIN_HISTORY]
    assert first.playbook["side"] == 1 and first.pnl_on_1000 == 50.0
    assert first.entry_time == first.time and first.exit_time == playbooks._iso(ts[playbooks.MIN_HISTORY] + 3 * 60_000)


def test_no_trade_without_a_positive_bound():
    samples = [_sample(i, i * 2 * DAY) for i in range(15)]
    r = np.tile([-0.01, -0.02], (15, 1))
    assert all(d.playbook is None for d in playbooks.walk_forward(samples, _outcomes(r), GRID))
    assert playbooks.fit(samples, r, GRID)["binance_spot_delisting"]["playbook"] is None


def test_stricter_bound_trades_less():
    samples = [_sample(i, i * 2 * DAY) for i in range(30)]
    noisy = np.where(np.arange(30) % 3 == 0, -0.08, 0.06)[:, None] * np.array([1.0, -1.0])
    loose = playbooks.walk_forward(samples, _outcomes(noisy), GRID, z=0.5)
    strict = playbooks.walk_forward(samples, _outcomes(noisy), GRID, z=3.0)
    assert sum(d.ret is not None for d in strict) < sum(d.ret is not None for d in loose)


def _decision(symbol: str, entry: str, exit_: str, ret: float) -> playbooks.Decision:
    return playbooks.Decision("t", symbol[:-4], symbol, entry, "", 20, {}, 0.1, ret, ret * 1000, entry, exit_)


def test_grid_stops_always_fire_before_liquidation():
    assert playbooks.GRID and all(p.stop <= playbooks.STOP_BEFORE_LIQ * liquidation_distance(p.leverage, p.side) for p in playbooks.GRID)
    assert all(p.delay_min + p.hold_min <= 1380 for p in playbooks.GRID)


def test_account_replay_shares_one_balance():
    ds = [
        _decision("AAAUSDT", "2026-01-01T00:00:00", "2026-01-01T05:00:00", 0.5),
        _decision("BBBUSDT", "2026-01-01T01:00:00", "2026-01-01T02:00:00", 0.3),
        _decision("CCCUSDT", "2026-01-02T00:00:00", "2026-01-02T03:00:00", -0.2),
    ]
    run = playbooks.replay_account(ds, "all_in")
    assert [t["symbol"] for t in run.trades] == ["AAAUSDT", "CCCUSDT"] and run.skipped == 1
    assert run.summary["final_equity"] == 1200.0 and run.daily == {"2026-01-01": 1500.0, "2026-01-02": 1200.0}
    assert run.summary["tokens_ge_10pct_of_balance"] == ["AAAUSDT"] and run.summary["max_drawdown_pct"] == -20.0
    frac = playbooks.replay_account(ds, "fraction", fraction=0.5, notice_cap=1.0)
    assert [t["margin"] for t in frac.trades] == [500.0, 500.0, 700.0]
    assert frac.summary["final_equity"] == 1000 + 250 + 150 - 140


def test_one_announcement_shares_one_exposure_cap():
    t = "2026-01-01T00:00:00"
    ds = [_decision(s, t, "2026-01-01T05:00:00", 0.1) for s in ("AAAUSDT", "BBBUSDT", "CCCUSDT")]
    run = playbooks.replay_account(ds, "fraction", fraction=0.2, notice_cap=0.3)
    assert [t["margin"] for t in run.trades] == [200.0, 100.0] and run.skipped == 1


def test_concentration_and_clustered_bootstrap():
    from trader.services import report

    ds = [_decision("AAAUSDT", f"2026-01-{d:02d}T00:00:00", f"2026-01-{d:02d}T05:00:00", r) for d, r in [(1, 0.9), (2, 0.05), (3, -0.05), (4, 0.05)]]
    rows = {r["variant"]: r for r in report._concentration(ds)}
    assert rows["all OOS trades"]["oos_trades"] == 4 and rows["without the best 1 announcement(s)"]["oos_trades"] == 3
    assert rows["without the best 1 announcement(s)"]["tokens_ge_100_on_fresh_1000"] == 0
    boot = report._cluster_bootstrap(ds, n_boot=2000)["all"]
    assert boot["announcements"] == 4 and boot["mean_ret_on_margin"] == pytest.approx(0.2375)
    assert boot["ci90"][0] < boot["mean_ret_on_margin"] < boot["ci90"][1] and 0.0 <= boot["p_mean_le_0"] < 0.5
