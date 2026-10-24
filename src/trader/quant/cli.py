import asyncio
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
    when: Annotated[str, typer.Argument(help="UTC day, YYYY-MM-DD")] = "",
    csv: Annotated[Path | None, typer.Option(help="your own quotes: CSV with time + open/high/low/close[/volume]")] = None,
    theta: Annotated[float | None, typer.Option(help="override the entry threshold (expected R)")] = None,
) -> None:
    """Feed one day of quotes to the bot and see every decision, trade and the P&L at once."""
    from trader.quant import day as day_replay

    target = datetime.fromisoformat(when).replace(tzinfo=UTC) if when else None
    doc = asyncio.run(asyncio.to_thread(day_replay.replay, symbol.upper(), target, csv, theta))
    _show({k: doc[k] for k in ("symbol", "day", "model", "policy", "summary", "report", "chart")})


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
