import json
import logging
from concurrent.futures import ThreadPoolExecutor

import lightgbm as lgb
import numpy as np
import pandas as pd

from trader.core.config import settings
from trader.quant import model, neutral, trend
from trader.quant.neutral import ENSEMBLE
from trader.quant.trend import DAY, DEV_END, DEV_START, END, stats

log = logging.getLogger(__name__)
HOUR = 3_600_000
DECISION_HOUR = 23
PARAMS = {
    "objective": "regression",
    "learning_rate": 0.03,
    "num_leaves": 15,
    "min_data_in_leaf": 1000,
    "feature_fraction": 0.5,
    "bagging_fraction": 0.7,
    "bagging_freq": 1,
    "lambda_l2": 10.0,
    "verbose": -1,
    "num_threads": 16,
}


def _rows(path, horizon_h: int) -> pd.DataFrame | None:
    df = pd.read_parquet(path)
    df = df[(df.open_time % DAY) == DECISION_HOUR * HOUR]
    if df.empty:
        return None
    bars = pd.read_parquet(model.root() / "bars" / path.name, columns=["open_time", "close"]).set_index("open_time").close
    now = bars.reindex(df.open_time.to_numpy()).to_numpy()
    later = bars.reindex(df.open_time.to_numpy() + horizon_h * HOUR).to_numpy()
    df = df.drop(columns=["y_long", "y_short"]).assign(fwd=np.log(later / now))
    return df[np.isfinite(df.fwd)]


SHARED = {"hour_sin", "hour_cos", "dow_sin", "dow_cos", "to_funding", "btc_ret_6", "btc_ret_24", "btc_ret_168", "btc_vol_24", "btc_vol_ratio", "btc_trend", "btc_rsi"}
NOT_FEATURES = {"open_time", "symbol", "fwd", "y", "pred_long", "pred_short", "xs"}


def cross_sectional(df: pd.DataFrame) -> pd.DataFrame:
    """Each per-symbol feature as its percentile among all symbols at the same decision time, plus the state of the market."""
    names = [c for c in df.columns if c not in NOT_FEATURES and c not in SHARED and not c.startswith(("xr_", "mkt_"))]
    t = df.open_time
    g = df.groupby(t)
    ranks = g[names].rank(pct=True).add_prefix("xr_")
    ctx = pd.DataFrame(
        {
            "mkt_breadth_24": (df.ret_24 > 0).groupby(t).transform("mean"),
            "mkt_breadth_168": (df.ret_168 > 0).groupby(t).transform("mean"),
            "mkt_disp_24": g.ret_24.transform("std"),
            "mkt_disp_168": g.ret_168.transform("std"),
            "mkt_median_24": g.ret_24.transform("median"),
            "mkt_median_168": g.ret_168.transform("median"),
            "mkt_funding": g.funding_24.transform("median"),
            "mkt_rv": g.rv_24.transform("median"),
        },
        index=df.index,
    )
    return pd.concat([df, ranks, ctx], axis=1)


def dataset(horizon_h: int = 168, version: str = "xs7") -> pd.DataFrame:
    paths = sorted((model.root() / "panel").glob("*.parquet"))
    with ThreadPoolExecutor(12) as pool:
        frames = [f for f in pool.map(lambda p: _rows(p, horizon_h), paths) if f is not None]
    df = pd.concat(frames, ignore_index=True)
    if version == "xs7r":
        df = cross_sectional(df)
    df["y"] = df.groupby("open_time").fwd.rank(pct=True) - 0.5
    df["symbol"] = df.symbol.astype("category")
    return df


def walk_forward(horizon_h: int = 168, version: str = "xs7", target: str = "rank", first: str = "2023-07-01", last_exclusive: str = "2026-10-01") -> pd.DataFrame:
    df = dataset(horizon_h, version)
    names = [c for c in df.columns if c not in NOT_FEATURES]
    params = PARAMS
    if target == "tails":
        df["y"] = np.where(df.y >= 0.3, 1.0, np.where(df.y <= -0.3, 0.0, np.nan))
        params = {**PARAMS, "objective": "binary"}
    labeled = df.y.notna().to_numpy()
    t = df.open_time.to_numpy()
    out = []
    folder = model.root() / ("xs_models" if version == "xs7" else f"{version}_models")
    folder.mkdir(parents=True, exist_ok=True)
    for lo, hi in model.quarters(first, last_exclusive):
        train = t + (horizon_h + 24) * HOUR < lo
        test = (t >= lo) & (t < hi)
        if not test.any() or train.sum() < 10_000:
            continue
        order = np.argsort(t[train], kind="stable")
        cut = t[train][order[int(len(order) * 0.85)]]
        fit_rows, valid_rows = train & (t < cut) & labeled, train & (t >= cut + (horizon_h + 24) * HOUR) & labeled
        booster = lgb.train(
            params,
            lgb.Dataset(df.loc[fit_rows, names], df.y[fit_rows]),
            1500,
            valid_sets=[lgb.Dataset(df.loc[valid_rows, names], df.y[valid_rows])],
            callbacks=[lgb.early_stopping(100, verbose=False)],
        )
        booster.save_model(str(folder / f"xs_{lo}.txt"))
        out.append(
            pd.DataFrame({"symbol": df.symbol[test].astype(str).to_numpy(), "open_time": t[test], "score": booster.predict(df.loc[test, names]), "fwd": df.fwd[test].to_numpy()})
        )
        log.warning("xs quarter %s: %d train rows, %d trees", pd.Timestamp(lo, unit="ms").date(), int(fit_rows.sum()), booster.best_iteration)
    preds = pd.concat(out, ignore_index=True)
    preds.to_parquet(model.root() / ("xs_predictions.parquet" if version == "xs7" else f"{version}_predictions.parquet"), index=False)
    full = df[labeled]
    booster = lgb.train(params, lgb.Dataset(full[names], full.y), max(50, booster.best_iteration))
    booster.save_model(str(folder / "xs_final.txt"))
    return preds


