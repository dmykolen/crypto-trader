"""The trading loop — watch the news, act on learned playbooks, manage positions, respect the risk rails.

Exchange notices take the hot path, with no LLM in it: the boards are polled every POLL_SECONDS, a new notice is
classified by rules (`services/events.py`) and every event with a learned playbook (`data/playbooks.json`, written
by `trader research events`) is scheduled to enter at  published_at + ENTRY_LATENCY_S + playbook delay  — exactly
the timing the playbook was backtested with. A notice first seen more than MAX_NOTICE_AGE_S after publication is
recorded but never traded.

Media news (RSS) goes to Claude for a structured price-impact assessment stored on the item. With
LLM_NEWS_TRADING=true an actionable assessment opens a small, short-dated position — opt-in, because no backtest
supports those trades.

Open positions are checked every MONITOR_SECONDS: liquidation (paper), stop, take-profit, time exit, then the
trailing stop ratchets. Risk rails: MAX_OPEN_POSITIONS, one position per symbol, isolated margin = MARGIN_FRACTION
of equity, leverage ≤ MAX_LEVERAGE, no new positions once the UTC day's realized loss reaches MAX_DAILY_LOSS.
"""

import asyncio
import json
import logging
import re
import time
from collections.abc import Awaitable, Callable
from contextlib import suppress
from datetime import UTC, datetime, timedelta

import httpx
from sqlmodel import Session, select

from trader.ai import news_analyst
from trader.core.config import settings
from trader.core.db import engine
from trader.core.metrics import news_events_total, notice_latency_seconds, open_positions, orders_total, trades_closed_total
from trader.integrations import binance, binance_ws, upbit
from trader.integrations.llm import LLM
from trader.models import NewsItem, Trade
from trader.services import fast, market_data, news, playbooks
from trader.services.broker import Broker, LiveBroker, PaperBroker
from trader.services.events import Event, Notice, binance_notice, classify, upbit_notice

log = logging.getLogger(__name__)
MEDIA_MAX_AGE = timedelta(hours=6)
LLM_TRIAGE_PER_POLL = 20


def now() -> datetime:
    return datetime.now(UTC)


def liquidation_price(t: Trade, mmr: float = settings.maintenance_margin) -> float:
    """Isolated-margin liquidation price (same formula as the engine, funding ignored)."""
    return t.entry_price * (t.leverage - t.side) / (t.leverage * (1 - t.side * mmr))


def exit_reason(t: Trade, price: float, at: datetime, *, paper: bool) -> str | None:
    """Why the position must be closed at `price` now, or None — same priority as the backtest engine."""
    long = t.side > 0
    liq = liquidation_price(t)
    if paper and (price <= liq if long else price >= liq):
        return "liquidation"
    if t.stop_price is not None and (price <= t.stop_price if long else price >= t.stop_price):
        return "stop"
    if t.take_profit_price is not None and (price >= t.take_profit_price if long else price <= t.take_profit_price):
        return "take_profit"
    if at >= t.exit_due:
        return "time"
    return None


def update_trail(t: Trade, price: float) -> None:
    """Ratchet the best price seen and, for trailing trades, the stop."""
    t.best_price = max(t.best_price, price) if t.side > 0 else min(t.best_price, price)
    if t.trail:
        trail_stop = t.best_price * (1 - t.side * t.trail)
        if t.stop_price is None:
            t.stop_price = trail_stop
        else:
            t.stop_price = max(t.stop_price, trail_stop) if t.side > 0 else min(t.stop_price, trail_stop)


def decisions_path():
    return settings.data_dir / "run" / "notice_decisions.jsonl"


def record(news_id: str | None, kind: str, token: str, outcome: str, detail: str = "") -> None:
    path = decisions_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps({"at": now().isoformat(timespec="seconds"), "news_id": news_id, "event": kind, "token": token, "outcome": outcome, "detail": detail}) + "\n")


