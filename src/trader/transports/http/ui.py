"""HTTP API for the web UI — the bots' state and control, the paper and live books, historical-test jobs, charts."""

import asyncio
import hashlib
import json
import time
from collections.abc import AsyncIterable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Any, Literal

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.sse import EventSourceResponse
from pydantic import BaseModel
from sqlmodel import Session, col, select

from trader.bots import BOTS
from trader.core.config import settings
from trader.core.db import create_db_and_tables, engine
from trader.integrations import binance
from trader.models import NewsItem, Trade
from trader.quant import evidence, limit_test, neutral, paper, retrain, why
from trader.services import jobs, processes, supervisor, trading
from trader.status import notice_bot, quant_bot

router = APIRouter(prefix="/api/v1", tags=["ui"])
BotKey = Literal["notice", "quant"]
BOT_MODES = ("paper", "live")
_prices: dict[str, Any] = {"at": 0.0, "data": {}}


def _confirm_phrase(bot: str) -> str:
    return f"LIVE {bot.upper()}"


def live_prices(max_age: float = 15.0) -> dict[str, float]:
    if time.monotonic() - _prices["at"] > max_age:
        rows = binance.FuturesREST()._get("/fapi/v1/ticker/price")
        _prices.update({"at": time.monotonic(), "data": {r["symbol"]: float(r["price"]) for r in rows}})
    return _prices["data"]


def _next_rebalance(now: datetime) -> str:
    due = datetime(now.year, now.month, now.day, 0, 15, tzinfo=UTC)
    return (due if now < due else due + timedelta(days=1)).isoformat(timespec="seconds")


def system_info() -> dict:
    meta = retrain.meta()
    through = meta.get("data_through")
    return {
        "now": datetime.now(UTC).isoformat(timespec="seconds"),
        "trading_mode_default": settings.trading_mode,
        "live_ready": processes.live_ready(),
        "testnet": bool(getattr(settings, "binance_testnet", False)),
        "models_trained_through": datetime.fromtimestamp(int(through) / 1000, UTC).isoformat(timespec="minutes") if through else None,
        "models_trained_at": meta.get("trained_at"),
        "next_retrain_due": "2027-01-02",
        "next_quant_rebalance": _next_rebalance(datetime.now(UTC)),
        "risk": risk_limits(),
    }


def risk_limits() -> dict:
    """The real-money rails each bot runs under, read from the same settings and limits the bots use."""
    from trader.quant import live_exec

    quant = live_exec.Limits()
    return {
        "notice": {"margin_fraction": settings.margin_fraction, "max_leverage": settings.max_leverage, "max_open_positions": settings.max_open_positions},
        "quant": {"leverage": quant.leverage, "max_gross": quant.max_gross, "max_position": quant.max_position, "kill_drawdown": quant.kill_drawdown},
    }


def _bots() -> list[dict]:
    state = processes.status()
    return [
        {"key": b.key, "number": b.number, "name": b.name, "what": b.what, "commands": list(b.commands), "confirm_phrase": _confirm_phrase(b.key), **state[b.key]} for b in BOTS
    ]


def _iso(at: datetime) -> str:
    return (at if at.tzinfo else at.replace(tzinfo=UTC)).isoformat()


def _events(limit: int = 40) -> list[dict]:
    """The activity tape as structured facts; the UI does all wording and number formatting."""
    create_db_and_tables()
    out: list[dict] = []
    with Session(engine) as session:
        for item in session.exec(select(NewsItem).where(col(NewsItem.source).in_(["binance", "upbit"])).order_by(col(NewsItem.published_at).desc()).limit(limit)):
            out.append({
                "at": _iso(item.published_at),
                "bot": "notice",
                "kind": "notice",
                "title": item.title,
                "source": item.source,
                "events": [{"type": e["type"], "symbols": e.get("symbols") or ([e["symbol"]] if e.get("symbol") else [])} for e in item.events or [] if e.get("type")],
            })
        for trade in session.exec(select(Trade).where(col(Trade.mode).in_(BOT_MODES)).order_by(col(Trade.entry_time).desc()).limit(limit)):
            base = {"bot": "notice", "symbol": trade.symbol, "side": "long" if trade.side > 0 else "short", "mode": trade.mode, "trigger": trade.trigger}
            out.append({**base, "at": _iso(trade.entry_time), "kind": "trade_open"})
            if trade.exit_time:
                out.append({**base, "at": _iso(trade.exit_time), "kind": "trade_close", "pnl": trade.pnl or 0.0, "exit_reason": trade.exit_reason})
    ledger = paper.ledger_path()
    if ledger.exists():
        history = json.loads(ledger.read_text())["history"]
        for i, row in list(enumerate(history))[-limit:]:
            out.append({
                "at": row["rebalanced_at"],
                "bot": "quant",
                "kind": "rebalance",
                "opening": i == 0,
                "longs": row["longs"],
                "shorts": row["shorts"],
                "pnl": row.get("pnl_since_last", 0.0),
                "cost": row["cost"],
                "equity": row["equity"],
            })
    for job in jobs.listing(15):
        out.append({"at": job.get("finished_at") or job.get("created_at"), "bot": "lab", "kind": "job", "title": job["title"], "status": job["status"], "job": job["id"]})
    out.sort(key=lambda e: e["at"] or "", reverse=True)
    return out[:limit]


