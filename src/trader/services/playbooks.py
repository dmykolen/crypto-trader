"""Event playbooks — how to trade the minutes and hours after an exchange notice.

For every event type the app replays EVERY past notice of that type on 1m bars and scores a grid of playbooks
(entry delay x side x stop x take-profit x trailing stop x holding time x leverage) with the shared engine.

Selection is walk-forward and pre-registered: the playbook applied to an event is the one with the best
lower-confidence-bound of log-growth over the events whose 24h outcome was already known when the notice
appeared — nothing after it. If no candidate's bound is positive, the event is skipped. Every number this
module reports for past events is therefore out-of-sample. `fit()` runs the same rule on all history to pick
the playbooks live trading uses.

Returns are per unit of isolated margin: committing the whole $1000 balance as margin, R = 0.12 is +$120.
"""

import itertools
import json
import logging
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta

import numpy as np
from sqlmodel import Session, select

from trader.core.config import settings
from trader.models import NewsItem
from trader.services import market_data
from trader.services.engine import Costs, event_grid, liquidation_distance
from trader.services.events import EventType
from trader.services.news import item_events

log = logging.getLogger(__name__)

HORIZON = timedelta(hours=24)
MIN_HISTORY = 10
LCB_Z = 1.0
DEDUP = timedelta(days=3)


@dataclass(frozen=True)
class Playbook:
    side: int
    delay_min: int
    stop: float
    take_profit: float
    trail: float
    hold_min: int
    leverage: float

    def describe(self) -> str:
        parts = [f"{'LONG' if self.side > 0 else 'SHORT'} {self.leverage:g}x", f"enter +{self.delay_min}m", f"hold ≤{self.hold_min}m"]
        parts += [f"SL {self.stop:.0%}"] if self.stop else []
        parts += [f"TP {self.take_profit:.0%}"] if self.take_profit else []
        parts += [f"trail {self.trail:.0%}"] if self.trail else []
        return ", ".join(parts)


STOP_BEFORE_LIQ = 0.8


def _grid() -> list[Playbook]:
    """Every combination whose holding window fits in 24h and whose stop fires before the exchange liquidates."""
    combos = itertools.product((1, -1), (0, 5, 15, 30, 60), (0.05, 0.1, 0.2, 0.35), (0.0, 0.1, 0.2), (0.0, 0.1), (60, 240, 480, 1380), (1.0, 2.0, 3.0, 5.0))
    return [Playbook(*c) for c in combos if c[1] + c[5] <= 1380 and c[2] <= STOP_BEFORE_LIQ * liquidation_distance(c[6], c[0])]


GRID = _grid()


def _first_fill(open_time: np.ndarray, ts: int, latency_s: int) -> int:
    """First 1m bar whose open is at least `latency_s` after the announcement."""
    return int(np.searchsorted(open_time, ts + latency_s * 1000))


def _iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, UTC).isoformat(timespec="seconds")


@dataclass
class Sample:
    """One past event and the 1m bars from 1h before to 24h after it."""

    type: EventType
    token: str
    symbol: str
    ts: int
    title: str
    open_time: np.ndarray
    ohlc: np.ndarray
    funding: np.ndarray
    base: int

    @property
    def when(self) -> datetime:
        return datetime.fromtimestamp(self.ts / 1000, UTC)


def notice_events(session: Session, types: set[EventType] | None = None, since: datetime | None = None) -> list[tuple[EventType, str, int, str]]:
    """(type, token, ts_ms, title) for every stored notice, deduplicated, oldest first."""
    query = select(NewsItem).where(NewsItem.source.in_(["upbit", "binance"]))
    if since:
        query = query.where(NewsItem.published_at >= since)
    found: dict[tuple[EventType, str], list[int]] = {}
    out = []
    for item in sorted(session.exec(query).all(), key=lambda i: i.published_at):
        ts = int(item.published_at.timestamp() * 1000)
        for event in item_events(item):
            if types and event.type not in types:
                continue
            seen = found.setdefault((event.type, event.token), [])
            if seen and ts - seen[-1] < DEDUP.total_seconds() * 1000:
                continue
            seen.append(ts)
            out.append((event.type, event.token, ts, item.title))
    return out


