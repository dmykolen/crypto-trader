import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from trader.core.config import settings
from trader.integrations import binance
from trader.quant import evidence, model, paper, tactics
from trader.quant.trend import DAY, DEV_END, DEV_START, END
from trader.quant.trend import _ms as _iso_ms
from trader.services import engine, market_data

HOUR = 3_600_000
HISTORY = timedelta(days=150)
TARGET_VOL, MAX_LEVERAGE = 0.02, 5.0
AUTO = "підібране: рахунок тактики має коливатися ≈ {target:g} % за день, а ціна за 30 днів до того ходила ≈ {vol:.2f} % за день; не більше {top:g}×"
SNAPSHOT = ("rsi_14", "adx", "atr_pct", "ema_dist_200", "bb_pctb", "supertrend", "zz_structure", "volume_z24", "funding_z", "btc_ret_24")
FAMILY = {
    "trend": ("ema_cross", "supertrend", "psar", "macd", "donchian", "kalman", "ichimoku", "adx_trend", "trend_vote", "heikin_ashi", "btc_follow", "hurst_switch"),
    "revert": ("rsi_revert", "bollinger_revert", "zscore_revert", "funding_fade", "residual_revert"),
    "ml": ("ml_edge",),
}
TIME_COLUMNS = ("open_time", "timestamp", "time", "date", "datetime", "open time", "ts")


def _ms(at: datetime) -> int:
    return int(at.timestamp() * 1000)


def _dt(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000, UTC)


def quotes(symbol: str, start: datetime, end: datetime) -> pd.DataFrame:
    bars = market_data.load_klines(symbol, start, end, "1h")
    if bars.empty:
        raise ValueError(f"no 1h quotes for {symbol} between {start:%Y-%m-%d} and {end:%Y-%m-%d}")
    bars = bars.sort_values("open_time", ignore_index=True)
    try:
        rates = binance.FuturesREST().funding(symbol, _ms(start), _ms(end))
    except Exception:
        rates = None
    bars["funding"] = market_data.funding_per_bar(bars.open_time.to_numpy(), HOUR, rates) if rates is not None and len(rates) else 0.0
    return bars


def _to_ms(column: pd.Series) -> np.ndarray:
    if pd.api.types.is_numeric_dtype(column):
        x = column.to_numpy(np.float64)
        scale = np.where(x > 1e14, 1e-3, np.where(x > 1e11, 1.0, 1e3))
        return (x * scale).astype(np.int64)
    return pd.to_datetime(column, utc=True).dt.as_unit("ms").astype("int64").to_numpy(np.int64)


def from_csv(path: Path) -> pd.DataFrame:
    raw = pd.read_csv(path)
    cols = {c.lower().strip(): c for c in raw.columns}
    tcol = next((cols[k] for k in TIME_COLUMNS if k in cols), raw.columns[0])
    df = pd.DataFrame({"open_time": _to_ms(raw[tcol])})
    for name in ("open", "high", "low", "close"):
        if name not in cols:
            raise ValueError(f"{path.name}: column '{name}' is missing (need time, open, high, low, close)")
        df[name] = pd.to_numeric(raw[cols[name]], errors="coerce")
    for name in ("volume", "quote_volume", "taker_buy_volume", "funding"):
        if name in cols:
            df[name] = pd.to_numeric(raw[cols[name]], errors="coerce")
    df = df.dropna(subset=["open", "high", "low", "close"]).sort_values("open_time").drop_duplicates("open_time", ignore_index=True)
    step = int(np.median(np.diff(df.open_time.to_numpy()))) if len(df) > 1 else HOUR
    if step > HOUR:
        raise ValueError(f"{path.name}: bars are {step / HOUR:g}h apart — the bot needs 1h or finer quotes")
    if step < HOUR:
        bucket = df.open_time // HOUR * HOUR
        agg = {"open": "first", "high": "max", "low": "min", "close": "last"} | {k: "sum" for k in ("volume", "quote_volume", "taker_buy_volume", "funding") if k in df}
        df = df.groupby(bucket).agg(agg).rename_axis("open_time").reset_index()
    if "volume" not in df:
        df["volume"] = 0.0
    return df


