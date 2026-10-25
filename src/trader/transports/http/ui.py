"""HTTP API for the web UI — the bots' state and control, the paper and live books, historical-test jobs, charts."""

import json
import time
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Session, col, select

from trader.bots import BOTS
from trader.core.config import settings
from trader.core.db import create_db_and_tables, engine
from trader.integrations import binance
from trader.models import NewsItem, Trade
from trader.quant import evidence, neutral, paper, retrain
from trader.services import jobs, processes
from trader.status import notice_bot, quant_bot

router = APIRouter(prefix="/api/v1", tags=["ui"])
BotKey = Literal["notice", "quant"]
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
    }


def _bots() -> list[dict]:
    state = processes.status()
    return [
        {"key": b.key, "number": b.number, "name": b.name, "what": b.what, "commands": list(b.commands), "confirm_phrase": _confirm_phrase(b.key), **state[b.key]} for b in BOTS
    ]


def _events(limit: int = 40) -> list[dict]:
    create_db_and_tables()
    out: list[dict] = []
    with Session(engine) as session:
        for item in session.exec(select(NewsItem).where(col(NewsItem.source).in_(["binance", "upbit"])).order_by(col(NewsItem.published_at).desc()).limit(limit)):
            kinds = [e.get("type") for e in item.events or [] if e.get("type")]
            out.append({
                "at": item.published_at.isoformat(),
                "bot": "notice",
                "kind": "notice",
                "title": item.title,
                "detail": ", ".join(kinds) or "без торгової події",
                "tone": "info" if kinds else "quiet",
                "source": item.source,
            })
        for trade in session.exec(select(Trade).order_by(col(Trade.entry_time).desc()).limit(limit)):
            side = "лонг" if trade.side > 0 else "шорт"
            out.append({
                "at": trade.entry_time.isoformat(),
                "bot": "notice",
                "kind": "trade_open",
                "title": f"{trade.symbol}: відкрито {side} ({trade.mode})",
                "detail": trade.trigger,
                "tone": "info",
            })
            if trade.exit_time:
                pnl = trade.pnl or 0.0
                tone = "gain" if pnl > 0 else "loss"
                out.append({
                    "at": trade.exit_time.isoformat(),
                    "bot": "notice",
                    "kind": "trade_close",
                    "title": f"{trade.symbol}: закрито, {pnl:+.2f} USDT",
                    "detail": trade.exit_reason or "",
                    "tone": tone,
                })
    ledger = paper.ledger_path()
    if ledger.exists():
        for row in json.loads(ledger.read_text())["history"][-limit:]:
            pnl = row.get("pnl_since_last", 0.0)
            out.append({
                "at": row["rebalanced_at"],
                "bot": "quant",
                "kind": "rebalance",
                "title": f"Ребаланс: {row['longs']} лонгів / {row['shorts']} шортів",
                "detail": f"P&L з попереднього {pnl:+.2f} USDT · витрати {row['cost']:.2f} · капітал {row['equity']:.2f}",
                "tone": "gain" if pnl > 0 else "loss" if pnl < 0 else "info",
            })
    for job in jobs.listing(15):
        stamp = job.get("finished_at") or job.get("created_at")
        out.append({
            "at": stamp,
            "bot": "lab",
            "kind": "job",
            "title": job["title"],
            "detail": job["status"],
            "tone": {"done": "info", "failed": "loss"}.get(job["status"], "quiet"),
            "job": job["id"],
        })
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


@router.get("/notice/feed")
def notice_feed(limit: Annotated[int, Query(ge=1, le=500)] = 100, events_only: bool = False) -> list[dict]:
    create_db_and_tables()
    with Session(engine) as session:
        query = select(NewsItem).where(col(NewsItem.source).in_(["binance", "upbit"])).order_by(col(NewsItem.published_at).desc()).limit(limit * (4 if events_only else 1))
        items = list(session.exec(query))
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