FINAL_TREES = 200


def train_final(horizon_h: int = 168, trees: int = FINAL_TREES) -> dict:
    df = dataset(horizon_h, "xs7")
    names = [c for c in df.columns if c not in NOT_FEATURES]
    folder = model.root() / "xs_models"
    folder.mkdir(parents=True, exist_ok=True)
    lgb.train(PARAMS, lgb.Dataset(df[names], df.y), trees).save_model(str(folder / "xs_final.txt"))
    return {"rows": len(df), "trees": trees}


def model_for(day_ms: int) -> lgb.Booster:
    """The 7-day model allowed to score `day_ms`: the latest quarterly model trained before it, the final one once it is 92 days past the last cutoff."""
    folder = model.root() / "xs_models"
    cutoffs = sorted(int(p.stem.split("_")[1]) for p in folder.glob("xs_*.txt") if p.stem.split("_")[1].isdigit())
    usable = [c for c in cutoffs if c <= day_ms]
    if (folder / "xs_final.txt").exists() and (not usable or day_ms >= cutoffs[-1] + 92 * 24 * HOUR):
        return lgb.Booster(model_file=str(folder / "xs_final.txt"))
    if not usable:
        raise FileNotFoundError("no 7-day model trained before this day; run `trader quant retrain` first")
    return lgb.Booster(model_file=str(folder / f"xs_{usable[-1]}.txt"))


def study(horizon_h: int = 168) -> dict:
    preds = walk_forward(horizon_h)
    p = trend.load_panel()
    score = preds.pivot_table(index=(preds.open_time // DAY * DAY), columns="symbol", values="score", aggfunc="last")
    ic = score.rank(axis=1).corrwith(p.r.shift(-1).reindex(index=score.index, columns=score.columns).rank(axis=1), axis=1).dropna()
    fwd = preds.pivot_table(index=(preds.open_time // DAY * DAY), columns="symbol", values="fwd", aggfunc="last")
    ic7 = score.rank(axis=1).corrwith(fwd.rank(axis=1), axis=1).dropna()
    doc = {
        "ic_next_day": {"dev": round(float(ic[ic.index < DEV_END].mean()), 4), "holdout": round(float(ic[ic.index >= DEV_END].mean()), 4)},
        "ic_7d": {
            "dev": round(float(ic7[ic7.index < DEV_END].mean()), 4),
            "holdout": round(float(ic7[ic7.index >= DEV_END].mean()), 4),
            "holdout_t": round(float(ic7[ic7.index >= DEV_END].mean() / ic7[ic7.index >= DEV_END].std() * np.sqrt(len(ic7[ic7.index >= DEV_END]) / 7)), 2),
        },
        "books": {},
    }
    for name, config in (("xs7 ensemble, 30/side", {**ENSEMBLE, "family": "xs7"}), ("xs7 ensemble, full", {**ENSEMBLE, "family": "xs7", "per_side": None})):
        w = neutral.ensemble_weights(p, {"xs7": score}, config)
        ret = neutral.weights_returns(p, w)
        doc["books"][name] = {"dev": stats(ret, DEV_START, DEV_END), "holdout": stats(ret, DEV_END, END)}
    edge = neutral.daily_scores(pd.read_parquet(model.root() / "predictions.parquet"), DECISION_HOUR)["edge"]
    blend = (score.rank(axis=1, pct=True) + edge.reindex(index=score.index, columns=score.columns).rank(axis=1, pct=True)) / 2
    w = neutral.ensemble_weights(p, {"blend": blend}, {**ENSEMBLE, "family": "blend"})
    ret = neutral.weights_returns(p, w)
    doc["books"]["xs7 + edge blend, 30/side"] = {"dev": stats(ret, DEV_START, DEV_END), "holdout": stats(ret, DEV_END, END)}
    (settings.reports_dir / "quant" / "xs7.json").write_text(json.dumps(doc, indent=2, default=str))
    return doc
