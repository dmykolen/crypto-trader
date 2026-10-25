import json
import logging
import shutil
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import pandas as pd
import pyarrow.parquet as pq

from trader.integrations import binance
from trader.quant import model, trend, xsmodel
from trader.services import market_data, universe

log = logging.getLogger(__name__)
HOUR = 3_600_000
FIRST_CUTOFF = int(datetime(2026, 10, 1, tzinfo=UTC).timestamp() * 1000)


def _month(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, UTC).strftime("%Y-%m")


def extend_symbol(symbol: str, interval: str = "1h", first: str = "2022-01") -> int:
    """Append the archive months newer than what is stored for one perpetual (a new listing comes whole); returns the bars added."""
    path = universe._root(interval) / f"{symbol}.parquet"
    have = pd.read_parquet(path) if path.exists() else None
    after = _month(int(have.open_time.max())) if have is not None and len(have) else None
    months = [m for m in binance.archive_months(symbol, interval) if m >= first and (after is None or m > after)]
    frames = [d for m in months if (d := binance.archive_klines(symbol, interval, m)) is not None]
    if not frames:
        return 0
    bars = market_data._normalize(pd.concat(frames, ignore_index=True))
    rates = [d for m in months if (d := binance.archive_funding(symbol, m)) is not None]
    funding = market_data._normalize_funding(pd.concat(rates, ignore_index=True) if rates else None)
    bars["funding"] = market_data.funding_per_bar(bars.open_time.to_numpy(), binance.INTERVAL_MS[interval], funding)
    merged = bars[universe.COLUMNS] if have is None else pd.concat([have, bars[universe.COLUMNS]], ignore_index=True)
    merged = merged.drop_duplicates("open_time", keep="last").sort_values("open_time", ignore_index=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    merged.to_parquet(path, index=False)
    return len(merged) - (0 if have is None else len(have))


def update_universe(interval: str = "1h", workers: int = 16) -> dict:
    def safe(symbol: str) -> tuple[str, int]:
        try:
            return symbol, extend_symbol(symbol, interval)
        except Exception as exc:
            log.warning("universe update %s failed: %s", symbol, exc)
            return symbol, -1

    with ThreadPoolExecutor(workers) as pool:
        result = dict(pool.map(safe, universe.usdt_perps()))
    return {
        "symbols": len(result),
        "extended": sum(v > 0 for v in result.values()),
        "new_bars": sum(v for v in result.values() if v > 0),
        "failed": sorted(k for k, v in result.items() if v < 0),
    }


def data_through() -> int | None:
    btc = universe._root("1h") / "BTCUSDT.parquet"
    if not btc.exists():
        return None
    return int(pq.read_table(btc, columns=["open_time"]).column(0).to_numpy().max()) + HOUR


def meta_path():
    return model.root() / "models_meta.json"


def meta() -> dict:
    return json.loads(meta_path().read_text()) if meta_path().exists() else {"data_through": FIRST_CUTOFF}


def archive_finals(cutoff: int) -> list[str]:
    """Keep the finals about to be replaced as the quarterly models for days from `cutoff` on, so later backtests never score a day with a model that saw it."""
    kept = []
    for folder, prefix in ((model.root() / "models", ("long", "short")), (model.root() / "xs_models", ("xs",))):
        for side in prefix:
            final = folder / f"{side}_final.txt"
            target = folder / f"{side}_{cutoff}.txt"
            if final.exists() and not target.exists():
                shutil.copy2(final, target)
                kept.append(target.name)
    return kept


def run(skip_download: bool = False) -> dict:
    started = datetime.now(UTC)
    steps: dict = {"archived": archive_finals(int(meta()["data_through"]))}
    if not skip_download:
        steps["universe"] = update_universe()
    trend.build_daily()
    steps["panel"] = model.build(model.geometry())
    model.train_final()
    steps["xs7"] = xsmodel.train_final()
    through = data_through()
    doc = {
        "trained_at": started.isoformat(timespec="seconds"),
        "finished_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "data_through": through,
        "data_through_utc": datetime.fromtimestamp(through / 1000, UTC).isoformat(timespec="minutes") if through else None,
        "steps": steps,
    }
    meta_path().write_text(json.dumps(doc, indent=2, default=str))
    return doc
