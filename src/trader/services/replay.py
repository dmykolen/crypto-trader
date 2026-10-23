import heapq
import itertools
import logging
from collections.abc import Coroutine
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd
from sqlmodel import Session, delete, select

from trader.core.config import settings
from trader.core.db import engine
from trader.models import NewsItem, Trade
from trader.services import fast, market_data, playbooks, ticks, trading
from trader.services.broker import Fill
from trader.services.events import Notice, classify

log = logging.getLogger(__name__)

MODE = "replay"
FAST_SLIPPAGE = 0.005
FILL_MS = 500
SLOW_DETECTION = timedelta(seconds=15)
SCENARIOS: dict[str, dict[str, float] | None] = {
    "fast feed, 1 s (WebSocket key, server near Binance)": {"upbit": 1.0, "binance": 1.0},
    "as configured now (Upbit 1 s polling, Binance 5 s polling)": {"upbit": 1.5, "binance": 4.0},
    "slow path only (60 s entry)": None,
}


class Clock:
    def __init__(self, at: datetime) -> None:
        self.at = at

    def __call__(self) -> datetime:
        return self.at

    @property
    def ms(self) -> int:
        return int(self.at.timestamp() * 1000)


class Tape:
    def __init__(self) -> None:
        self.bar_t = np.empty(0, np.int64)
        self.bars = np.empty((0, 4), np.float64)
        self.tick_t = np.empty(0, np.int64)
        self.tick_p = np.empty(0, np.float64)
        self.spans: list[tuple[int, int]] = []

    def add_bars(self, df: pd.DataFrame) -> None:
        t = np.concatenate([self.bar_t, df.open_time.to_numpy(np.int64)])
        b = np.concatenate([self.bars, df[["open", "high", "low", "close"]].to_numpy(np.float64)])
        t, keep = np.unique(t, return_index=True)
        self.bar_t, self.bars = t, b[keep]

    def add_ticks(self, df: pd.DataFrame) -> None:
        df = ticks.clean(df)
        if df.empty:
            return
        t = np.concatenate([self.tick_t, df.transact_time.to_numpy(np.int64)])
        p = np.concatenate([self.tick_p, df.price.to_numpy(np.float64)])
        order = np.argsort(t, kind="stable")
        self.tick_t, self.tick_p = t[order], p[order]
        self.spans.append((int(df.transact_time.iat[0]), int(df.transact_time.iat[-1])))

    def has_ticks(self, ms: int) -> bool:
        return any(lo <= ms <= hi for lo, hi in self.spans)

    def traded(self, lo: int, hi: int) -> np.ndarray:
        if self.has_ticks(lo) or self.has_ticks(hi):
            a, b = int(np.searchsorted(self.tick_t, lo)), int(np.searchsorted(self.tick_t, hi, side="right"))
            return self.tick_p[a:b] if b > a else self.tick_p[max(a - 1, 0) : max(a, 1)]
        k = int(np.searchsorted(self.bar_t, hi, side="right")) - 1
        return self.bars[max(k, 0), [2, 1, 3]]

    def bar_open(self, ms: int) -> float | None:
        k = int(np.searchsorted(self.bar_t, ms))
        return float(self.bars[k, 0]) if k < len(self.bar_t) and self.bar_t[k] == ms else None


class ReplayBroker:
    mode = MODE

    def __init__(self, clock: Clock, tapes: dict[str, Tape]) -> None:
        self.clock, self.tapes = clock, tapes
        self.phase, self.step_ms = "close", 1000
        self.slip = settings.event_slippage
        self.sides: dict[str, int] = {}
        self.slips: dict[str, float] = {}
        self.last: dict[str, float] = {}

    async def price(self, symbol: str) -> float:
        seen = self.tapes[symbol].traded(self.clock.ms - self.step_ms, self.clock.ms)
        long = self.sides.get(symbol, 1) > 0
        px = {"adverse": seen.min() if long else seen.max(), "favorable": seen.max() if long else seen.min()}.get(self.phase, seen[-1])
        self.last[symbol] = float(px)
        return float(px)

    async def equity(self) -> float | None:
        return None

    def _base(self, symbol: str, order_side: int, entry: bool) -> float:
        tape, ms = self.tapes[symbol], self.clock.ms
        if tape.has_ticks(ms):
            window = tape.traded(ms, ms + FILL_MS)
            return float(window.max() if order_side > 0 else window.min())
        opened = tape.bar_open(ms) if entry else None
        return opened if opened is not None else self.last.get(symbol, float(tape.traded(ms - 60_000, ms)[-1]))

    async def open(self, symbol: str, side: int, qty: float, leverage: float) -> Fill:
        px = self._base(symbol, side, True) * (1 + side * self.slip)
        self.sides[symbol], self.slips[symbol] = side, self.slip
        return Fill(px, qty, qty * px * settings.taker_fee)

    async def protect(self, symbol: str, side: int, qty: float, stop: float) -> None:
        return None

    async def close(self, symbol: str, side: int, qty: float) -> Fill:
        px = self._base(symbol, -side, False) * (1 - side * self.slips.pop(symbol, self.slip))
        self.sides.pop(symbol, None)
        return Fill(px, qty, qty * px * settings.taker_fee)

    async def aclose(self) -> None:
        return None