@router.get("/overview")
def overview() -> dict:
    return {"system": system_info(), "bots": _bots(), "paper": {"notice": notice_bot(), "quant": quant_bot()}, "events": _events(30)}


@router.get("/bots")
def bots() -> list[dict]:
    return _bots()


class StartBody(BaseModel):
    mode: Literal["paper", "live"] = "paper"
    confirm: str | None = None


@router.post("/bots/{bot}/start")
def start_bot(bot: BotKey, body: StartBody) -> dict:
    if body.mode == "live" and body.confirm != _confirm_phrase(bot):
        raise HTTPException(400, f"to trade real money type exactly: {_confirm_phrase(bot)}")
    try:
        processes.start(bot, body.mode)
    except processes.ProcessError as exc:
        raise HTTPException(409, str(exc)) from exc
    return processes.status()[bot]


@router.post("/bots/{bot}/stop")
def stop_bot(bot: BotKey) -> dict:
    try:
        processes.stop(bot)
    except processes.ProcessError as exc:
        raise HTTPException(409, str(exc)) from exc
    return processes.status()[bot]


@router.get("/bots/{bot}/logs")
def bot_logs(bot: BotKey, lines: Annotated[int, Query(ge=10, le=2000)] = 300) -> dict:
    return {"bot": bot, "lines": processes.logs(bot, lines)}


@router.get("/quant/ledger")
def quant_ledger() -> dict:
    path = paper.ledger_path()
    if not path.exists():
        return {"started": False}
    state = json.loads(path.read_text())
    try:
        prices = live_prices()
    except Exception:
        prices = {}
    base = state["equity"]
    positions, unrealized = [], 0.0
    for sym, pos in state["positions"].items():
        price = prices.get(sym)
        move = price / pos["entry"] - 1 if price else None
        pnl = pos["weight"] * base * move if move is not None else None
        unrealized += pnl or 0.0
        positions.append({
            "symbol": sym,
            "side": "long" if pos["weight"] > 0 else "short",
            "weight": pos["weight"],
            "notional": abs(pos["weight"]) * base,
            "entry": pos["entry"],
            "price": price,
            "move": move,
            "pnl": pnl,
        })
    positions.sort(key=lambda p: -abs(p["weight"]))
    now = datetime.now(UTC)
    return {
        "started": True,
        "start_equity": state["start_equity"],
        "equity": base,
        "equity_now": base + unrealized,
        "unrealized": unrealized,
        "return_now_pct": 100 * ((base + unrealized) / state["start_equity"] - 1),
        "history": state["history"],
        "positions": positions,
        "gross": sum(abs(p["weight"]) for p in positions),
        "net": sum(p["weight"] for p in positions),
        "priced_at": now.isoformat(timespec="seconds"),
        "next_rebalance": _next_rebalance(now),
    }


@router.get("/quant/limit-test")
def quant_limit_test() -> dict:
    return limit_test.summary()


@router.get("/quant/live")
def quant_live() -> dict:
    from trader.quant import live_exec

    return {"live_ready": processes.live_ready(), **live_exec.load_ledger()}


@router.get("/quant/config")
def quant_config() -> dict:
    return {
        "ensemble": neutral.ENSEMBLE,
        "models": retrain.meta(),
        "decision": "щодня о 23:00 UTC, ребаланс о 00:15 UTC",
        "costs": {"per_side": 0.0008, "note": "комісія taker 0.05 % + проковзування 0.03 %"},
    }


@router.get("/quant/evidence")
def quant_evidence() -> dict:
    doc = evidence.load()
    if doc is None:
        raise HTTPException(404, "evidence not built yet — start the job «quant_evidence»")
    return doc


