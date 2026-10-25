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


def blend(xs7: pd.DataFrame, edge: pd.DataFrame) -> pd.DataFrame:
    edge = edge.reindex(index=xs7.index, columns=xs7.columns)
    return (xs7.rank(axis=1, pct=True) + edge.rank(axis=1, pct=True)) / 2


def all_scores(p: Panel, preds: pd.DataFrame) -> dict[str, pd.DataFrame]:
    base = daily_scores(preds, 23)
    hours = [_xrank(daily_scores(preds, h)["edge"]) for h in (5, 11, 17, 23)]
    multi = sum(x.fillna(0.5) for x in hours) / len(hours)
    multi = multi.where(hours[-1].notna())
    mom30 = _xrank((p.c / p.c.shift(30) - 1).reindex(index=base["edge"].index, columns=base["edge"].columns))
    edge = _xrank(base["edge"])
    xs_path = model.root() / "xs_predictions.parquet"
    extra = {}
    if xs_path.exists():
        xs = pd.read_parquet(xs_path)
        xs7 = xs.pivot_table(index=(xs.open_time // DAY * DAY), columns="symbol", values="score", aggfunc="last")
        extra = {"xs7": xs7, "blend": blend(xs7, base["edge"])}
    return extra | {
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


def weights_returns(p: Panel, w: pd.DataFrame, stop: float | None = None) -> pd.Series:
    r_next = p.r.shift(-1).fillna(0.0)
    stopped = pd.DataFrame(False, index=w.index, columns=w.columns)
    if stop:
        base = p.c
        gap = (p.o.shift(-1) / base - 1).fillna(0.0)
        up = (p.h.shift(-1) / base - 1).fillna(0.0)
        down = (p.low.shift(-1) / base - 1).fillna(0.0)
        long_hit, short_hit = (w > 0) & (down <= -stop), (w < 0) & (up >= stop)
        r_next = r_next.mask(long_hit, np.minimum(gap, -stop)).mask(short_hit, np.maximum(gap, stop))
        stopped = long_hit | short_hit
    pnl = (w * r_next).sum(axis=1)
    turnover = (w - w.shift(1).fillna(0.0)).abs().sum(axis=1) + 2 * w.abs().where(stopped, 0.0).sum(axis=1)
    funding = (w * p.funding.shift(-1).fillna(0.0)).sum(axis=1)
    return (pnl - COST * turnover - funding).shift(1).fillna(0.0)


def book_returns(p: Panel, score: pd.DataFrame, book: Book) -> pd.Series:
    return weights_returns(p, book_weights(p, score, book))


ENSEMBLE = {
    "family": "blend",
    "k": (5, 10, 20),
    "hold_days": (5, 7, 10, 14),
    "weighting": ("equal", "inverse_vol"),
    "gross": 2.0,
    "per_side": 30,
    "short_cap": 0.04,
    "beta_days": 60,
    "band": 0.01,
}


def ensemble_weights(p: Panel, scores: dict[str, pd.DataFrame], config: dict = ENSEMBLE) -> pd.DataFrame:
    books = [Book(k, h, config["gross"], config["family"], wt) for k, h, wt in product(config["k"], config["hold_days"], config["weighting"])]
    w = sum(book_weights(p, scores[config["family"]], b) for b in books) / len(books)
    return compress(w, config["per_side"]) if config.get("per_side") else w


def beta_hedge(p: Panel, w: pd.DataFrame, lookback: int = 60, hedge: str = "BTCUSDT") -> pd.DataFrame:
    """Offset the book's market beta with the hedge perpetual so the whole book has zero beta to it."""
    rb = p.r[hedge]
    beta = p.r.rolling(lookback, min_periods=lookback // 2).cov(rb).div(rb.rolling(lookback, min_periods=lookback // 2).var(), axis=0)
    beta = beta.clip(-1.0, 4.0).fillna(1.0)
    net = (w * beta.reindex(index=w.index, columns=w.columns).fillna(1.0)).sum(axis=1)
    out = w.copy()
    out[hedge] = out.get(hedge, 0.0) - net
    return out


def vol_target(p: Panel, w: pd.DataFrame, target: float, lookback: int = 30, lo: float = 0.25, hi: float = 2.0) -> pd.DataFrame:
    """Scale the whole book so its trailing realized daily volatility sits near `target`."""
    raw = weights_returns(p, w)
    realized = raw.rolling(lookback, min_periods=lookback // 2).std()
    scale = (target / realized).clip(lo, hi).fillna(1.0)
    return w.mul(scale.reindex(w.index).fillna(1.0), axis=0)


def banded(w: pd.DataFrame, band: float) -> pd.DataFrame:
    """Trade a position only when its target drifts more than `band` from what is held; names that leave the book are closed."""
    target = w.to_numpy()
    out = np.zeros_like(target)
    held = np.zeros(target.shape[1])
    for i, row in enumerate(target):
        row = np.nan_to_num(row)
        held = np.where(np.abs(row - held) > band, row, held)
        held = np.where(row == 0.0, 0.0, held)
        out[i] = held
    return pd.DataFrame(out, index=w.index, columns=w.columns)


def compress(w: pd.DataFrame, per_side: int) -> pd.DataFrame:
    """Keep the `per_side` largest longs and shorts of a book, resized so each side keeps its gross."""
    longs = w.where(w > 0)
    shorts = w.where(w < 0)
    keep_l = longs.where(longs.rank(axis=1, ascending=False) <= per_side).fillna(0.0)
    keep_s = shorts.where(shorts.rank(axis=1, ascending=True) <= per_side).fillna(0.0)
    scale_l = (longs.sum(axis=1) / keep_l.sum(axis=1).replace(0, np.nan)).fillna(0.0)
    scale_s = (shorts.sum(axis=1) / keep_s.sum(axis=1).replace(0, np.nan)).fillna(0.0)
    return keep_l.mul(scale_l, axis=0) + keep_s.mul(scale_s, axis=0)


def production_weights(p: Panel, scores: dict[str, pd.DataFrame], config: dict = ENSEMBLE, band: bool = True) -> pd.DataFrame:
    """The book the bot trades: ensemble → 30 per side → shorts capped → beta-hedged with BTC → traded only past the band."""
    w = ensemble_weights(p, scores, config)
    if config.get("short_cap"):
        w = w.clip(lower=-config["short_cap"])
    if config.get("beta_days") and "BTCUSDT" in p.r.columns:
        w = beta_hedge(p, w, config["beta_days"])
    if band and config.get("band"):
        w = banded(w, config["band"])
    return w


def day_view(day_ms: int, capital: float = 1000.0, config: dict = ENSEMBLE) -> dict:
    p = trend.load_panel()
    scores = all_scores(p, pd.read_parquet(model.root() / "predictions.parquet"))
    w = production_weights(p, scores, config)
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
