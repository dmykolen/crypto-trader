import json
import zlib
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

from trader.core.config import settings
from trader.quant import model, tactics
from trader.quant.model import STABLES
from trader.quant.trend import DAY, DEV_END, DEV_START, END, _ms

VARIANTS = tuple((lookback, top, floor) for lookback in (90, 180, 365) for top in (1, 3) for floor in (0.0, 1.0))
TOPS = (10, 30, None)
TARGET_VOL, MAX_LEVERAGE, MIN_VOLUME = 0.02, 5.0, 10e6
SETS = {
    "main": {"first": _ms("2023-01-01"), "last": END, "periods": {"dev": (DEV_START, DEV_END), "holdout": (DEV_END, END)}},
    "pre": {
        "first": _ms("2021-01-01"),
        "last": _ms("2023-07-01"),
        "periods": {"untouched": (_ms("2021-07-01"), _ms("2023-07-01")), "h1": (_ms("2021-07-01"), _ms("2022-07-01")), "h2": (_ms("2022-07-01"), _ms("2023-07-01"))},
    },
}


def variant(lookback: int, top: int, floor: float) -> str:
    return f"L{lookback}_top{top}_min{floor:g}"


def quarters(first: int, last: int) -> list[int]:
    return [int(q.timestamp() * 1000) for q in pd.date_range(pd.Timestamp(first, unit="ms", tz="UTC"), pd.Timestamp(last - 1, unit="ms", tz="UTC"), freq="QS")]


def _sharpe(r):
    return r.mean() / r.std() * np.sqrt(365)


def _lev(r: pd.Series) -> float:
    s = float(r.std())
    return float(np.clip(TARGET_VOL / s, 0.0, MAX_LEVERAGE)) if s > 0 else 0.0


def edge(symbol: str, times: np.ndarray) -> np.ndarray:
    path = model.root() / "predictions.parquet"
    if not path.exists():
        return np.zeros(len(times))
    p = pd.read_parquet(path, columns=["open_time", "pred_long", "pred_short"], filters=[("symbol", "==", symbol)]).drop_duplicates("open_time").set_index("open_time")
    return (p.pred_long - p.pred_short).reindex(times).to_numpy(np.float64)


