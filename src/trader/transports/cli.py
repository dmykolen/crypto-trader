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
from trader.intel.cli import app as intel_app
from trader.quant.cli import quant as quant_app

app = typer.Typer(no_args_is_help=True, help="AI-assisted crypto research & trading for Binance USDⓈ-M perpetuals.")
research = typer.Typer(no_args_is_help=True, help="Learn strategies from history (out-of-sample) and write reports.")
app.add_typer(research, name="research")
app.add_typer(quant_app, name="quant")
app.add_typer(intel_app, name="intel")


@app.command("bots")
def bots_list() -> None:
    """The trading bots of this app and how to run each one."""
    from trader.bots import BOTS

    _print([{"bot": f"#{b.number} {b.name}", "key": b.key, "what": b.what, "commands": list(b.commands)} for b in BOTS])


job = typer.Typer(no_args_is_help=True, help="Background jobs started from the web UI.")
app.add_typer(job, name="job")


@job.command("run")
def job_run(job_id: str) -> None:
    """Run one queued web-UI job (historical test, forward test, retraining) and store its result."""
    from trader.services import jobs

    doc = jobs.run(job_id)
    _print({k: doc.get(k) for k in ("id", "kind", "status", "error")})


@app.command("status")
def bots_status() -> None:
    """How each bot is doing on its paper account right now."""
    from trader.status import summary

    _print(summary())


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


@research.command("proof")
def research_proof(latency_s: Annotated[float, typer.Option(help="reaction time to replay")] = 1.0) -> None:
    """Every walk-forward fast trade with its announcement link, tick prices and the Binance archive file that proves them."""
    import numpy as np
    import pandas as pd
    from sqlmodel import select

    from trader.models import NewsItem
    from trader.services import fast, ticks

    frame = pd.read_parquet(settings.reports_dir / "lab" / "tick_reactions_v2.parquet")
    latency = ticks.as_latency(latency_s)
    robust = np.nanmean(np.stack([ticks.outcome_matrix(frame, x) for x in fast.neighbourhood(latency)]), axis=0)
    decisions = ticks.walk_forward(frame, latency, select_matrix=robust)
    log = ticks.trade_log(frame, decisions, latency)
    with Session(engine) as session:
        urls = {i.title: i.url for i in session.exec(select(NewsItem).where(NewsItem.source.in_(["upbit", "binance"]))).all()}
    log["announcement_url"] = log.title.map(urls)
    path = settings.reports_dir / "lab" / f"proof_trades_L{latency}.csv"
    log.to_csv(path, index=False)
    account = ticks.account(decisions, cap_notional=10_000.0)
    recent = decisions[pd.to_datetime(decisions.ts, unit="ms", utc=True) >= pd.Timestamp("2026-07-01", tz="UTC")]
    holdout = ticks.account(recent, first="2026-07-01", cap_notional=10_000.0)
    _print({
        "csv": str(path),
        "trades": len(log),
        "winners": int((log.ret_on_margin > 0).sum()),
        "losers": int((log.ret_on_margin <= 0).sum()),
        "account_cap10k": account,
        "holdout_cap10k": holdout,
    })


@app.command()
def replay(
    day: Annotated[str, typer.Argument(help="first UTC day to replay, YYYY-MM-DD")],
    days: Annotated[int, typer.Option(help="number of days")] = 1,
) -> None:
    """Run the real trading loop over past days: every notice, order and exit on historical tick and minute prices, playbooks learned only from earlier events."""
    from datetime import UTC, datetime

    from trader.services import replay as replay_service

    create_db_and_tables()
    doc = asyncio.run(replay_service.replay(datetime.fromisoformat(day).replace(tzinfo=UTC), days))
    out = settings.reports_dir / "replay"
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{day}_{days}d.json").write_text(json.dumps(doc, indent=2, default=str))
    (out / f"{day}_{days}d.md").write_text(replay_service.markdown(doc))
    _print({
        "report": str(out / f"{day}_{days}d.md"),
        "notices": len(doc["notices"]),
        **{name: {k: s[k] for k in ("trades", "winners", "pnl", "final_equity", "max_drawdown_pct", "days_with_100_or_more")} for name, s in doc["scenarios"].items()},
    })


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
def serve(host: str = "127.0.0.1", port: int = 8710) -> None:
    """Start the API and the web control room on http://127.0.0.1:8710 (RUN_WATCHER=true also runs the trading loop inside it)."""
    import uvicorn

    from trader.main import WEB_DIST

    if not (WEB_DIST / "index.html").exists():
        console.print("[yellow]web UI is not built: cd web && pnpm install && pnpm build[/yellow]")
    console.print(f"control room: http://{host}:{port}")
    uvicorn.run("trader.main:app", host=host, port=port)
