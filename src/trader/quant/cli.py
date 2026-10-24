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