def token(symbol: str, data_dir: str, first: int, last: int, periods: dict) -> dict | None:
    settings.data_dir = Path(data_dir)
    bars = pd.read_parquet(model.universe_dir() / f"{symbol}.parquet")
    qv = bars.groupby(bars.open_time // DAY * DAY).quote_volume.sum()
    liquid = qv.rolling(30, min_periods=20).mean().shift(1) >= MIN_VOLUME
    qs = [q for q in quarters(first, last) if liquid.get(q, False)]
    if len(bars) < 24 * 200 or not qs:
        return None
    x = tactics.inputs(bars, pd.read_parquet(model.universe_dir() / "BTCUSDT.parquet"), edge(symbol, bars.open_time.to_numpy()))
    d = tactics.daily(x, tactics.catalog())
    names = [variant(*v) for v in VARIANTS]
    out = pd.DataFrame(np.nan, index=d.index, columns=[*names, "random", "ensemble"])
    scaled = pd.DataFrame(np.nan, index=d.index, columns=d.columns, dtype=np.float32)
    scores, picks = {}, []
    rng = np.random.default_rng(zlib.crc32(symbol.encode()))
    bounds = quarters(first, last)
    for q in qs:
        q_end = next((b for b in bounds if b > q), last)
        here = (d.index >= q) & (d.index < q_end)
        if not here.any():
            continue
        oos = d[here].fillna(0.0)
        for (lookback, top, floor), name in zip(VARIANTS, names, strict=True):
            past = d[(d.index >= q - lookback * DAY) & (d.index < q)]
            if len(past.dropna(how="all")) < 0.8 * lookback:
                continue
            s = _sharpe(past).dropna()
            best = s[s > floor].nlargest(top)
            out.loc[here, name] = _lev(past[best.index].mean(axis=1)) * oos[best.index].mean(axis=1) if len(best) else 0.0
            scores[f"{q}|{name}"] = float(best.mean()) if len(best) else None
            if (lookback, top, floor) == (180, 1, 0.0) and len(best):
                picks.append({"quarter": q, "tactic": best.index[0], "trailing_sharpe": round(float(best.iloc[0]), 2)})
        past = d[(d.index >= q - 180 * DAY) & (d.index < q)]
        valid = _sharpe(past).dropna().index
        if len(valid):
            pick = valid[rng.integers(len(valid))]
            out.loc[here, "random"] = _lev(past[pick]) * oos[pick]
            out.loc[here, "ensemble"] = _lev(past[valid].mean(axis=1)) * oos[valid].mean(axis=1)
        recent = d[(d.index >= q - 90 * DAY) & (d.index < q)]
        scaled.loc[here] = (oos * (TARGET_VOL / recent.std()).clip(0.0, MAX_LEVERAGE).fillna(0.0)).astype(np.float32)
    traded = out.notna().any(axis=1)
    sharpe = pd.DataFrame({k: _sharpe(d[(d.index >= lo) & (d.index < hi) & traded]) for k, (lo, hi) in periods.items()})
    return {"symbol": symbol, "out": out[traded], "scaled": scaled[traded], "scores": scores, "picks": picks, "sharpe": sharpe}


def _stats(r: pd.Series, lo: int, hi: int) -> dict:
    r = r[(r.index >= lo) & (r.index < hi)].fillna(0.0)
    if r.empty or r.std() == 0:
        return {}
    eq = (1 + r).cumprod()
    return {
        "return_pct": round(100 * float(eq.iloc[-1] - 1), 1),
        "sharpe": round(float(_sharpe(r)), 2),
        "max_drawdown_pct": round(100 * float((eq / eq.cummax() - 1).min()), 1),
        "worst_day_pct": round(100 * float(r.min()), 2),
        "days": len(r),
    }


def _top(results: list[dict], name: str, k: int | None) -> pd.Series:
    frame = pd.DataFrame({r["symbol"]: r["out"][name] for r in results}).sort_index()
    if k is None:
        return frame.mean(axis=1)
    score = pd.DataFrame({
        r["symbol"]: pd.Series({int(key.split("|")[0]): v for key, v in r["scores"].items() if key.endswith("|" + name)}, dtype=float) for r in results
    }).sort_index()
    keep = (score.rank(axis=1, ascending=False) <= k).reindex(columns=frame.columns, fill_value=False)
    at = np.searchsorted(score.index.to_numpy(), frame.index.to_numpy(), side="right") - 1
    mask = keep.to_numpy()[np.clip(at, 0, None)] & (at >= 0)[:, None]
    return frame.where(mask).mean(axis=1)


def persistence(results: list[dict], a: str, b: str) -> dict:
    s = pd.concat({r["symbol"]: r["sharpe"][[a, b]] for r in results}).dropna()
    s = s[np.isfinite(s).all(axis=1)]
    resid = {}
    for k in (a, b):
        x = s[k]
        x = x - x.groupby(level=1).transform("mean")
        resid[k] = x - x.groupby(level=0).transform("mean")
    ra, rb = resid[a], resid[b]
    hi = ra >= ra.quantile(0.8)
    return {
        "pairs": len(s),
        "tokens": int(s.index.get_level_values(0).nunique()),
        "raw_spearman": round(float(s[a].corr(s[b], method="spearman")), 3),
        "resid_pearson": round(float(ra.corr(rb)), 3),
        "resid_spearman": round(float(ra.corr(rb, method="spearman")), 3),
        "top_quintile_next_resid_sharpe": round(float(rb[hi].mean()), 3),
        "bottom_quintile_next_resid_sharpe": round(float(rb[ra <= ra.quantile(0.2)].mean()), 3),
    }


def run_set(key: str, workers: int = 10, report=print) -> tuple[list[dict], pd.DataFrame]:
    cfg = SETS[key]
    directory = str(settings.data_dir) + ("_pre" if key == "pre" else "")
    folder = Path(directory) / "universe" / "1h"
    symbols = [p.stem for p in sorted(folder.glob("*.parquet")) if p.stem.removesuffix("USDT") not in STABLES]
    results, total, count = [], None, None
    with ProcessPoolExecutor(workers) as pool:
        futures = [pool.submit(token, s, directory, cfg["first"], cfg["last"], cfg["periods"]) for s in symbols]
        for i, fut in enumerate(futures):
            r = fut.result()
            if r is None:
                continue
            sc = r.pop("scaled").astype(np.float64)
            total = sc.fillna(0.0) if total is None else total.add(sc.fillna(0.0), fill_value=0.0)
            count = sc.notna().astype(float) if count is None else count.add(sc.notna().astype(float), fill_value=0.0)
            results.append(r)
            if i % 50 == 0:
                report(f"{key}: {i}/{len(symbols)} tokens")
    return results, total / count.replace(0, np.nan)


def study(workers: int = 10, report=print) -> dict:
    names = [variant(*v) for v in VARIANTS] + ["random", "ensemble"]
    main, main_cfg = run_set("main", workers, report)
    pre, pre_cfg = run_set("pre", workers, report)
    pm, pp = SETS["main"]["periods"], SETS["pre"]["periods"]
    rows = []
    for name in names:
        for k in TOPS if name not in ("random", "ensemble") else (None,):
            sm, sp = _top(main, name, k), _top(pre, name, k)
            rows.append({"variant": name, "top_tokens": k or "all", **{p: _stats(sm, *pm[p]) for p in pm}, **{p: _stats(sp, *pp[p]) for p in pp}})
    dev_sharpe = {c: _stats(main_cfg[c], *pm["dev"]).get("sharpe", -9) for c in main_cfg.columns}
    best = max(dev_sharpe, key=dev_sharpe.get)
    per_config = sorted(
        (
            {
                "tactic": c,
                "dev": _stats(main_cfg[c], *pm["dev"]),
                "holdout": _stats(main_cfg[c], *pm["holdout"]),
                "untouched": _stats(pre_cfg[c], *pp["untouched"]) if c in pre_cfg else {},
            }
            for c in main_cfg.columns
        ),
        key=lambda r: -r["dev"].get("sharpe", -9),
    )
    chosen = max((r for r in rows if r["variant"] not in ("random", "ensemble")), key=lambda r: r["dev"].get("sharpe", -9))
    doc = {
        "tokens": {"main": len(main), "pre": len(pre)},
        "tactics": len(tactics.catalog()),
        "variants": rows,
        "chosen_on_dev": chosen,
        "random_same_tops": [r for r in rows if r["variant"] == "random"],
        "best_single_tactic_on_dev": next(r for r in per_config if r["tactic"] == best),
        "single_tactics_top20_by_dev": per_config[:20],
        "single_tactics_positive_share": {p: round(float(np.mean([r[p].get("sharpe", -9) > 0 for r in per_config])), 3) for p in ("dev", "holdout", "untouched")},
        "persistence": {"dev_to_holdout": persistence(main, "dev", "holdout"), "2021H2-22H1_to_2022H2-23H1": persistence(pre, "h1", "h2")},
        "picks_sample": {r["symbol"]: r["picks"] for r in main if r["symbol"] in ("BTCUSDT", "ETHUSDT", "SOLUSDT", "DOGEUSDT", "XRPUSDT")},
    }
    out = settings.reports_dir / "quant"
    out.mkdir(parents=True, exist_ok=True)
    (out / "tactics.json").write_text(json.dumps(doc, indent=1, default=str))
    store = model.root() / "tactics"
    store.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({
        f"{r['variant']}|{r['top_tokens']}": _top(main, r["variant"], None if r["top_tokens"] == "all" else r["top_tokens"]) for r in rows if r["top_tokens"] == "all"
    }).to_parquet(store / "main_streams.parquet")
    main_cfg.astype(np.float32).to_parquet(store / "main_configs.parquet")
    pre_cfg.astype(np.float32).to_parquet(store / "pre_configs.parquet")
    return doc