@router.get("/notice/trades")
def notice_trades(limit: Annotated[int, Query(ge=1, le=1000)] = 200) -> list[dict]:
    """The bot's paper and live trades together (replay simulations excluded), newest first, with explicit UTC timestamps."""
    create_db_and_tables()
    with Session(engine) as session:
        rows = session.exec(select(Trade).where(col(Trade.mode).in_(BOT_MODES)).order_by(col(Trade.entry_time).desc()).limit(limit)).all()
    return [{**t.model_dump(), **{k: _iso(v) for k in ("entry_time", "exit_due", "exit_time") if (v := getattr(t, k)) is not None}} for t in rows]


@router.get("/notice/daily")
def notice_daily(days: Annotated[int, Query(ge=1, le=90)] = 14) -> list[dict]:
    """Announcements per UTC day, and how many of them carried a tradable event — the notice bot's daily workload."""
    create_db_and_tables()
    first = datetime.now(UTC).date() - timedelta(days=days - 1)
    since = datetime(first.year, first.month, first.day, tzinfo=UTC)
    counts = {first + timedelta(days=i): [0, 0] for i in range(days)}
    with Session(engine) as session:
        rows = session.exec(select(NewsItem).where(col(NewsItem.source).in_(["binance", "upbit"]), col(NewsItem.published_at) >= since))
        for item in rows:
            day = datetime.fromisoformat(_iso(item.published_at)).date()
            if day in counts:
                counts[day][0] += 1
                counts[day][1] += any(e.get("type") for e in item.events or [])
    return [{"day": day.isoformat(), "total": total, "events": events} for day, (total, events) in counts.items()]


@router.get("/notice/feed")
def notice_feed(limit: Annotated[int, Query(ge=1, le=500)] = 100, events_only: bool = False) -> list[dict]:
    create_db_and_tables()
    with Session(engine) as session:
        query = select(NewsItem).where(col(NewsItem.source).in_(["binance", "upbit"])).order_by(col(NewsItem.published_at).desc()).limit(limit * (4 if events_only else 1))
        items = list(session.exec(query))
    decided: dict[str, list[dict]] = {}
    path = trading.decisions_path()
    for line in path.read_text().splitlines()[-5000:] if path.exists() else []:
        d = json.loads(line)
        decided.setdefault(d.get("news_id") or "", []).append({k: d[k] for k in ("at", "event", "token", "outcome", "detail")})
    rows = []
    for item in items:
        kinds = [e for e in item.events or [] if e.get("type")]
        if events_only and not kinds:
            continue
        published = item.published_at if item.published_at.tzinfo else item.published_at.replace(tzinfo=UTC)
        seen = item.seen_at if item.seen_at.tzinfo else item.seen_at.replace(tzinfo=UTC)
        rows.append({
            "id": item.id,
            "source": item.source,
            "title": item.title,
            "url": item.url,
            "published_at": published.isoformat(),
            "seen_at": seen.isoformat(),
            "latency_s": round((seen - published).total_seconds(), 1),
            "events": [{"type": e.get("type"), "symbols": e.get("symbols") or ([e["symbol"]] if e.get("symbol") else [])} for e in kinds],
            "decisions": decided.get(item.id, []),
        })
    return rows[:limit]


@router.get("/notice/summary")
def notice_summary() -> dict:
    from trader.services import playbooks

    fast = settings.data_dir / "fast_playbooks.json"
    return {
        "paper": notice_bot(),
        "playbooks": playbooks.saved(),
        "fast_playbooks": json.loads(fast.read_text()) if fast.exists() else None,
        "stream": {"binance_ws": processes.live_ready()},
    }


@router.get("/market/klines")
def market_klines(
    symbol: str, interval: Literal["1m", "5m", "15m", "1h", "4h", "1d"] = "1h", hours: Annotated[int, Query(ge=1, le=24 * 120)] = 72, end: datetime | None = None
) -> dict:
    stop = end or datetime.now(UTC)
    start = stop - timedelta(hours=hours)
    bars = binance.FuturesREST().klines(symbol.upper(), interval, int(start.timestamp() * 1000), int(stop.timestamp() * 1000))
    if bars is None or bars.empty:
        return {"symbol": symbol.upper(), "bars": []}
    rows = bars[["open_time", "open", "high", "low", "close", "volume"]].astype(float).to_numpy().tolist()
    return {"symbol": symbol.upper(), "interval": interval, "bars": [[int(r[0]), *r[1:]] for r in rows]}


