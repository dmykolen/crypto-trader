import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from trader.quant.labels import Geometry

quant = typer.Typer(no_args_is_help=True, help="Bot #2 «Квант»: indicators + math + chart patterns → LightGBM → leveraged futures trades.")
console = Console()


def _show(doc) -> None:
    console.print_json(json.dumps(doc, default=str))


@quant.command("build")
def build(
    min_volume: Annotated[float, typer.Option(help="min 30-day average daily quote volume, USDT")] = 10e6,
    sl: Annotated[float, typer.Option(help="stop, in ATRs")] = 1.5,
    tp: Annotated[float, typer.Option(help="take-profit, in ATRs")] = 3.0,
    horizon: Annotated[int, typer.Option(help="max hold, hours")] = 48,
) -> None:
    """Features (~135 per bar) and triple-barrier labels for every liquid USDT-M perpetual."""
    from trader.quant import model

    _show(model.build(Geometry(sl, tp, horizon), min_volume))


@quant.command("train")
def train() -> None:
    """Walk-forward LightGBM: one model per quarter, trained only on earlier data; then a final model on all data."""
    from trader.quant import model

    logging.getLogger("trader.quant.model").setLevel(logging.WARNING)
    preds = model.walk_forward()
    model.train_final()
    _show({"predictions": len(preds), "symbols": int(preds.symbol.nunique())})


@quant.command("evaluate")
def evaluate() -> None:
    """Calibration of the out-of-sample predictions, policy chosen on 2023-07…2024-12, verified on 2025-01…2026-09."""
    from trader.quant import research

    doc = research.evaluate()
    _show({"report": "reports/quant/research.md", "calibration": doc["calibration"], "chosen": {k: doc["chosen"][k] for k in ("describe", "dev", "holdout", "full_oos")}})


@quant.command("research")
def run_all(min_volume: Annotated[float, typer.Option()] = 10e6) -> None:
    """build → train → evaluate."""
    build(min_volume)
    train()
    evaluate()


@quant.command("day")
def day(
    symbol: Annotated[str, typer.Argument(help="e.g. SOLUSDT")],
    when: Annotated[str, typer.Argument(help="first UTC day, YYYY-MM-DD (default: yesterday)")] = "",
    days: Annotated[int, typer.Option(help="how many days from that day")] = 1,
    csv: Annotated[Path | None, typer.Option(help="your own quotes: CSV with time + open/high/low/close[/volume], 1h or finer")] = None,
    leverage: Annotated[float | None, typer.Option(help="leverage for every tactic (default: daily account swing ≈ 2 %, ≤ 5x)")] = None,
) -> None:
    """Feed one pair's quotes for a day (or several) and see at once what each of the 305 tactics and the market-neutral book did with it."""
    from trader.quant import day as lab

    target = datetime.fromisoformat(when).replace(tzinfo=UTC) if when else None
    doc = lab.run(symbol.upper(), target, days, csv, leverage)
    _show({k: doc[k] for k in ("symbol", "from", "to", "source", "leverage", "price_move_pct", "bot", "summary", "families", "book", "report")})
    for r in doc["tactics"][:10] + doc["tactics"][-5:]:
        rec = r["record"]
        console.print(f"{r['pnl']:+9.2f}$ {r['return_pct']:+7.2f}%  {r['key']:48} Sharpe dev {rec.get('dev')} holdout {rec.get('holdout')} untouched {rec.get('untouched')}")


@quant.command("tactics")
def tactic_study(workers: Annotated[int, typer.Option(help="parallel processes")] = 10) -> None:
    """Walk-forward per-token tactic selection over every liquid perp (2021-2026): 305 indicator, pattern and model tactics with stops, trailing and re-entry."""
    from trader.quant import tactic_study as study

    doc = study.study(workers)
    _show({k: doc[k] for k in ("tokens", "chosen_on_dev", "best_single_tactic_on_dev", "single_tactics_positive_share", "persistence")})


@quant.command("trend")
def trend_study() -> None:
    """Daily trend-following portfolios (momentum, EMA crosses, Donchian, SuperTrend, ensembles) on the most liquid perps, walk-forward."""
    from trader.quant import trend

    doc = trend.study()
    _show({k: doc[k] for k in ("symbols", "configs", "best_on_dev", "walk_forward_top1", "walk_forward_top3", "holdout_share_positive")})


