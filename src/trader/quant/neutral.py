import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from itertools import product

import numpy as np
import pandas as pd

from trader.core.config import settings
from trader.quant import model, trend
from trader.quant.trend import COST, DAY, DEV_END, DEV_START, END, Panel, stats

HOUR = 3_600_000


@dataclass(frozen=True)
class Book:
    k: int = 10
    hold_days: int = 1
    gross: float = 2.0
    score: str = "edge"
    weighting: str = "equal"

    def describe(self) -> str:
        return f"long top {self.k} / short bottom {self.k} by {self.score}, hold {self.hold_days}d, gross {self.gross:g}x, {self.weighting} weights"


def _xrank(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.rank(axis=1, pct=True)


def all_scores(p: Panel, preds: pd.DataFrame) -> dict[str, pd.DataFrame]:
    base = daily_scores(preds, 23)
    hours = [_xrank(daily_scores(preds, h)["edge"]) for h in (5, 11, 17, 23)]
    multi = sum(x.fillna(0.5) for x in hours) / len(hours)
    multi = multi.where(hours[-1].notna())
    mom30 = _xrank((p.c / p.c.shift(30) - 1).reindex(index=base["edge"].index, columns=base["edge"].columns))
    edge = _xrank(base["edge"])
    return {
        "edge": base["edge"],
        "edge_multi": multi,
        "edge+mom30": (edge + mom30.fillna(0.5)).where(edge.notna()) / 2,
        "edge_multi+mom30": (multi + mom30.fillna(0.5)).where(multi.notna()) / 2,
        "mom30": mom30.where(edge.notna()),
    }


def daily_scores(preds: pd.DataFrame, at_hour: int = 23) -> dict[str, pd.DataFrame]:
    dec = preds[(preds.open_time % DAY) == at_hour * HOUR]
    day = (dec.open_time // DAY * DAY).to_numpy()
    frame = pd.DataFrame({"day": day, "symbol": dec.symbol.astype(str).to_numpy(), "long": dec.pred_long.to_numpy(), "short": dec.pred_short.to_numpy()})
    wide = {k: frame.pivot_table(index="day", columns="symbol", values=k, aggfunc="last") for k in ("long", "short")}
    return {"edge": wide["long"] - wide["short"], "long": wide["long"], "anti_short": -wide["short"]}


def cross_ic(score: pd.DataFrame, r_next: pd.DataFrame) -> pd.Series:
    s, r = score.align(r_next, join="inner")
    return s.rank(axis=1).corrwith(r.rank(axis=1), axis=1, method="pearson").dropna()


def book_weights(p: Panel, score: pd.DataFrame, book: Book) -> pd.DataFrame:
    score = score.reindex(index=p.c.index, columns=p.c.columns)
    valid = score.notna() & p.c.notna()
    s = score.where(valid)
    n = s.notna().sum(axis=1)
    enough = (n >= 2 * book.k).to_numpy()[:, None]
    longs = (s.rank(axis=1, ascending=False) <= book.k) & enough
    shorts = (s.rank(axis=1, ascending=True) <= book.k) & enough
    if book.weighting == "inverse_vol":
        inv = 1.0 / p.r.rolling(30, min_periods=20).std().clip(lower=0.01)
        wl = inv.where(longs).div(inv.where(longs).sum(axis=1), axis=0).fillna(0.0)
        ws = inv.where(shorts).div(inv.where(shorts).sum(axis=1), axis=0).fillna(0.0)
    else:
        wl = longs.astype(float).div(longs.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)
        ws = shorts.astype(float).div(shorts.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)
    w = (wl - ws) * (book.gross / 2)
    return w.rolling(book.hold_days, min_periods=1).mean() if book.hold_days > 1 else w


def weights_returns(p: Panel, w: pd.DataFrame) -> pd.Series:
    r_next = p.r.shift(-1).fillna(0.0)
    pnl = (w * r_next).sum(axis=1)
    turnover = (w - w.shift(1).fillna(0.0)).abs().sum(axis=1)
    funding = (w * p.funding.shift(-1).fillna(0.0)).sum(axis=1)
    return (pnl - COST * turnover - funding).shift(1).fillna(0.0)


def book_returns(p: Panel, score: pd.DataFrame, book: Book) -> pd.Series:
    return weights_returns(p, book_weights(p, score, book))


ENSEMBLE = {"family": "edge", "k": (5, 10, 20), "hold_days": (5, 7, 10, 14), "weighting": ("equal", "inverse_vol"), "gross": 2.0}


def ensemble_weights(p: Panel, scores: dict[str, pd.DataFrame], config: dict = ENSEMBLE) -> pd.DataFrame:
    books = [Book(k, h, config["gross"], config["family"], wt) for k, h, wt in product(config["k"], config["hold_days"], config["weighting"])]
    return sum(book_weights(p, scores[config["family"]], b) for b in books) / len(books)


def day_view(day_ms: int, capital: float = 1000.0, config: dict = ENSEMBLE) -> dict:
    p = trend.load_panel()
    scores = all_scores(p, pd.read_parquet(model.root() / "predictions.parquet"))
    w = ensemble_weights(p, scores, config)
    if day_ms - DAY not in w.index or day_ms not in p.r.index:
        raise ValueError("this day is outside the out-of-sample prediction range (2023-07-01 … 2026-09-30)")
    held, before = w.loc[day_ms - DAY], w.loc[day_ms - 2 * DAY] if day_ms - 2 * DAY in w.index else w.loc[day_ms - DAY] * 0
    r = p.r.loc[day_ms].fillna(0.0)
    funding = p.funding.loc[day_ms].fillna(0.0)
    open_pos = held[held.abs() > 1e-9].sort_values()
    rows = [
        {
            "symbol": s,
            "side": "LONG" if wgt > 0 else "SHORT",
            "weight_pct": round(100 * float(wgt), 2),
            "notional": round(capital * abs(float(wgt)), 2),
            "day_return_pct": round(100 * float(r[s]), 2),
            "pnl": round(capital * float(wgt * r[s] - wgt * funding[s]), 2),
        }
        for s, wgt in open_pos.items()
    ]
    cost = capital * COST * float((held - before).abs().sum())
    pnl = sum(x["pnl"] for x in rows) - cost
    return {
        "day": datetime.fromtimestamp(day_ms / 1000, UTC).strftime("%Y-%m-%d"),
        "book": f"market-neutral ensemble of {len(config['k']) * len(config['hold_days']) * len(config['weighting'])} books ({config['family']} score, gross {config['gross']:g}x)",
        "positions": len(rows),
        "longs": sum(x["side"] == "LONG" for x in rows),
        "shorts": sum(x["side"] == "SHORT" for x in rows),
        "gross_exposure_pct": round(100 * float(held.abs().sum()), 1),
        "net_exposure_pct": round(100 * float(held.sum()), 1),
        "rebalance_cost": round(cost, 2),
        "pnl": round(pnl, 2),
        "return_pct": round(100 * pnl / capital, 3),
        "table": rows,
    }


def study() -> dict:
    p = trend.load_panel()
    preds = pd.read_parquet(model.root() / "predictions.parquet")
    scores = all_scores(p, preds)
    r_next = p.r.shift(-1)
    doc: dict = {"ic": {}, "books": []}
    for name, sc in scores.items():
        ic = cross_ic(sc, r_next)
        dev, hold = ic[(ic.index >= DEV_START) & (ic.index < DEV_END)], ic[ic.index >= DEV_END]
        doc["ic"][name] = {
            "dev_mean": round(float(dev.mean()), 4),
            "dev_t": round(float(dev.mean() / dev.std() * np.sqrt(len(dev))), 2),
            "holdout_mean": round(float(hold.mean()), 4),
            "holdout_t": round(float(hold.mean() / hold.std() * np.sqrt(len(hold))), 2),
            "days": len(ic),
        }
    for (name, sc), k, hold_days, gross, weighting in product(scores.items(), (5, 10, 20), (5, 7, 10, 14), (2.0,), ("equal", "inverse_vol")):
        book = Book(k, hold_days, gross, name, weighting)
        ret = book_returns(p, sc, book)
        doc["books"].append({"book": book.describe(), **asdict(book), "dev": stats(ret, DEV_START, DEV_END), "holdout": stats(ret, DEV_END, END)})
    best = max(doc["books"], key=lambda b: b["dev"].get("sharpe", -9))
    doc["best_on_dev"] = best
    chosen = Book(best["k"], best["hold_days"], best["gross"], best["score"], best["weighting"])
    doc["leverage"] = []
    for gross in (2.0, 4.0, 6.0, 8.0):
        ret = book_returns(p, scores[chosen.score], Book(chosen.k, chosen.hold_days, gross, chosen.score, chosen.weighting))
        doc["leverage"].append({"gross": gross, "dev": stats(ret, DEV_START, DEV_END), "holdout": stats(ret, DEV_END, END)})
    (model.root() / "book.json").write_text(json.dumps(asdict(chosen), indent=2))
    doc["holdout_share_positive"] = round(float(np.mean([b["holdout"].get("return_pct", 0) > 0 for b in doc["books"]])), 3)
    out = settings.reports_dir / "quant"
    out.mkdir(parents=True, exist_ok=True)
    (out / "neutral.json").write_text(json.dumps(doc, indent=2, default=str))
    return doc
