"""`trader intel …` — source health, fetch passes, the watcher, per-symbol signals, history backfill and the study."""

import asyncio
from datetime import UTC, date, datetime, timedelta
from typing import Annotated

import typer
from sqlmodel import Session, col, select

app = typer.Typer(no_args_is_help=True, help="News & market intelligence: many sources → entity-linked signals per perp.")


def _print(doc) -> None:
    from trader.transports.cli import _print as show

    show(doc)


def _llm(enabled: bool):
    if not enabled:
        return None
    from trader.integrations.llm import LLM

    llm = LLM()
    return llm if llm.enabled else None


@app.command("sources")
def sources_cmd() -> None:
    """Health check of every source: ok/fail, item count, latency."""
    from trader.intel import pipeline, sources

    rows = pipeline.health(asyncio.run(sources.run()))
    from rich.table import Table

    from trader.transports.cli import console

    table = Table("source", "kind", "ok", "items", "latency s", "error")
    for r in rows:
        table.add_row(r["source"], r["kind"], "ok" if r["ok"] else "FAIL", str(r["items"]), f"{r['latency_s']:.2f}", r.get("error", "")[:70])
    console.print(table)
    console.print(f"{sum(r['ok'] for r in rows)}/{len(rows)} sources ok; known dead (not polled): {', '.join(sources.DEAD)}")


@app.command()
def fetch(
    llm: Annotated[bool, typer.Option(help="also run Claude deep analysis on the most relevant new items")] = False,
    llm_budget: Annotated[int, typer.Option(help="hard cap on Claude calls in this pass")] = 20,
) -> None:
    """One full pass over every source → NewsItem rows, series caches and hourly IntelSignal rows."""
    from trader.core.db import engine
    from trader.intel import pipeline
    from trader.intel.entities import default_linker

    async def go():
        client = _llm(llm)
        try:
            with Session(engine) as session:
                return await pipeline.fetch_pass(session, default_linker(), llm=client, llm_budget=llm_budget)
        finally:
            if client is not None:
                await client.aclose()

    report = asyncio.run(go())
    report["sources"] = {s["source"]: (s["items"] if s["ok"] else f"FAIL {s.get('error', '')[:60]}") for s in report["sources"]}
    _print(report)


@app.command()
def watch(
    seconds: Annotated[float, typer.Option(help="pause between passes")] = 60.0,
    llm: bool = False,
    llm_budget: Annotated[int, typer.Option(help="Claude calls per pass")] = 5,
    passes: Annotated[int | None, typer.Option(help="stop after N passes (default: forever)")] = None,
) -> None:
    """Poll text sources every N seconds (numeric series every 15th pass) and keep signals fresh."""
    from trader.core.db import engine
    from trader.intel import pipeline
    from trader.intel.entities import default_linker

    async def go():
        client = _llm(llm)
        try:
            with Session(engine) as session:
                await pipeline.watch(session, default_linker(), seconds, llm=client, llm_budget=llm_budget, passes=passes)
        finally:
            if client is not None:
                await client.aclose()

    asyncio.run(go())


@app.command("signals")
def signals_cmd(symbol: str, hours: int = 72) -> None:
    """Hourly news signals of a symbol (MARKET for the market-wide row) + the latest feature row."""
    from trader.core.db import engine
    from trader.intel import signals
    from trader.models import NewsItem

    symbol = symbol.upper()
    with Session(engine) as session:
        rows = signals.recent(session, symbol, hours)
        since = datetime.now(UTC) - timedelta(hours=hours)
        items = session.exec(select(NewsItem).where(col(NewsItem.published_at) >= since).order_by(col(NewsItem.published_at).desc())).all()
        headlines = [
            {"at": i.published_at.isoformat(), "source": i.source, "title": i.title, **{k: (i.analysis or {}).get("intel", {}).get(k) for k in ("category", "polarity")}}
            for i in items
            if symbol in ((i.analysis or {}).get("intel") or {}).get("symbols", [])
        ][:15]
        now = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
        feats = signals.features(symbol, now - timedelta(hours=24), now + timedelta(hours=1), session=session)
    latest = feats.iloc[-1].dropna().round(4).to_dict() if len(feats) else {}
    _print({
        "symbol": symbol,
        "hours_with_mentions": len(rows),
        "total_mentions": sum(r["mentions"] for r in rows),
        "hourly": rows[-24:],
        "headlines": headlines,
        "latest_features": latest,
    })


@app.command()
def backfill(
    metrics_symbols: Annotated[list[str] | None, typer.Option(help="perps for the metrics archive (default: the study universe)")] = None,
    start: str = "2021-12-01",
    end: Annotated[str | None, typer.Option(help="last day, default: 3 days ago")] = None,
    gdelt: Annotated[bool, typer.Option(help="also pull GDELT timelines (slow: one request per 6 s)")] = True,
) -> None:
    """Download the histories the study needs: Fear & Greed, Wikipedia pageviews, Binance metrics archive, GDELT.

    Resumable: cached days/chunks are skipped, days that keep failing are reported and retried by the next run.
    """
    from trader.intel import history, study

    first = date.fromisoformat(start)
    last = date.fromisoformat(end) if end else datetime.now(UTC).date() - timedelta(days=3)
    out = asyncio.run(history.backfill_series(wiki_start=first.strftime("%Y%m%d")))
    metrics = asyncio.run(history.backfill_metrics(metrics_symbols or study.UNIVERSE, first, last))
    if gdelt:
        out["gdelt"] = asyncio.run(history.backfill_gdelt(datetime.combine(first, datetime.min.time(), UTC), datetime.now(UTC).replace(minute=0, second=0, microsecond=0)))
    out["metrics"] = {s: {"rows": m["rows"], "failed_days": len(m.get("failed_days", [])), **({"error": m["error"]} if "error" in m else {})} for s, m in metrics.items()}
    out["metrics_failed_days"] = {s: m["failed_days"] for s, m in metrics.items() if m.get("failed_days")}
    _print(out)


@app.command()
def retag() -> None:
    """Re-run rule tagging + entity linking on every stored item and rebuild all hourly signals."""
    from trader.core.db import engine
    from trader.intel import analyze, signals
    from trader.intel.entities import default_linker
    from trader.models import NewsItem

    linker = default_linker()
    with Session(engine) as session:
        items = list(session.exec(select(NewsItem)).all())
        n = analyze.tag_items(session, items, linker, force=True)
        first = min(i.published_at for i in items) if items else datetime.now(UTC)
        rows = signals.compute(session, first, datetime.now(UTC) + timedelta(hours=1), linker)
    _print({"tagged": n, "signal_rows": rows})


@app.command("study")
def study_cmd() -> None:
    """Out-of-sample predictive-power study of the signals with real history → reports/intel_study.{md,json}."""
    from trader.intel import study

    doc = study.run()
    _print({"report": str(study.report_path()), "verdicts": doc["verdicts"]})