def _load_sample(event: tuple[EventType, str, int, str], universe: set[str]) -> Sample | None:
    etype, token, ts, title = event
    symbol = market_data.perp_symbol(token, universe)
    if symbol is None:
        return None
    start = datetime.fromtimestamp(ts / 1000, UTC) - timedelta(hours=1)
    try:
        bars, funding = market_data.load_bars(symbol, "1m", start, start + timedelta(hours=1) + HORIZON + timedelta(minutes=2))
    except Exception as exc:
        log.warning("no bars for %s %s: %s", symbol, start, exc)
        return None
    open_time = bars.open_time.to_numpy()
    base = _first_fill(open_time, ts, settings.entry_latency_s)
    if len(open_time) == 0 or open_time[0] > ts - 30 * 60_000 or base >= len(open_time) - 60:
        return None
    ohlc = bars[["open", "high", "low", "close"]].to_numpy(np.float64).T.copy()
    return Sample(etype, token, symbol, ts, title, open_time, ohlc, funding, base)


def load_samples(session: Session, types: set[EventType] | None = None, workers: int = 12) -> list[Sample]:
    """Every past event with its reaction window (archive downloads run in parallel, cached on disk)."""
    events = notice_events(session, types)
    universe = market_data.perp_universe()
    with ThreadPoolExecutor(workers) as pool:
        samples = [s for s in pool.map(lambda e: _load_sample(e, universe), events) if s is not None]
    log.info("%d of %d events have a tradable perpetual window", len(samples), len(events))
    return sorted(samples, key=lambda s: s.ts)


@dataclass
class Outcomes:
    """Every playbook replayed on every event."""

    r: np.ndarray
    exits: np.ndarray
    bases: np.ndarray


def evaluate(samples: list[Sample], grid: list[Playbook] = GRID, costs: Costs | None = None, latency_s: int | None = None) -> Outcomes:
    """Replay the whole grid on every event. `latency_s` overrides the reaction time the samples were loaded with."""
    costs = costs or Costs.for_events()

    def col(field: str, dtype: type) -> np.ndarray:
        return np.array([getattr(p, field) for p in grid], dtype=dtype)

    cols = (
        col("delay_min", np.int64),
        col("side", np.int64),
        col("stop", np.float64),
        col("take_profit", np.float64),
        col("trail", np.float64),
        col("hold_min", np.int64),
        col("leverage", np.float64),
    )
    bases = np.array([s.base if latency_s is None else _first_fill(s.open_time, s.ts, latency_s) for s in samples], dtype=np.int64)

    def one(k: int) -> tuple[np.ndarray, np.ndarray]:
        o, h, lo, c = samples[k].ohlc
        return event_grid(o, h, lo, c, samples[k].funding, bases[k], *cols, costs.fee, costs.slip, costs.stop_slip, costs.mmr)

    with ThreadPoolExecutor() as pool:
        rows = list(pool.map(one, range(len(samples))))
    if not rows:
        return Outcomes(np.empty((0, len(grid))), np.empty((0, len(grid)), np.int64), bases)
    return Outcomes(np.vstack([r for r, _ in rows]), np.vstack([e for _, e in rows]), bases)


def _growth(r: np.ndarray) -> np.ndarray:
    """log(1 + R) per unit of margin; a trade that cannot run (NaN) counts as flat, a wipe-out as -4.6."""
    return np.log1p(np.clip(np.nan_to_num(r, nan=0.0), -0.99, None))


def _select(growth: np.ndarray, z: float = LCB_Z) -> tuple[int | None, float]:
    """Best playbook by the lower confidence bound of mean log-growth; None when no bound is positive."""
    n = len(growth)
    score = growth.mean(axis=0) - z * growth.std(axis=0, ddof=1) / np.sqrt(n)
    best = int(np.argmax(score))
    return (best if score[best] > 0 else None), float(score[best])


