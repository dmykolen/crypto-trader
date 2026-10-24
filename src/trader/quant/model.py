import json
import logging
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

from trader.core.config import settings
from trader.quant import features, labels
from trader.quant.labels import Geometry

log = logging.getLogger(__name__)

FEE = 0.0005
SLIP = 0.0003
COST = 2 * (FEE + SLIP)
START = int(datetime(2022, 7, 1, tzinfo=UTC).timestamp() * 1000)
WARMUP = 500
HOUR = 3_600_000
MIN_ATR_PCT = 0.002
STABLES = ("USDC", "FDUSD", "TUSD", "BUSD", "USDP", "DAI", "EUR", "USDE", "PYUSD", "USD1", "XUSD", "AEUR")
BAR_COLUMNS = ["open_time", "open", "high", "low", "close", "atr", "funding", "eligible"]
PARAMS = {
    "objective": "huber",
    "alpha": 1.5,
    "learning_rate": 0.05,
    "num_leaves": 31,
    "min_data_in_leaf": 2000,
    "feature_fraction": 0.5,
    "bagging_fraction": 0.5,
    "bagging_freq": 1,
    "lambda_l2": 10.0,
    "verbose": -1,
    "num_threads": 16,
}


def root() -> Path:
    return settings.data_dir / "quant"


def universe_dir() -> Path:
    return settings.data_dir / "universe" / "1h"


def _btc() -> pd.DataFrame:
    return pd.read_parquet(universe_dir() / "BTCUSDT.parquet")


def build_symbol(symbol: str, geometry: Geometry, min_daily_volume: float) -> int:
    bars = pd.read_parquet(universe_dir() / f"{symbol}.parquet").sort_values("open_time", ignore_index=True)
    if len(bars) < WARMUP + geometry.horizon + 200:
        return 0
    f = features.frame(bars, _btc())
    o, h, low, c = (bars[k].to_numpy(np.float64) for k in ("open", "high", "low", "close"))
    a = f.atr_pct.to_numpy(np.float64) * c
    y_long, y_short = labels.triple_barrier(o, h, low, c, a, geometry.sl_atr, geometry.tp_atr, geometry.horizon, COST)
    daily = bars.quote_volume.rolling(720, min_periods=240).sum().to_numpy() / 30.0 * (720 / np.minimum(np.arange(1, len(bars) + 1), 720))
    t = bars.open_time.to_numpy(np.int64)
    live = np.isfinite(a) & (a / c >= MIN_ATR_PCT) & np.isfinite(y_long) & np.isfinite(y_short)
    stable = symbol.removesuffix("USDT") in STABLES
    eligible = (daily >= min_daily_volume) & (np.arange(len(bars)) >= WARMUP) & (t >= START) & live & (not stable)
    if eligible.sum() < 300:
        return 0
    keep = t >= START
    sim = pd.DataFrame({"open_time": t, "open": o, "high": h, "low": low, "close": c, "atr": a, "funding": bars.funding.fillna(0.0).to_numpy(), "eligible": eligible})[keep]
    rows = f.loc[t[eligible]].reset_index(names="open_time")
    rows["y_long"], rows["y_short"] = y_long[eligible].astype(np.float32), y_short[eligible].astype(np.float32)
    rows["symbol"] = symbol
    (root() / "bars").mkdir(parents=True, exist_ok=True)
    (root() / "panel").mkdir(parents=True, exist_ok=True)
    sim.to_parquet(root() / "bars" / f"{symbol}.parquet", index=False)
    rows.to_parquet(root() / "panel" / f"{symbol}.parquet", index=False)
    return int(eligible.sum())


def build(geometry: Geometry | None = None, min_daily_volume: float = 10e6, workers: int = 14) -> dict:
    geometry = geometry or Geometry()
    symbols = sorted(p.stem for p in universe_dir().glob("*.parquet"))
    for folder in ("panel", "bars"):
        for p in (root() / folder).glob("*.parquet"):
            p.unlink()
    with ProcessPoolExecutor(workers) as pool:
        counts = dict(zip(symbols, pool.map(build_symbol, symbols, [geometry] * len(symbols), [min_daily_volume] * len(symbols), chunksize=4), strict=True))
    used = {s: n for s, n in counts.items() if n}
    meta = {"geometry": asdict(geometry), "min_daily_volume": min_daily_volume, "symbols": len(used), "rows": int(sum(used.values())), "cost_round_trip": COST}
    (root() / "panel_meta.json").write_text(json.dumps(meta, indent=2))
    return meta