class Trader:
    def __init__(self, broker: Broker, llm: LLM | None = None, *, rest: binance.FuturesREST | None = None) -> None:
        self.broker = broker
        self.mode = broker.mode
        self.llm = llm
        self.playbooks = playbooks.live_playbooks()
        self.fast = fast.live() if settings.fast_trading else {}
        self._rest = rest or binance.FuturesREST()
        self._tradable: set[str] = set()
        self._tradable_at = datetime.min.replace(tzinfo=UTC)
        self._lock = asyncio.Lock()
        self._tasks: set[asyncio.Task] = set()
        self._seen: dict[str, float] = {}

    async def run(self, stop: asyncio.Event) -> None:
        log.info("trader started: mode=%s llm=%s playbooks=%s", self.mode, self.llm is not None, {k.value: v.describe() for k, v in self.playbooks.items()})
        log.info("fast playbooks: %s", {k.value: [f"<={lat:g}s {pb.describe()}" for lat, pb in v] for k, v in self.fast.items()})
        monitor_every = min(settings.monitor_seconds, settings.fast_monitor_seconds) if self.fast else settings.monitor_seconds
        async with httpx.AsyncClient(timeout=20) as client:
            loops = [
                self._every(stop, settings.poll_seconds, self.poll_notices, client),
                self._every(stop, settings.rss_poll_seconds, self.poll_media, client),
                self._every(stop, monitor_every, self.monitor),
            ]
            if self.fast:
                await self.tradable()
                loops.append(self.stream_binance(stop))
                if settings.fast_upbit_poll_s > 0:
                    loops.append(self._every(stop, settings.fast_upbit_poll_s, self.poll_upbit_fast, client))
                if settings.binance_api_key is None and settings.fast_binance_poll_s > 0:
                    loops.append(self._every(stop, settings.fast_binance_poll_s, self.poll_binance_fast, client))
            await asyncio.gather(*loops)
        for task in self._tasks:
            task.cancel()

    def _spawn(self, coro: Awaitable) -> asyncio.Task:
        task = asyncio.ensure_future(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    async def stream_binance(self, stop: asyncio.Event) -> None:
        if settings.binance_api_key is None or settings.binance_api_secret is None:
            log.warning("BINANCE_API_KEY/BINANCE_API_SECRET not set: the Binance announcement stream (fast path) is off")
            return
        stream = binance_ws.announcements(settings.binance_api_key.get_secret_value(), settings.binance_api_secret.get_secret_value())
        async for notice, received, _ in stream:
            if stop.is_set():
                return
            await self.on_fast_notice(notice, received)

    async def poll_upbit_fast(self, client: httpx.AsyncClient) -> None:
        batch, _ = await upbit.notices(client, 1, per_page=5)
        received = time.time()
        for raw in batch:
            await self.on_fast_notice(upbit_notice(raw), received)

    async def poll_binance_fast(self, client: httpx.AsyncClient) -> None:
        for catalog in binance.CATALOGS:
            batch = await binance.announcements(client, catalog, 1, 5)
            received = time.time()
            for raw in batch:
                await self.on_fast_notice(binance_notice(raw), received)

    @staticmethod
    def _title_key(title: str) -> str:
        return re.sub(r"\W+", " ", title.lower()).strip()

    async def on_fast_notice(self, notice: Notice, received: float) -> list[Trade]:
        key = self._title_key(notice.title)
        if key in self._seen:
            return []
        self._seen[key] = received
        latency = received - notice.published_at.timestamp()
        notice_latency_seconds.labels(notice.source).observe(max(latency, 0.0))
        with Session(engine) as session:
            stored = news.store_new(session, [news.to_item(notice)])
        news_id = stored[0].id if stored else f"{notice.source}:{notice.source_id}"
        trades = []
        for event in classify(notice):
            pb = fast.for_latency(self.fast.get(event.type, []), latency)
            log.info("fast %s %s seen %.2fs after publication: %s", event.type.value, event.token, latency, notice.title)
            if pb is None or latency > settings.fast_max_latency_s:
                record(news_id, event.type.value, event.token, "no_rule" if pb is None else "too_slow", f"{latency:.2f}")
                continue
            symbol = market_data.perp_symbol(event.token, await self.tradable())
            if symbol is None:
                record(news_id, event.type.value, event.token, "no_perp")
                continue
            trade = await self.open_position(
                symbol,
                pb.side,
                pb.leverage,
                stop=pb.stop,
                take_profit=pb.take_profit,
                trail=0.0,
                hold=timedelta(seconds=pb.hold_s),
                trigger=f"fast {event.type.value}: {pb.describe()} ({latency:.2f}s)",
                news_id=news_id,
            )
            if trade is not None:
                trades.append(trade)
                self._spawn(self._exit_at(trade.id, trade.exit_due))
        return trades

    async def _exit_at(self, trade_id: int | None, due: datetime) -> None:
        await asyncio.sleep(max(0.0, (due - now()).total_seconds()))
        async with self._lock:
            with Session(engine) as session:
                t = session.get(Trade, trade_id)
                if t is None or t.status != "open":
                    return
                await self._close(t, await self.broker.price(t.symbol), "time")
                session.add(t)
                session.commit()

    @staticmethod
    async def _every(stop: asyncio.Event, seconds: float, fn: Callable[..., Awaitable[None]], *args) -> None:
        while not stop.is_set():
            try:
                await fn(*args)
            except Exception:
                log.exception("%s failed", fn.__name__)
            with suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), seconds)

    async def tradable(self) -> set[str]:
        """Perpetuals trading right now (refreshed hourly)."""
        if now() - self._tradable_at > timedelta(hours=1):
            info = await asyncio.to_thread(self._rest.exchange_info)
            self._tradable = {s["symbol"] for s in info["symbols"] if s.get("status") == "TRADING" and s.get("contractType") == "PERPETUAL"}
            self._tradable_at = now()
        return self._tradable

    async def poll_notices(self, client: httpx.AsyncClient) -> None:
        items = await news.fetch_exchange_notices(client)
        with Session(engine) as session:
            events = [(event, item.id) for item in news.store_new(session, items) for event in news.item_events(item)]
        for event, news_id in events:
            news_events_total.labels(event.type.value).inc()
            await self.on_event(event, news_id)

    async def on_event(self, event: Event, news_id: str | None = None) -> asyncio.Task | None:
        """Schedule the playbook entry for a fresh event; returns the scheduled task (None when not traded)."""
        playbook = self.playbooks.get(event.type)
        age = (now() - event.notice.published_at).total_seconds()
        log.info("event %s %s, %.0fs old: %s", event.type.value, event.token, age, event.notice.title)
        if playbook is None or age > settings.max_notice_age_s:
            record(news_id, event.type.value, event.token, "no_rule" if playbook is None else "too_old", f"{age:.0f}")
            return None
        symbol = market_data.perp_symbol(event.token, await self.tradable())
        if symbol is None:
            log.info("no tradable perpetual for %s", event.token)
            record(news_id, event.type.value, event.token, "no_perp")
            return None
        enter_at = event.notice.published_at + timedelta(seconds=settings.entry_latency_s, minutes=playbook.delay_min)
        record(news_id, event.type.value, event.token, "scheduled", enter_at.isoformat(timespec="seconds"))
        return self._schedule_entry(enter_at, symbol, playbook, f"{event.type.value}: {playbook.describe()}", news_id)

    def _schedule_entry(self, at: datetime, symbol: str, pb: playbooks.Playbook, trigger: str, news_id: str | None) -> asyncio.Task | None:
        task = asyncio.create_task(self._enter_at(at, symbol, pb, trigger, news_id))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    async def _enter_at(self, at: datetime, symbol: str, pb: playbooks.Playbook, trigger: str, news_id: str | None) -> None:
        await asyncio.sleep(max(0.0, (at - now()).total_seconds()))
        try:
            await self.open_position(
                symbol, pb.side, pb.leverage, stop=pb.stop, take_profit=pb.take_profit, trail=pb.trail, hold=timedelta(minutes=pb.hold_min), trigger=trigger, news_id=news_id
            )
        except Exception:
            log.exception("could not open %s (%s)", symbol, trigger)

    async def poll_media(self, client: httpx.AsyncClient) -> None:
        items = await news.fetch_media(client)
        with Session(engine) as session:
            fresh = news.store_new(session, items)
            if self.llm is None:
                return
            recent = sorted((i for i in fresh if now() - i.published_at <= MEDIA_MAX_AGE), key=lambda i: i.published_at, reverse=True)
            for item in recent[:LLM_TRIAGE_PER_POLL]:
                try:
                    impact = await news_analyst.assess(self.llm, item.title, item.summary, item.source, item.published_at.isoformat())
                except Exception as exc:
                    log.warning("LLM triage of %s failed: %s", item.id, exc)
                    continue
                item.analysis = impact.model_dump()
                session.add(item)
                session.commit()
                for hit in news_analyst.actionable(impact):
                    log.warning(
                        "ACTIONABLE NEWS %s %s ~%.1f%% in %dm (confidence %.2f): %s",
                        hit.ticker,
                        hit.direction,
                        hit.expected_move_pct,
                        hit.horizon_minutes,
                        hit.confidence,
                        item.title,
                    )
                    if settings.llm_news_trading:
                        await self._llm_trade(hit, item)

    async def _llm_trade(self, hit: news_analyst.TokenImpact, item: NewsItem) -> None:
        symbol = market_data.perp_symbol(hit.ticker.upper(), await self.tradable())
        if symbol is None:
            return
        move = hit.expected_move_pct / 100
        await self.open_position(
            symbol,
            1 if hit.direction == "bullish" else -1,
            2.0,
            stop=min(max(move / 2, 0.02), 0.1),
            take_profit=move,
            trail=0.0,
            hold=timedelta(minutes=min(max(hit.horizon_minutes, 30), 1440)),
            trigger=f"llm:{(item.analysis or {}).get('category')}",
            news_id=item.id,
        )

    def _open_trades(self, session: Session) -> list[Trade]:
        return list(session.exec(select(Trade).where(Trade.mode == self.mode, Trade.status == "open")).all())

    async def equity(self, session: Session) -> float:
        live = await self.broker.equity()
        if live is not None:
            return live
        realized = session.exec(select(Trade.pnl).where(Trade.mode == self.mode, Trade.status == "closed")).all()
        return settings.paper_equity + sum(p or 0.0 for p in realized)

    def _realized_today(self, session: Session) -> float:
        midnight = now().replace(hour=0, minute=0, second=0, microsecond=0)
        rows = session.exec(select(Trade.pnl).where(Trade.mode == self.mode, Trade.status == "closed", Trade.exit_time >= midnight)).all()
        return sum(p or 0.0 for p in rows)

    def _blocked(self, session: Session, active: list[Trade], symbol: str, equity: float) -> str | None:
        if len(active) >= settings.max_open_positions:
            return "max open positions reached"
        if any(t.symbol == symbol for t in active):
            return "already in a position on this symbol"
        if self._realized_today(session) <= -settings.max_daily_loss * equity:
            return "daily loss limit reached"
        if equity - sum(t.margin for t in active) < 10:
            return "no free margin"
        return None

    @staticmethod
    def _margin(active: list[Trade], equity: float, news_id: str | None) -> float:
        """Margin for a new trade: a fraction of equity, within free margin and the per-announcement cap."""
        margin = min(equity * settings.margin_fraction, equity - sum(t.margin for t in active))
        if news_id is not None:
            margin = min(margin, equity * settings.max_notice_fraction - sum(t.margin for t in active if t.news_id == news_id))
        return margin

    async def open_position(
        self, symbol: str, side: int, leverage: float, *, stop: float, take_profit: float, trail: float, hold: timedelta, trigger: str, news_id: str | None = None
    ) -> Trade | None:
        async with self._lock:
            with Session(engine) as session:
                active = self._open_trades(session)
                equity = await self.equity(session)
                margin = self._margin(active, equity, news_id)
                blocked = self._blocked(session, active, symbol, equity) or ("announcement exposure cap reached" if margin < 10 else None)
                if blocked:
                    log.warning("not opening %s (%s): %s", symbol, trigger, blocked)
                    record(news_id, trigger.removeprefix("fast ").split(":")[0], symbol, "blocked", blocked)
                    return None
                leverage = min(float(leverage), float(settings.max_leverage))
                fill = await self.broker.open(symbol, side, margin * leverage / await self.broker.price(symbol), leverage)
                trade = Trade(
                    mode=self.mode,
                    symbol=symbol,
                    side=side,
                    leverage=leverage,
                    margin=margin,
                    quantity=fill.qty,
                    entry_price=fill.price,
                    entry_time=now(),
                    stop_price=fill.price * (1 - side * stop) if stop else None,
                    take_profit_price=fill.price * (1 + side * take_profit) if take_profit else None,
                    trail=trail,
                    best_price=fill.price,
                    exit_due=now() + hold,
                    trigger=trigger,
                    news_id=news_id,
                    fees=fill.fee,
                )
                if trade.stop_price is not None:
                    await self.broker.protect(symbol, side, fill.qty, trade.stop_price)
                session.add(trade)
                session.commit()
                session.refresh(trade)
                orders_total.labels(self.mode, "buy" if side > 0 else "sell").inc()
                open_positions.labels(self.mode).set(len(active) + 1)
                log.warning(
                    "OPEN %s %s %s qty=%.6g @ %.6g %gx margin=%.2f — %s", self.mode, "LONG" if side > 0 else "SHORT", symbol, fill.qty, fill.price, leverage, margin, trigger
                )
                record(news_id, trigger.removeprefix("fast ").split(":")[0], symbol, "entered", f"trade {trade.id}")
                return trade

    async def monitor(self) -> None:
        async with self._lock:
            with Session(engine) as session:
                active = self._open_trades(session)
                for t in active:
                    price = await self.broker.price(t.symbol)
                    reason = exit_reason(t, price, now(), paper=self.mode != "live")
                    if reason:
                        await self._close(t, price, reason)
                    else:
                        update_trail(t, price)
                    session.add(t)
                session.commit()
                open_positions.labels(self.mode).set(sum(t.status == "open" for t in active))

    async def _close(self, t: Trade, price: float, reason: str) -> None:
        if reason == "liquidation":
            exit_price, fee, gross = liquidation_price(t), 0.0, -t.margin
        else:
            fill = await self.broker.close(t.symbol, t.side, t.quantity)
            if fill is None:
                fill, reason = type("F", (), {"price": price, "fee": 0.0})(), f"{reason}:exchange"
            exit_price, fee = fill.price, fill.fee
            gross = max(t.side * t.quantity * (exit_price - t.entry_price), -t.margin)
        t.fees += fee
        t.pnl = gross - t.fees
        t.status, t.exit_price, t.exit_time, t.exit_reason = "closed", exit_price, now(), reason
        trades_closed_total.labels(self.mode, reason.split(":")[0]).inc()
        log.warning("CLOSE %s %s %s @ %.6g (%s): pnl %.2f", self.mode, "LONG" if t.side > 0 else "SHORT", t.symbol, exit_price, reason, t.pnl)


async def run_forever(stop: asyncio.Event | None = None) -> None:
    """`trader run` / RUN_WATCHER=true: the trading loop with the broker TRADING_MODE selects."""
    broker: Broker = LiveBroker() if settings.trading_mode == "live" else PaperBroker()
    llm = LLM()
    try:
        await Trader(broker, llm if llm.enabled else None).run(stop or asyncio.Event())
    finally:
        await broker.aclose()
        await llm.aclose()