@dataclass
class Decision:
    """What the walk-forward did with one event."""

    type: str
    token: str
    symbol: str
    time: str
    title: str
    history: int
    playbook: dict | None
    score: float | None
    ret: float | None
    pnl_on_1000: float | None
    entry_time: str | None = None
    exit_time: str | None = None

    @property
    def notice(self) -> str:
        """One announcement can name several tokens; their trades are one bet (exposure cap, clustered stats)."""
        return f"{self.type}@{self.time}"


def _select_running(total: np.ndarray, total2: np.ndarray, n: int, z: float) -> tuple[int | None, float]:
    mean = total / n
    var = np.maximum(total2 - n * mean**2, 0.0) / (n - 1)
    score = mean - z * np.sqrt(var / n)
    best = int(np.argmax(score))
    return (best if score[best] > 0 else None), float(score[best])


def walk_forward(samples: list[Sample], out: Outcomes, grid: list[Playbook] = GRID, z: float = LCB_Z) -> list[Decision]:
    decisions = []
    horizon_ms = HORIZON.total_seconds() * 1000
    for etype in sorted({s.type for s in samples}):
        idx = [i for i, s in enumerate(samples) if s.type == etype]
        ts = np.array([samples[i].ts for i in idx])
        growth = _growth(out.r[idx])
        zero = np.zeros((1, growth.shape[1]))
        total, total2 = np.vstack([zero, np.cumsum(growth, axis=0)]), np.vstack([zero, np.cumsum(growth**2, axis=0)])
        for k, i in enumerate(idx):
            s = samples[i]
            known = int(np.searchsorted(ts, ts[k] - horizon_ms, side="right"))
            best, score = _select_running(total[known], total2[known], known, z) if known >= MIN_HISTORY else (None, None)
            ret = None if best is None or np.isnan(out.r[i, best]) else float(out.r[i, best])
            d = Decision(etype.value, s.token, s.symbol, _iso(s.ts), s.title, known, asdict(grid[best]) if best is not None else None, score, ret, None)
            if ret is not None and best is not None:
                d.pnl_on_1000 = round(1000 * ret, 2)
                d.entry_time = _iso(int(s.open_time[out.bases[i] + grid[best].delay_min]))
                d.exit_time = _iso(int(s.open_time[out.exits[i, best]] + s.open_time[1] - s.open_time[0]))
            decisions.append(d)
    return sorted(decisions, key=lambda d: d.time)


@dataclass
class AccountRun:
    """The out-of-sample trades replayed as ONE account: overlapping trades share the balance."""

    policy: str
    trades: list[dict]
    skipped: int
    daily: dict[str, float]
    summary: dict