@quant.command("neutral")
def neutral_study() -> None:
    """Market-neutral books from the model's ranking: long the best-ranked perps, short the worst, overlapping holds; chosen on 2023-07…2024-12."""
    from trader.quant import neutral

    doc = neutral.study()
    _show({k: doc[k] for k in ("ic", "best_on_dev", "leverage", "holdout_share_positive")})


@quant.command("book")
def book_day(when: Annotated[str, typer.Argument(help="UTC day, YYYY-MM-DD (2023-07-02 … 2026-09-30)")]) -> None:
    """The market-neutral book held on a day: every long and short, its weight, the day's move and the P&L on $1000."""
    from trader.quant import neutral

    doc = neutral.day_view(int(datetime.fromisoformat(when).replace(tzinfo=UTC).timestamp() * 1000))
    rows = doc.pop("table")
    _show(doc)
    for r in sorted(rows, key=lambda x: -abs(x["pnl"]))[:15]:
        console.print(f"{r['side']:5} {r['symbol']:16} weight {r['weight_pct']:+6.2f}%  day {r['day_return_pct']:+7.2f}%  P&L ${r['pnl']:+8.2f}")


@quant.command("forward")
def forward_test(
    start: Annotated[str, typer.Argument(help="first UTC day of the forward test, YYYY-MM-DD")] = "2026-10-01",
    end: Annotated[str, typer.Argument(help="last UTC day (default: yesterday)")] = "",
) -> None:
    """Forward test on days the models never saw: fresh 1h quotes of every liquid perp → features → final model → the market-neutral book, day by day."""
    from trader.quant import live

    first = datetime.fromisoformat(start).replace(tzinfo=UTC)
    last = datetime.fromisoformat(end).replace(tzinfo=UTC) if end else None
    doc = live.forward(first, last)
    _show({k: doc[k] for k in ("model", "symbols_scored", "period", "stats", "days")})
    console.print(f"book for {doc['book_for_next_day']['decided_at']}: {len(doc['book_for_next_day']['longs'])} longs, {len(doc['book_for_next_day']['shorts'])} shorts")


@quant.command("paper")
def paper_trade(
    loop: Annotated[bool, typer.Option(help="keep running: rebalance every day at 00:15 UTC")] = False,
    capital: Annotated[float, typer.Option(help="starting paper equity, USDT")] = 1000.0,
) -> None:
    """Paper-trade the market-neutral book: mark yesterday's positions to market, rebalance to today's book, log the equity."""
    from trader.quant import paper

    if loop:
        paper.loop(capital)
    else:
        _show(paper.step(capital))


@quant.command("limits", help="Shadow test of limit orders: each paper rebalance's orders priced as market orders and as post-only limits that wait 30 min.")
def limit_orders() -> None:
    from trader.quant import limit_test

    _show(limit_test.summary())


@quant.command("retrain")
def retrain_models(
    skip_download: Annotated[bool, typer.Option(help="reuse the stored quotes; only rebuild the panel and the models")] = False,
) -> None:
    """Quarterly refresh: new archive months for every perp → daily and feature panels → final models (the replaced ones are kept for the quarter they served)."""
    from trader.quant import retrain

    _show(retrain.run(skip_download))


@quant.command("live")
def live_trade(
    loop: Annotated[bool, typer.Option(help="keep running: rebalance every day at 00:15 UTC with REAL money")] = False,
    dry_run: Annotated[bool, typer.Option(help="show the orders today's book needs, place nothing")] = False,
) -> None:
    """Trade the market-neutral book with real money on Binance (needs TRADING_MODE=live and API keys); --dry-run only plans."""
    from trader.core.config import settings
    from trader.quant import live_exec

    if not dry_run and settings.trading_mode != "live":
        raise typer.BadParameter("real-money trading needs TRADING_MODE=live (the web UI sets it after your confirmation)")
    if loop:
        live_exec.loop()
    else:
        _show(live_exec.step(dry_run=dry_run))
