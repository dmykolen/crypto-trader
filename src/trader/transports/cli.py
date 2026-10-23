"""`trader` command line — research, reports, AI analysis, the trading loop and the API server."""

import asyncio
import json
from typing import Annotated

import typer
from rich.console import Console
from sqlmodel import Session

from trader.core.config import settings
from trader.core.db import create_db_and_tables, engine
from trader.core.logging import configure_logging

app = typer.Typer(no_args_is_help=True, help="AI-assisted crypto research & trading for Binance USDⓈ-M perpetuals.")
research = typer.Typer(no_args_is_help=True, help="Learn strategies from history (out-of-sample) and write reports.")
app.add_typer(research, name="research")
console = Console()


@app.callback()
def _setup() -> None:
    configure_logging(settings.log_level, settings.log_format)
    create_db_and_tables()


def _print(doc) -> None:
    console.print_json(json.dumps(doc, default=str, ensure_ascii=False))


def _with_llm(fn, *args):
    """Run `await fn(llm, *args)` with a fresh Claude client, closed afterwards."""
    from trader.integrations.llm import LLM

    async def go():
        llm = LLM()
        try:
            return await fn(llm, *args)
        finally:
            await llm.aclose()

    return asyncio.run(go())


@app.command()
def backfill(binance_pages: int = 100) -> None:
    """Download the full Upbit + Binance notice history into the database."""
    from trader.services.news import backfill as run

    with Session(engine) as session:
        _print(asyncio.run(run(session, binance_pages=binance_pages)))


@research.command("events")
def research_events(latency_s: Annotated[int, typer.Option(help="seconds between an announcement and our first fill")] = settings.entry_latency_s) -> None:
    """Event study + walk-forward playbook selection over every past exchange notice → reports/event_research.*"""
    from trader.services import report

    settings.entry_latency_s = latency_s
    with Session(engine) as session:
        _print(report.event_research(session)["headline"])


@research.command("strategies")
def research_strategies(
    symbols: Annotated[list[str], typer.Argument(help="e.g. BTCUSDT ETHUSDT SOLUSDT")],
    days: int = 365,
    interval: str = "15m",
    train_days: int = 60,
    fold_days: int = 7,
) -> None:
    """Walk-forward strategy selection per token (trend / breakout / mean reversion / ML) → reports/strategy_selection.*"""
    from trader.services import report

    _print(report.strategy_research(symbols, days=days, interval=interval, train_days=train_days, fold_days=fold_days)["summary"])


@research.command("ticks")
def research_ticks(download: Annotated[bool, typer.Option(help="fetch tick windows for notices not yet cached")] = True) -> None:
    """Second-by-second reaction of every past notice (aggTrades) → latency study + fast playbooks (data/fast_playbooks.json)."""
    from trader.services import fast, lab, ticks

    if download:
        with Session(engine) as session:
            ticks.study(session)
    frame = ticks.restudy()
    report = ticks.latency_report(frame)
    lab.save("tick_latency_v2", report)
    fitted = fast.fit_all(frame)
    fast.save(fitted)
    by_latency = {L: {k: row["by_type"]["cap10k"]["all"][k] for k in ("trades", "mean_ret", "final_equity", "mean_daily_usd", "max_drawdown_pct")} for L, row in report.items()}
    live = {L: {k: v.get("describe") for k, v in types.items() if v.get("playbook")} for L, types in fitted.items()}
    _print({"fast_playbooks_by_latency": live, "by_latency_cap10k": by_latency})


@research.command("review")
def research_review(name: str = "event_research") -> None:
    """Claude reviews a research report for overfitting, cost sensitivity and failure modes."""
    from trader.services import report

    _print(_with_llm(report.review, name))


@app.command()
def forecast(symbol: str, interval: str = "1h", days: int = 365) -> None:
    """Multi-horizon LightGBM forecast with its out-of-sample accuracy."""
    from trader.services import analysis

    _print(analysis.forecast_symbol(symbol, interval, days))


@app.command()
def brief(symbol: str, interval: str = "1h") -> None:
    """Claude's desk brief for a symbol, grounded in the app's own measurements."""
    from trader.services import analysis

    _print(_with_llm(analysis.brief, symbol, interval).model_dump())


@app.command("analyze-news")
def analyze_news(title: str, summary: str | None = None, source: str | None = None) -> None:
    """Rule-based events + Claude's price-impact assessment of one headline."""
    from trader.services import analysis

    _print(_with_llm(analysis.analyze_headline, title, summary, source))


@app.command()
def run() -> None:
    """News watcher + trading loop (paper by default; TRADING_MODE=live trades real money)."""
    from trader.services import trading

    asyncio.run(trading.run_forever())


@app.command()
def serve(host: str = "127.0.0.1", port: int = 8000) -> None:
    """Start the HTTP API (RUN_WATCHER=true also runs the trading loop inside it)."""
    import uvicorn

    uvicorn.run("trader.main:app", host=host, port=port)
