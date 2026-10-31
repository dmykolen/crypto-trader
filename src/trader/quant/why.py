import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from trader.core.config import settings
from trader.quant import features, live, model, neutral, paper, xsmodel
from trader.quant.trend import DAY

GROUPS = (
    ("btc", ("btc_", "resid_")),
    ("funding", ("funding", "to_funding")),
    ("volume", ("volume", "taker", "vwap", "obv", "qv", "amihud", "liquidity", "cmf")),
    ("volatility", ("atr", "rv_", "parkinson", "garman", "bb_width", "bb_squeeze", "lvl_width", "kurt_", "skew_", "vol_of_vol")),
    ("patterns", ("zz_", "cdl_", "lvl_")),
    ("overbought", ("rsi", "stoch", "williams", "cci", "mfi", "bb_pctb", "keltner", "z_")),
    ("momentum", ("mom_", "ret_", "macd", "tsi", "runup_", "drawdown_", "ffd")),
    ("trend", ("ema", "supertrend", "psar", "ichi", "kalman", "trend_", "adx", "di_", "aroon", "donchian", "heikin")),
    ("regime", ("ac1_", "hurst", "var_ratio", "ou_half_life", "perm_entropy")),
    ("time", ("hour", "dow")),
)


def group(feature: str) -> str:
    return next((g for g, prefixes in GROUPS if feature.startswith(prefixes)), "other")


def root() -> Path:
    return settings.data_dir / "quant" / "paper" / "why"


def rebalance(day: str) -> dict:
    history = json.loads(paper.ledger_path().read_text())["history"] if paper.ledger_path().exists() else []
    row = next((h for h in history if h["day"] == day), None)
    if row is None:
        raise LookupError(f"the virtual account has no rebalance on {day}")
    return row


def _midnight(at: datetime) -> datetime:
    return datetime(at.year, at.month, at.day, tzinfo=UTC)


def bars_path(at: datetime) -> Path:
    return settings.data_dir / "quant" / "live" / f"bars_{_midnight(at) - timedelta(days=62):%Y%m%d%H}_{at:%Y%m%d%H}.parquet"


def build(day: str) -> pd.DataFrame:
    cached = root() / f"{day}.parquet"
    if cached.exists():
        return pd.read_parquet(cached)
    at = datetime.fromisoformat(rebalance(day)["rebalanced_at"])
    if not bars_path(at).exists():
        raise FileNotFoundError(f"the quotes the bot used on {day} were not kept")
    today = _midnight(at)
    bars = live.collect(today - timedelta(days=62), at)
    raw = live.scores(bars, live._ms(today))
    edge = neutral.daily_scores(raw, live.DECISION_HOUR)["edge"]
    xs7 = raw.pivot_table(index=(raw.open_time // DAY * DAY), columns="symbol", values="xs", aggfunc="last")
    blend = neutral.blend(xs7, edge)
    weights = neutral.production_weights(live.panel(bars), {"blend": blend, "edge": edge})
    parts = []
    for d in blend.index[blend.index < live._ms(today)][-14:]:
        b = blend.loc[d].dropna()
        parts.append(
            pd.DataFrame({
                "decided": d,
                "symbol": b.index,
                "blend": b.to_numpy(),
                "rank": b.rank(ascending=False, method="min").to_numpy(),
                "of": len(b),
                "edge": edge.loc[d].reindex(b.index).to_numpy(),
                "xs": xs7.loc[d].reindex(b.index).to_numpy(),
                "weight": weights.loc[d].reindex(b.index).fillna(0.0).to_numpy() if d in weights.index else 0.0,
            })
        )
    out = pd.concat(parts, ignore_index=True)
    root().mkdir(parents=True, exist_ok=True)
    out.to_parquet(cached, index=False)
    return out


def factors(symbol: str, at: datetime, spread: tuple[float, float]) -> list[dict]:
    frame = pd.read_parquet(bars_path(at), filters=[("symbol", "in", [symbol, "BTCUSDT"])])
    split = {s: g.drop(columns="symbol").sort_values("open_time").reset_index(drop=True) for s, g in frame.groupby("symbol")}
    if symbol not in split:
        return []
    f = features.frame(split[symbol], split.get("BTCUSDT"))
    decided = live._ms(_midnight(at)) - DAY + live.DECISION_HOUR * live.HOUR
    if decided not in f.index:
        return []
    long_m, short_m, _, _ = model.model_for(live._ms(_midnight(at)))
    xs_m = xsmodel.model_for(live._ms(_midnight(at)))
    x = f.reindex(columns=long_m.feature_name()).loc[[decided]]
    xx = f.reindex(columns=xs_m.feature_name()).loc[[decided]]
    edge = pd.Series(long_m.predict(x, pred_contrib=True)[0][:-1] - short_m.predict(x, pred_contrib=True)[0][:-1], index=long_m.feature_name())
    xs = pd.Series(xs_m.predict(xx, pred_contrib=True)[0][:-1], index=xs_m.feature_name())
    push = edge.div(spread[0] or 1.0).add(xs.div(spread[1] or 1.0), fill_value=0.0) / 2
    out = []
    for g, part in push.groupby(push.index.map(group)):
        top = part.reindex(part.abs().sort_values(ascending=False).index[:3])
        out.append({"group": g, "value": round(float(part.sum()), 4), "top": [{"feature": k, "value": round(float(v), 4)} for k, v in top.items()]})
    return sorted(out, key=lambda r: -abs(r["value"]))


def _iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, UTC).isoformat(timespec="seconds")


def explain(symbol: str, day: str) -> dict:
    table = build(day)
    at = datetime.fromisoformat(rebalance(day)["rebalanced_at"])
    last_day = int(table.decided.max())
    last = table[table.decided == last_day]
    me = last[last.symbol == symbol]
    mine = table[table.symbol == symbol].sort_values("decided")

    def pct(col: str) -> float | None:
        return None if me.empty else round(float((last[col] < float(me[col].iat[0])).mean()), 3)

    return {
        "symbol": symbol,
        "day": day,
        "source": "reproduced",
        "rebalanced_at": at.isoformat(timespec="seconds"),
        "decided_at": _iso(last_day + live.DECISION_HOUR * live.HOUR),
        "of": int(last["of"].iat[0]),
        "rank": None if me.empty else int(me["rank"].iat[0]),
        "weight": 0.0 if me.empty else round(float(me["weight"].iat[0]), 6),
        "edge_pct": pct("edge"),
        "xs_pct": pct("xs"),
        "history": [{"day": _iso(int(r.decided)), "rank": int(r.rank), "of": int(r.of), "weight": round(float(r.weight), 6)} for r in mine.itertuples(index=False)],
        "factors": [] if me.empty else factors(symbol, at, (float(np.nanstd(last["edge"])), float(np.nanstd(last["xs"])))),
    }


def ranks(day: str) -> dict[str, dict]:
    table = build(day)
    last = table[table.decided == table.decided.max()]
    return {s: {"rank": int(r), "of": int(o)} for s, r, o in zip(last.symbol, last["rank"], last["of"], strict=True)}