@dataclass(order=True)
class Job:
    at: datetime
    seq: int
    kind: str = field(compare=False)
    payload: tuple = field(compare=False)


class ReplayTrader(trading.Trader):
    def __init__(self, broker: ReplayBroker, universe: set[str]) -> None:
        super().__init__(broker)
        self.replay_broker = broker
        self.jobs: list[Job] = []
        self.seq = itertools.count()
        self._tradable, self._tradable_at = universe, datetime.max.replace(tzinfo=UTC)

    def push(self, at: datetime, kind: str, *payload) -> None:
        heapq.heappush(self.jobs, Job(at, next(self.seq), kind, payload))

    def _spawn(self, coro: Coroutine) -> None:
        coro.close()

    def _schedule_entry(self, at: datetime, symbol: str, pb: playbooks.Playbook, trigger: str, news_id: str | None) -> None:
        tape = self.replay_broker.tapes.get(symbol)
        ms = int(at.timestamp() * 1000)
        if tape is not None and not tape.has_ticks(ms):
            at = datetime.fromtimestamp(-(-ms // 60_000) * 60, UTC)
        self.push(at, "enter", symbol, pb, trigger, news_id)


def _aware(at: datetime) -> datetime:
    return at.astimezone(UTC) if at.tzinfo else at.replace(tzinfo=UTC)


def notices_between(start: datetime, end: datetime) -> list[tuple[str, Notice]]:
    with Session(engine) as session:
        items = session.exec(select(NewsItem).where(NewsItem.source.in_(["upbit", "binance"])).where(NewsItem.published_at >= start).where(NewsItem.published_at < end)).all()
    return sorted(((i.id, Notice(i.source, i.id.split(":", 1)[1], i.title, _aware(i.published_at), i.url)) for i in items), key=lambda x: x[1].published_at)


def fitted_before(start: datetime) -> tuple[dict, dict]:
    cutoff = int((start - playbooks.HORIZON).timestamp() * 1000)
    with Session(engine) as session:
        samples = [s for s in playbooks.load_samples(session) if s.ts < cutoff]
    slow = playbooks.to_live(playbooks.fit(samples, playbooks.evaluate(samples).r))
    frame = pd.read_parquet(settings.reports_dir / "lab" / "tick_reactions_v2.parquet")
    frame = frame[frame.ts < int((start - timedelta(hours=1)).timestamp() * 1000)].reset_index(drop=True)
    return slow, fast.to_live(fast.fit_all(frame))


def tapes_for(notices: list[tuple[str, Notice]], universe: set[str], until: datetime) -> dict[str, Tape]:
    tapes: dict[str, Tape] = {}
    for _, notice in notices:
        for event in classify(notice):
            symbol = market_data.perp_symbol(event.token, universe)
            if symbol is None:
                continue
            tape = tapes.setdefault(symbol, Tape())
            lo, hi = notice.published_at - timedelta(hours=1), min(notice.published_at + timedelta(hours=26), until)
            try:
                tape.add_bars(market_data.load_klines(symbol, lo, hi))
                window = ticks.window(symbol, int(notice.published_at.timestamp() * 1000))
            except Exception as exc:
                log.warning("no prices for %s around %s: %s", symbol, notice.published_at, exc)
                continue
            if window is not None:
                tape.add_ticks(window)
    return {s: t for s, t in tapes.items() if len(t.bar_t)}


async def _monitor(trader: ReplayTrader, broker: ReplayBroker, step: timedelta) -> None:
    broker.step_ms = int(step.total_seconds() * 1000)
    for phase in ("adverse", "favorable", "close"):
        broker.phase = phase
        await trader.monitor()
    broker.phase = "close"


async def _finish(trader: ReplayTrader, broker: ReplayBroker) -> None:
    async with trader._lock:
        with Session(engine) as session:
            for t in trader._open_trades(session):
                await trader._close(t, await broker.price(t.symbol), "end of data")
                session.add(t)
            session.commit()


async def run(start: datetime, end: datetime, latency: dict[str, float] | None, slow: dict, quick: dict, universe: set[str], tapes: dict[str, Tape]) -> list[Trade]:
    notices = notices_between(start, end)
    until = min(end + timedelta(hours=26), datetime.now(UTC) - timedelta(minutes=2))
    with Session(engine) as session:
        session.exec(delete(Trade).where(Trade.mode == MODE))
        session.commit()
    clock = Clock(start)
    original = trading.now
    trading.now = clock
    try:
        broker = ReplayBroker(clock, tapes)
        trader = ReplayTrader(broker, set(tapes))
        trader.playbooks, trader.fast = slow, quick if latency else {}
        for news_id, notice in notices:
            if latency:
                trader.push(notice.published_at + timedelta(seconds=latency[notice.source]), "fast", notice)
            for event in classify(notice):
                trader.push(notice.published_at + SLOW_DETECTION, "event", event, news_id)
        while True:
            with Session(engine) as session:
                active = trader._open_trades(session)
            fine = any(tapes[t.symbol].has_ticks(clock.ms) for t in active)
            step = timedelta(seconds=1) if fine else timedelta(minutes=1)
            check = clock.at + step if active else None
            due = trader.jobs[0].at if trader.jobs else None
            nxt = min(x for x in (check, due, datetime.max.replace(tzinfo=UTC)) if x is not None)
            if nxt == datetime.max.replace(tzinfo=UTC):
                break
            if nxt > until:
                await _finish(trader, broker)
                break
            clock.at = nxt
            if due is not None and nxt == due:
                job = heapq.heappop(trader.jobs)
                if job.kind == "fast":
                    broker.slip = FAST_SLIPPAGE
                    await trader.on_fast_notice(job.payload[0], nxt.timestamp())
                elif job.kind == "event":
                    await trader.on_event(*job.payload)
                else:
                    broker.slip = settings.event_slippage
                    await trader._enter_at(nxt, *job.payload)
            else:
                await _monitor(trader, broker, step)
    finally:
        trading.now = original
    with Session(engine) as session:
        return list(session.exec(select(Trade).where(Trade.mode == MODE).order_by(Trade.entry_time)).all())


def _row(t: Trade) -> dict:
    return {
        "entry_time": _aware(t.entry_time).isoformat(timespec="milliseconds"),
        "symbol": t.symbol,
        "side": "LONG" if t.side > 0 else "SHORT",
        "leverage": t.leverage,
        "margin": round(t.margin, 2),
        "entry_price": t.entry_price,
        "exit_time": _aware(t.exit_time).isoformat(timespec="milliseconds") if t.exit_time else None,
        "exit_price": t.exit_price,
        "exit_reason": t.exit_reason,
        "fees": round(t.fees, 2),
        "pnl": round(t.pnl or 0.0, 2),
        "return_on_margin_pct": round(100 * (t.pnl or 0.0) / t.margin, 1) if t.margin else None,
        "trigger": t.trigger,
        "news_id": t.news_id,
    }


def summary(trades: list[Trade], start: datetime, days: int) -> dict:
    rows = [_row(t) for t in trades]
    pnl = np.array([r["pnl"] for r in rows]) if rows else np.zeros(0)
    curve = settings.paper_equity + np.concatenate([[0.0], np.cumsum(pnl)])
    peak = np.maximum.accumulate(curve)
    by_day = pd.Series(pnl, index=pd.to_datetime([r["entry_time"] for r in rows]).strftime("%Y-%m-%d")).groupby(level=0).sum() if rows else pd.Series(dtype=float)
    return {
        "start_equity": settings.paper_equity,
        "trades": len(rows),
        "winners": int((pnl > 0).sum()),
        "losers": int((pnl <= 0).sum()),
        "pnl": round(float(pnl.sum()), 2),
        "final_equity": round(float(curve[-1]), 2),
        "pnl_per_day": round(float(pnl.sum()) / days, 2),
        "max_drawdown_pct": round(float(((curve - peak) / peak).min() * 100), 1),
        "days_with_trades": len(by_day),
        "days_with_100_or_more": int((by_day >= 100).sum()),
        "by_day": {k: round(float(v), 2) for k, v in by_day.items()},
        "trades_log": rows,
    }


def decisions(notices: list[tuple[str, Notice]], slow: dict, quick: dict, universe: set[str]) -> list[dict]:
    out = []
    for news_id, notice in notices:
        events = classify(notice)
        out.append({
            "published": notice.published_at.isoformat(timespec="milliseconds"),
            "source": notice.source,
            "title": notice.title,
            "url": notice.url,
            "news_id": news_id,
            "events": [
                {
                    "type": e.type.value,
                    "token": e.token,
                    "perpetual": market_data.perp_symbol(e.token, universe),
                    "slow_playbook": slow[e.type].describe() if e.type in slow else None,
                    "fast_playbooks": {f"<= {lat:g}s": pb.describe() for lat, pb in quick.get(e.type, [])},
                }
                for e in events
            ],
        })
    return out


async def replay(start: datetime, days: int = 1) -> dict:
    end = start + timedelta(days=days)
    universe = market_data.perp_universe()
    slow, quick = fitted_before(start)
    notices = notices_between(start, end)
    tapes = tapes_for(notices, universe, min(end + timedelta(hours=26), datetime.now(UTC) - timedelta(minutes=2)))
    doc = {
        "period": {"start": start.isoformat(), "end": end.isoformat(), "days": days},
        "playbooks_fitted_on": f"events before {start.date()} only",
        "slow_playbooks": {k.value: v.describe() for k, v in slow.items()},
        "fast_playbooks": {k.value: {f"<= {lat:g}s": pb.describe() for lat, pb in v} for k, v in quick.items()},
        "notices": decisions(notices, slow, quick, universe),
        "scenarios": {},
    }
    for name, latency in SCENARIOS.items():
        doc["scenarios"][name] = {"latency_s": latency, **summary(await run(start, end, latency, slow, quick, universe, tapes), start, days)}
    return doc


def _when(iso: str | None) -> str:
    return (iso or "")[:23].replace("T", " ")


def _trade_line(r: dict) -> str:
    cells = [
        _when(r["entry_time"]),
        r["symbol"],
        r["side"],
        f"{r['leverage']:g}x",
        f"${r['margin']:,.0f}",
        f"{r['entry_price']:.6g}",
        _when(r["exit_time"]),
        f"{r['exit_price'] or 0:.6g}",
        r["exit_reason"] or "",
        f"${r['pnl']:+,.2f}",
    ]
    return "| " + " | ".join(cells) + " |"


def markdown(doc: dict) -> str:
    p = doc["period"]
    lines = [
        f"# Replay of the trader: {p['start'][:10]} → {p['end'][:10]} ({p['days']} day{'s' if p['days'] > 1 else ''})",
        "",
        f"Playbooks: {doc['playbooks_fitted_on']}. Start equity $1000.",
        "",
    ]
    lines += ["## What was published", "", "| published (UTC) | source | title | events | what the trader knows how to trade |", "|---|---|---|---|---|"]
    for n in doc["notices"]:
        ev = ", ".join(f"{e['type']} {e['token']}" for e in n["events"]) or "—"
        known = "; ".join(
            filter(
                None,
                [
                    ", ".join(
                        filter(
                            None,
                            [f"slow: {e['slow_playbook']}" if e["slow_playbook"] else None, f"fast: {len(e['fast_playbooks'])} latency buckets" if e["fast_playbooks"] else None],
                        )
                    )
                    for e in n["events"]
                ],
            )
        )
        lines.append(f"| {n['published'][:19].replace('T', ' ')} | {n['source']} | {n['title'][:70].replace('|', '/')} | {ev} | {known or 'nothing — skipped'} |")
    lines += ["", "## Result per scenario", "", "| scenario | trades | winners | P&L | final equity | max DD | days ≥ $100 |", "|---|---|---|---|---|---|---|"]
    for name, s in doc["scenarios"].items():
        lines.append(f"| {name} | {s['trades']} | {s['winners']} | ${s['pnl']:+,.2f} | ${s['final_equity']:,.2f} | {s['max_drawdown_pct']}% | {s['days_with_100_or_more']} |")
    for name, s in doc["scenarios"].items():
        if not s["trades_log"]:
            continue
        lines += [
            "",
            f"### Trades — {name}",
            "",
            "| entry (UTC) | symbol | side | lev | margin | entry | exit (UTC) | exit | reason | P&L |",
            "|---|---|---|---|---|---|---|---|---|---|",
        ]
        lines += [_trade_line(r) for r in s["trades_log"]]
    return "\n".join(lines) + "\n"