def _edge(f: pd.DataFrame) -> np.ndarray:
    out = np.full(len(f), np.nan)
    t = f.index.to_numpy(np.int64)
    starts = pd.to_datetime(t, unit="ms").to_period("Q").start_time.as_unit("ms").asi8
    for q in np.unique(starts):
        try:
            long_m, short_m, _, _ = model.model_for(int(q))
        except FileNotFoundError:
            continue
        rows = starts == q
        x = f.reindex(columns=long_m.feature_name())[rows]
        out[rows] = long_m.predict(x) - short_m.predict(x)
    return out


def family(rule: str) -> str:
    return next((k for k, rules in FAMILY.items() if rule in rules), "pattern")


def _record() -> dict[str, dict]:
    out: dict[str, dict] = {}
    store = model.root() / "tactics"
    for name, periods in (
        ("main_configs", {"dev": (DEV_START, DEV_END), "holdout": (DEV_END, END)}),
        ("pre_configs", {"untouched": (_iso_ms("2021-07-01"), _iso_ms("2023-07-01"))}),
    ):
        path = store / f"{name}.parquet"
        if not path.exists():
            continue
        frame = pd.read_parquet(path)
        for key, (lo, hi) in periods.items():
            r = frame[(frame.index >= lo) & (frame.index < hi)].fillna(0.0)
            sharpe = r.mean() / r.std().replace(0, np.nan) * np.sqrt(365)
            for tactic, v in sharpe.items():
                out.setdefault(tactic, {})[key] = None if pd.isna(v) else round(float(v), 2)
    return out


