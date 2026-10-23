"""HTTP API v1 — the news and trade journals, the research reports, forecasts and Claude's analysis."""

import json
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import String, cast
from sqlmodel import col, select

from trader.core.config import settings
from trader.core.db import SessionDep
from trader.integrations.llm import LLM
from trader.models import NewsItem, Trade
from trader.services import analysis, playbooks

router = APIRouter(prefix="/api/v1", tags=["trader"])
REPORTS = ("event_research", "strategy_selection", "event_research_review", "strategy_selection_review")
Interval = Literal["15m", "1h", "4h", "1d"]


def get_llm(request: Request) -> LLM:
    return request.app.state.llm


def require_llm(llm: Annotated[LLM, Depends(get_llm)]) -> LLM:
    if not llm.enabled:
        raise HTTPException(503, "ANTHROPIC_API_KEY is not configured")
    return llm


@router.get("/news")
def list_news(session: SessionDep, source: str | None = None, events_only: bool = False, limit: Annotated[int, Query(ge=1, le=500)] = 50) -> list[NewsItem]:
    query = select(NewsItem).order_by(col(NewsItem.published_at).desc()).limit(limit)
    if source:
        query = query.where(NewsItem.source == source)
    if events_only:
        query = query.where(cast(NewsItem.events, String) != "[]")
    return list(session.exec(query).all())


@router.get("/trades")
def list_trades(session: SessionDep, status: Literal["open", "closed"] | None = None, limit: Annotated[int, Query(ge=1, le=1000)] = 100) -> list[Trade]:
    query = select(Trade).where(Trade.mode == settings.trading_mode).order_by(col(Trade.entry_time).desc()).limit(limit)
    if status:
        query = query.where(Trade.status == status)
    return list(session.exec(query).all())


@router.get("/portfolio")
def portfolio(session: SessionDep) -> dict:
    trades = session.exec(select(Trade).where(Trade.mode == settings.trading_mode)).all()
    closed = [t for t in trades if t.status == "closed"]
    realized = round(sum(t.pnl or 0.0 for t in closed), 2)
    return {
        "mode": settings.trading_mode,
        "paper_equity": round(settings.paper_equity + realized, 2) if settings.trading_mode == "paper" else None,
        "realized_pnl": realized,
        "closed_trades": len(closed),
        "win_rate": round(sum((t.pnl or 0.0) > 0 for t in closed) / len(closed), 3) if closed else None,
        "open": [t.model_dump(mode="json") for t in trades if t.status == "open"],
    }


@router.get("/playbooks")
def get_playbooks() -> dict:
    """The event playbooks live trading uses (from the last `trader research events`)."""
    return playbooks.saved()


@router.get("/reports/{name}")
def get_report(name: str) -> dict:
    path = settings.reports_dir / f"{name}.json"
    if name not in REPORTS or not path.exists():
        raise HTTPException(404, f"no report {name!r} — run `trader research …` first")
    return json.loads(path.read_text())


@router.get("/forecast/{symbol}")
def get_forecast(symbol: str, interval: Interval = "1h", days: Annotated[int, Query(ge=60, le=1500)] = 365) -> dict:
    try:
        return analysis.forecast_symbol(symbol.upper(), interval, days)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


class Headline(BaseModel):
    title: str
    summary: str | None = None
    source: str | None = None


@router.post("/analyze")
async def analyze(headline: Headline, llm: Annotated[LLM, Depends(get_llm)]) -> dict:
    return await analysis.analyze_headline(llm, headline.title, headline.summary, headline.source)


@router.post("/brief/{symbol}")
async def brief(symbol: str, llm: Annotated[LLM, Depends(require_llm)], interval: Interval = "1h") -> dict:
    return (await analysis.brief(llm, symbol.upper(), interval)).model_dump()