@router.post("/uploads", status_code=201)
async def upload_quotes(request: Request) -> dict:
    from trader.quant import day

    body = await request.body()
    if not body or len(body) > 30_000_000:
        raise HTTPException(413, "CSV must be between 1 byte and 30 MB")
    key = hashlib.sha256(body).hexdigest()[:16]
    path = jobs.uploads_dir() / f"{key}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    try:
        bars = day.from_csv(path)
    except (ValueError, KeyError, pd.errors.ParserError) as exc:
        path.unlink(missing_ok=True)
        raise HTTPException(422, str(exc)) from exc
    first, last = (datetime.fromtimestamp(int(t) / 1000, UTC) for t in (bars.open_time.min(), bars.open_time.max()))
    return {"upload": key, "bars": len(bars), "from": _iso(first), "to": _iso(last)}


class JobBody(BaseModel):
    kind: str
    params: dict = {}


@router.get("/jobs")
def list_jobs(limit: Annotated[int, Query(ge=1, le=200)] = 50) -> list[dict]:
    return jobs.listing(limit)


@router.post("/jobs", status_code=201)
def create_job(body: JobBody) -> dict:
    try:
        return jobs.create(body.kind, body.params)
    except jobs.JobError as exc:
        raise HTTPException(400, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    try:
        return jobs.get(job_id)
    except jobs.JobError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.delete("/jobs/{job_id}")
def cancel_job(job_id: str) -> dict:
    try:
        return jobs.cancel(job_id)
    except jobs.JobError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/system")
def system() -> dict:
    return system_info()


class Toggle(BaseModel):
    enabled: bool


@router.get("/processes")
def process_list() -> dict:
    return {"now": datetime.now(UTC).isoformat(timespec="seconds"), "processes": supervisor.inventory()}


@router.post("/processes/{key}/stop")
def process_stop(key: str) -> dict:
    try:
        return supervisor.stop(key)
    except (supervisor.SupervisorError, processes.ProcessError, jobs.JobError) as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/bots/{bot}/restart")
def restart_bot(bot: BotKey) -> dict:
    try:
        supervisor.restart_bot(bot)
    except (supervisor.SupervisorError, processes.ProcessError) as exc:
        raise HTTPException(409, str(exc)) from exc
    return processes.status()[bot]


@router.post("/server/restart")
def restart_server() -> dict:
    return supervisor.restart_server()


@router.get("/autostart")
def autostart() -> dict:
    return supervisor.autostart()


@router.post("/autostart")
def set_autostart(body: Toggle) -> dict:
    try:
        return supervisor.set_autostart(body.enabled)
    except supervisor.SupervisorError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/disk")
def disk() -> dict:
    return supervisor.disk()


@router.post("/disk/clean")
def clean_disk() -> dict:
    return supervisor.clean_caches()


@router.get("/schedule")
def schedule() -> dict:
    return {"items": supervisor.schedule(), "errors": supervisor.errors()}


def _log(source: str) -> Path:
    try:
        return supervisor.log_file(source)
    except (supervisor.SupervisorError, jobs.JobError) as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/logs/{source}")
def log_tail(source: str, lines: Annotated[int, Query(ge=10, le=2000)] = 300) -> dict:
    text, _ = supervisor.tail(_log(source), lines)
    return {"source": source, "lines": text}


@router.get("/logs/{source}/stream", response_class=EventSourceResponse)
async def log_stream(path: Annotated[Path, Depends(_log)], poll: float = 0.6) -> AsyncIterable[dict]:
    lines, position = supervisor.tail(path, 300)
    yield {"lines": lines, "reset": True}
    while True:
        await asyncio.sleep(poll)
        size = path.stat().st_size if path.exists() else 0
        if size < position:
            position = 0
        if size <= position:
            continue
        with path.open("rb") as f:
            f.seek(position)
            data = f.read(size - position)
        cut = data.rfind(b"\n")
        if cut < 0:
            continue
        position += cut + 1
        if fresh := [x for x in data[:cut].decode("utf-8", errors="replace").splitlines() if x]:
            yield {"lines": fresh}


def _latest_day() -> str:
    history = json.loads(paper.ledger_path().read_text())["history"] if paper.ledger_path().exists() else []
    if not history:
        raise HTTPException(404, "the virtual account has no rebalances yet")
    return history[-1]["day"]


@router.get("/quant/why")
def quant_why(symbol: str, day: str | None = None) -> dict:
    try:
        return why.explain(symbol.upper(), day or _latest_day())
    except (LookupError, FileNotFoundError) as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/quant/ranks")
def quant_ranks(day: str | None = None) -> dict:
    day = day or _latest_day()
    try:
        return {"day": day, "ranks": why.ranks(day)}
    except (LookupError, FileNotFoundError) as exc:
        raise HTTPException(404, str(exc)) from exc