def geometry() -> Geometry:
    return Geometry(**json.loads((root() / "panel_meta.json").read_text())["geometry"])


def load_panel(columns: list[str] | None = None) -> pd.DataFrame:
    frames = [pd.read_parquet(p, columns=columns) for p in sorted((root() / "panel").glob("*.parquet"))]
    df = pd.concat(frames, ignore_index=True)
    df["symbol"] = df.symbol.astype("category")
    return df


def feature_names(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if c not in ("open_time", "symbol", "y_long", "y_short")]


def _fit(x: pd.DataFrame, y: np.ndarray, t: np.ndarray, rounds: int = 1000) -> lgb.Booster:
    order = np.argsort(t, kind="stable")
    cut = order[int(len(order) * 0.9)]
    valid = t >= t[cut]
    y = np.clip(y, -3.0, None)
    train_set = lgb.Dataset(x[~valid], y[~valid], free_raw_data=True)
    valid_set = lgb.Dataset(x[valid], y[valid], reference=train_set, free_raw_data=True)
    return lgb.train(PARAMS, train_set, rounds, valid_sets=[valid_set], callbacks=[lgb.early_stopping(100, verbose=False)])


def quarters(first: str = "2023-07-01", last_exclusive: str = "2026-10-01") -> list[tuple[int, int]]:
    edges = pd.date_range(first, last_exclusive, freq="QS", tz="UTC")
    return [(int(a.timestamp() * 1000), int(b.timestamp() * 1000)) for a, b in pairwise(edges)]


def walk_forward(sub: int = 4) -> pd.DataFrame:
    df = load_panel()
    names = feature_names(df)
    horizon = geometry().horizon
    (root() / "models").mkdir(parents=True, exist_ok=True)
    out = []
    for lo, hi in quarters():
        train = (df.open_time.to_numpy() + (horizon + 1) * HOUR < lo) & ((df.open_time.to_numpy() // HOUR) % sub == 0)
        test = (df.open_time.to_numpy() >= lo) & (df.open_time.to_numpy() < hi)
        if not test.any():
            continue
        x, t = df.loc[train, names], df.open_time.to_numpy()[train]
        preds = {"symbol": df.symbol[test].astype(str).to_numpy(), "open_time": df.open_time.to_numpy()[test]}
        for side in ("long", "short"):
            booster = _fit(x, df[f"y_{side}"].to_numpy()[train], t)
            booster.save_model(str(root() / "models" / f"{side}_{lo}.txt"))
            preds[f"pred_{side}"] = booster.predict(df.loc[test, names], num_threads=16).astype(np.float32)
            preds[f"y_{side}"] = df[f"y_{side}"].to_numpy()[test]
            log.warning("quarter %s %s: %d train rows, %d trees", datetime.fromtimestamp(lo / 1000, UTC).date(), side, int(train.sum()), booster.best_iteration)
        out.append(pd.DataFrame(preds))
    result = pd.concat(out, ignore_index=True)
    result.to_parquet(root() / "predictions.parquet", index=False)
    return result


def train_final(sub: int = 4) -> None:
    df = load_panel()
    names = feature_names(df)
    keep = (df.open_time.to_numpy() // HOUR) % sub == 0
    x, t = df.loc[keep, names], df.open_time.to_numpy()[keep]
    for side in ("long", "short"):
        _fit(x, df[f"y_{side}"].to_numpy()[keep], t).save_model(str(root() / "models" / f"{side}_final.txt"))


def model_for(day_ms: int) -> tuple[lgb.Booster, lgb.Booster, str, str]:
    folder = root() / "models"
    cutoffs = sorted(int(p.stem.split("_")[1]) for p in folder.glob("long_*.txt") if p.stem.split("_")[1].isdigit())
    usable = [c for c in cutoffs if c <= day_ms]
    final = (folder / "long_final.txt").exists()
    if final and (not usable or day_ms >= cutoffs[-1] + 92 * 24 * HOUR):
        tag = "final"
    elif usable:
        tag = str(usable[-1])
    else:
        raise FileNotFoundError("no model trained before this day; run `trader quant research` first")
    folder_tag = tag

    def load(side: str) -> lgb.Booster:
        return lgb.Booster(model_file=str(folder / f"{side}_{folder_tag}.txt"))

    label = "trained on all history" if tag == "final" else f"trained on data before {datetime.fromtimestamp(int(tag) / 1000, UTC).date()}"
    return load("long"), load("short"), label, tag