def replay_account(
    decisions: list[Decision],
    policy: str = "all_in",
    capital: float = 1000.0,
    fraction: float = settings.margin_fraction,
    max_open: int = settings.max_open_positions,
    notice_cap: float = settings.max_notice_fraction,
) -> AccountRun:
    """Replay OOS trades in time order on one balance.

    * `all_in`: every trade commits all free cash as isolated margin — the criterion's "$1000 balance" taken
      literally; a signal arriving while the cash is tied up is skipped.
    * `fraction`: every trade commits `fraction` of equity, ≤ `max_open` positions, and all trades of ONE
      announcement together ≤ `notice_cap` of equity — the live trader's rules.
    PnL is realized at each trade's exit; a day's PnL is the sum of trades that exited during it.
    """
    trades = sorted((d for d in decisions if d.ret is not None and d.entry_time and d.exit_time), key=lambda d: d.entry_time or "")
    cash, open_, taken, skipped = capital, [], [], 0

    def settle(until: str) -> None:
        nonlocal cash
        for pos in sorted([p for p in open_ if p["exit_time"] <= until], key=lambda p: p["exit_time"]):
            open_.remove(pos)
            cash += pos["margin"] + pos["pnl"]

    for d in trades:
        settle(d.entry_time or "")
        equity = cash + sum(p["margin"] for p in open_)
        if equity < 1.0:
            skipped += 1
            continue
        busy = any(p["symbol"] == d.symbol for p in open_)
        notice_room = notice_cap * equity - sum(p["margin"] for p in open_ if p["notice"] == d.notice)
        margin = cash if policy == "all_in" else min(cash, fraction * equity, notice_room)
        if busy or margin < 0.01 * equity or (policy == "fraction" and len(open_) >= max_open):
            skipped += 1
            continue
        cash -= margin
        pos = {"symbol": d.symbol, "type": d.type, "notice": d.notice, "entry_time": d.entry_time, "exit_time": d.exit_time, "ret": d.ret, "margin": round(margin, 2)}
        pos |= {"pnl": round(margin * max(d.ret or 0.0, -1.0), 2), "equity_at_entry": round(equity, 2)}
        open_.append(pos)
        taken.append(pos)
    settle("9999")

    by_day: dict[str, float] = defaultdict(float)
    for t in taken:
        by_day[t["exit_time"][:10]] += t["pnl"]
    daily, equity, rows = {}, capital, []
    for day in sorted(by_day):
        rows.append((day, by_day[day], by_day[day] / equity if equity > 0 else 0.0))
        equity += by_day[day]
        daily[day] = round(equity, 2)
    curve = np.array([capital, *daily.values()])
    big = [t for t in taken if t["pnl"] >= 0.1 * t["equity_at_entry"]]
    summary = {
        "policy": policy,
        "final_equity": round(cash, 2),
        "return_pct": round((cash / capital - 1) * 100, 2),
        "max_drawdown_pct": round(float((curve / np.maximum.accumulate(curve) - 1).min()) * 100, 2),
        "trades_taken": len(taken),
        "signals_skipped": skipped,
        "win_rate": round(float(np.mean([t["pnl"] > 0 for t in taken])), 3) if taken else None,
        "trading_days": len(rows),
        "days_ge_10pct": sum(1 for _, _, g in rows if g >= 0.1),
        "days_le_minus_10pct": sum(1 for _, _, g in rows if g <= -0.1),
        "best_day_pct": round(max((g for *_, g in rows), default=0.0) * 100, 2),
        "worst_day_pct": round(min((g for *_, g in rows), default=0.0) * 100, 2),
        "trades_ge_10pct_of_balance": len(big),
        "tokens_ge_10pct_of_balance": sorted({t["symbol"] for t in big}),
    }
    return AccountRun(policy, taken, skipped, daily, summary)


def fit(samples: list[Sample], r: np.ndarray, grid: list[Playbook] = GRID) -> dict[str, dict]:
    """Live playbook per event type, selected on all history with the walk-forward rule."""
    out = {}
    for etype in sorted({s.type for s in samples}):
        idx = [i for i, s in enumerate(samples) if s.type == etype]
        if len(idx) < MIN_HISTORY:
            continue
        best, score = _select(_growth(r[idx]))
        if best is None:
            out[etype.value] = {"playbook": None, "events": len(idx), "score": score}
            continue
        col = np.nan_to_num(r[idx, best])
        out[etype.value] = {
            "playbook": asdict(grid[best]),
            "describe": grid[best].describe(),
            "events": len(idx),
            "score": round(score, 4),
            "mean_ret": round(float(col.mean()), 4),
            "median_ret": round(float(np.median(col)), 4),
            "win_rate": round(float((col > 0).mean()), 3),
            "worst_ret": round(float(col.min()), 4),
        }
    return out


def save_playbooks(fitted: dict[str, dict]) -> None:
    path = settings.data_dir / "playbooks.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"fitted_at": datetime.now(UTC).isoformat(timespec="seconds"), "latency_s": settings.entry_latency_s, "types": fitted}, indent=2))


def saved() -> dict:
    """The last `trader research events` fit (data/playbooks.json); {} before the first run."""
    path = settings.data_dir / "playbooks.json"
    return json.loads(path.read_text()) if path.exists() else {}


def live_playbooks() -> dict[EventType, Playbook]:
    """Playbooks the trader uses, by event type."""
    return {EventType(k): Playbook(**v["playbook"]) for k, v in saved().get("types", {}).items() if v.get("playbook")}