def _book(symbol: str, lo: int, hi: int) -> tuple[list[dict], bool]:
    held: dict[str, float] = {}
    known: set[str] = set()
    for path in (model.root() / "book_history.parquet", settings.data_dir / "quant" / "live" / "forward_book.parquet"):
        if path.exists():
            b = pd.read_parquet(path)
            b = b[(b.day >= lo) & (b.day < hi)]
            known |= {_dt(int(d)).strftime("%Y-%m-%d") for d in b.day.unique()}
            mine = b[b.symbol == symbol]
            held |= {_dt(int(d)).strftime("%Y-%m-%d"): round(float(w), 5) for d, w in zip(mine.day, mine.weight, strict=True)}
    ledger = paper.ledger_path()
    for h in json.loads(ledger.read_text())["history"] if ledger.exists() else []:
        if "book" in h and lo <= _iso_ms(h["day"]) < hi:
            known.add(h["day"])
            held |= {h["day"]: round(h["book"][symbol], 5)} if symbol in h["book"] else {}
    days = {_dt(lo + i * DAY).strftime("%Y-%m-%d") for i in range((hi - lo) // DAY)}
    return [{"day": d, "weight": w} for d, w in sorted(held.items())], days <= known


def _price(entry: float, side: int, ret: float, lev: float, fee: float) -> float:
    return entry * ((ret / lev + fee + 1) / (1 - fee) if side > 0 else (1 - fee - ret / lev) / (1 + fee))


def _bot(lo: int, hi: int) -> dict | None:
    first, last = _dt(lo).strftime("%Y-%m-%d"), _dt(hi).strftime("%Y-%m-%d")
    ledger = paper.ledger_path()
    paid = {h["day"]: h["equity"] for h in json.loads(ledger.read_text())["history"]} if ledger.exists() else {}
    if first in paid and last in paid:
        return {"source": "paper", "pnl": round(paid[last] - paid[first], 2), "return_pct": round(100 * (paid[last] / paid[first] - 1), 2)}
    e = evidence.load() or {"days": [], "equity": []}
    tested = dict(zip(e["days"], e["equity"], strict=True))
    before, end = _dt(lo - DAY).strftime("%Y-%m-%d"), _dt(hi - DAY).strftime("%Y-%m-%d")
    return {"source": "history", "return_pct": round(100 * (tested[end] / tested[before] - 1), 2)} if before in tested and end in tested else None


def _trades(x: tactics.Inputs, t: tactics.Tactic, side: np.ndarray, lev: float, start: int, capital: float) -> list[dict]:
    result = tactics.backtest(x, t, side, lev, start, capital)
    costs = engine.Costs()
    sl, tp, _ = tactics._risk(x, t)
    out, before = [], capital
    for r in result.trades.to_dict("records"):
        i, j, s = int(r["entry_bar"]), int(r["exit_bar"]), int(r["side"])
        entry = x.o[i] * (1 + s * costs.slip)
        snap = {k: round(float(x.f[k].iat[i - 1]), 3) for k in SNAPSHOT if k in x.f and i > 0 and np.isfinite(x.f[k].iat[i - 1])}
        out.append({
            "side": "LONG" if s > 0 else "SHORT",
            "entry_time": int(x.time[i]),
            "exit_time": int(x.time[j]) + (HOUR if r["reason"] in ("end", "time") else 0),
            "entry": round(float(entry), 8),
            "exit": round(float(_price(entry, s, float(r["ret"]), lev, costs.fee)), 8),
            "reason": r["reason"],
            "stop": round(float(entry * (1 - s * sl[i])), 8) if sl[i] > 0 else None,
            "take": round(float(entry * (1 + s * tp[i])), 8) if tp[i] > 0 else None,
            "return_on_margin_pct": round(100 * float(r["ret"]), 2),
            "pnl": round(float(before * r["ret"]), 2),
            "why": snap,
        })
        before *= 1 + float(r["ret"])
    return out


def run(symbol: str, day: datetime | None = None, days: int = 1, csv: Path | None = None, leverage: float | None = None, capital: float = 1000.0) -> dict:
    now = datetime.now(UTC)
    if csv is not None:
        bars = from_csv(csv)
        last = _dt(int(bars.open_time.max()))
        day = day or datetime(last.year, last.month, last.day, tzinfo=UTC) - timedelta(days=days - 1)
    else:
        day = day or datetime(now.year, now.month, now.day, tzinfo=UTC) - timedelta(days=days)
        bars = quotes(symbol, day - HISTORY, min(day + timedelta(days=days), now))
    lo, hi = _ms(day), _ms(day) + days * DAY
    bars = bars[bars.open_time < hi].reset_index(drop=True)
    start = int(np.searchsorted(bars.open_time.to_numpy(), lo))
    if start >= len(bars):
        raise ValueError(f"no quotes for {symbol} on {day:%Y-%m-%d}")
    try:
        btc = None if csv is not None else bars if symbol == "BTCUSDT" else quotes("BTCUSDT", _dt(int(bars.open_time.min())), _dt(int(bars.open_time.max()) + HOUR))
    except Exception:
        btc = None
    probe = tactics.inputs(bars, btc)
    x = tactics.inputs(bars, btc, _edge(probe.f))
    daily_close = bars.groupby(bars.open_time // DAY).close.last()
    vol = float(daily_close.pct_change().iloc[-31:-1].std()) if len(daily_close) > 10 else 0.0
    lev = float(leverage or (np.clip(TARGET_VOL / vol, 1.0, MAX_LEVERAGE) if vol > 0 else 1.0))
    catalog = tactics.catalog()
    sig = tactics.signals(x, catalog)
    history = tactics.daily(x, catalog)
    past = history[(history.index >= lo - 90 * DAY) & (history.index < lo)]
    pair_sharpe = past.mean() / past.std().replace(0, np.nan) * np.sqrt(365)
    record = _record()
    rows = []
    for t in catalog:
        eq = tactics.curve(x, t, sig[t.signal], lev, start)
        rows.append({
            "key": t.key,
            "label": t.describe(),
            "rule": t.rule,
            "family": family(t.rule),
            "overlay": t.overlay.name,
            "pnl": round(capital * float(eq[-1] - 1), 2),
            "return_pct": round(100 * float(eq[-1] - 1), 2),
            "worst_pct": round(100 * float(eq[start:].min() - 1), 2),
            "in_market_hours": int((tactics.targets(sig[t.signal], start)[start:] != 0).sum()),
            "pair_90d_sharpe": None if pd.isna(pair_sharpe.get(t.key)) else round(float(pair_sharpe[t.key]), 2),
            "record": record.get(t.key, {}),
        })
    rows.sort(key=lambda r: -r["pnl"])
    reference = "ema_cross(fast=50,slow=200)|signal"
    seen: set = set()
    top = []
    for r in rows:
        marks = {r["rule"], (r["pnl"], r["in_market_hours"], r["worst_pct"])}
        if not marks & seen:
            top.append(r["key"])
            seen |= marks
    picks: dict[str, str] = {}
    for key, role in [*zip(top[:3], ("best", "second", "third"), strict=False), (reference, "reference"), (rows[-1]["key"], "worst")]:
        picks.setdefault(key, role)
    atr = float(np.nan_to_num(x.f["atr_pct"].iat[start - 1])) if "atr_pct" in x.f and start > 0 else 0.0
    pnl_of = {r["key"]: r["pnl"] for r in rows}
    detail = []
    for key, role in picks.items():
        t = tactics.by_key(key)
        trades = _trades(x, t, sig[t.signal], lev, start, capital)
        detail.append({"key": key, "role": role, "title": t.title, "label": t.describe(), "about": t.explain(atr), "pnl": pnl_of[key], "trades": trades})
    view = bars[bars.open_time >= lo - 24 * HOUR]
    move = float(bars.close.iloc[-1] / (bars.close.iloc[start - 1] if start > 0 else bars.open.iloc[0]) - 1)
    pnl = np.array([r["pnl"] for r in rows])
    book, book_known = _book(symbol, lo, hi)
    doc = {
        "symbol": symbol,
        "from": f"{day:%Y-%m-%d}",
        "to": _dt(hi - DAY).strftime("%Y-%m-%d"),
        "days": days,
        "source": "ваш файл (без контексту BTC)" if csv else "Binance USDⓈ-M, свічки 1 год",
        "bars_in_window": len(bars) - start,
        "warmup_bars": start,
        "capital": capital,
        "leverage": round(lev, 2),
        "leverage_rule": "задано вами" if leverage else AUTO.format(target=100 * TARGET_VOL, vol=100 * vol, top=MAX_LEVERAGE).replace(".", ","),
        "price_move_pct": round(100 * move, 2),
        "atr_pct": round(100 * atr, 2),
        "bot": _bot(lo, hi),
        "summary": {
            "tactics": len(rows),
            "positive": int((pnl > 0).sum()),
            "negative": int((pnl < 0).sum()),
            "flat": int((pnl == 0).sum()),
            "median_pnl": round(float(np.median(pnl)), 2),
            "total_pnl": round(float(pnl.sum()), 2),
            "tied_best": int((pnl == pnl[0]).sum()),
            "robust": sum(all((r["record"].get(k) or -1) > 0 for k in ("dev", "holdout", "untouched")) for r in rows),
            "best": rows[0]["key"],
            "worst": rows[-1]["key"],
        },
        "families": {
            f: {
                "tactics": sum(r["family"] == f for r in rows),
                "positive": sum(r["family"] == f and r["pnl"] > 0 for r in rows),
                "pnl_sum": round(sum(r["pnl"] for r in rows if r["family"] == f), 2),
            }
            for f in ("trend", "revert", "pattern", "ml")
        },
        "reference": reference,
        "book": book,
        "book_known": book_known,
        "candles": [
            {"time": int(r.open_time) // 1000, "open": float(r.open), "high": float(r.high), "low": float(r.low), "close": float(r.close)} for r in view.itertuples(index=False)
        ],
        "tactics": rows,
        "detail": detail,
    }
    out = settings.reports_dir / "quant" / "day"
    out.mkdir(parents=True, exist_ok=True)
    doc["report"] = str(out / f"{symbol}_{day:%Y-%m-%d}_{days}d.json")
    Path(doc["report"]).write_text(json.dumps(doc, default=str))
    return doc
