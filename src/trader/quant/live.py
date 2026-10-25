import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pandas as pd

from trader.core.config import settings
from trader.integrations import binance
from trader.quant import features, model, neutral, xsmodel
from trader.quant.model import MIN_ATR_PCT, STABLES
from trader.quant.trend import DAY, Panel, stats
from trader.services import market_data

log = logging.getLogger(__name__)
HOUR = 3_600_000
DECISION_HOUR = 23


def _ms(at: datetime) -> int:
    return int(at.timestamp() * 1000)


def _fetch(rest: binance.FuturesREST, symbol: str, start_ms: int, end_ms: int) -> pd.DataFrame | None:
    for attempt in range(4):
        try:
            bars = rest.klines(symbol, "1h", start_ms, end_ms)
            break
        except Exception as exc:
            log.warning("klines %s failed (%s), retrying", symbol, exc)
            time.sleep(2 * (attempt + 1))
    else:
        return None
    if bars is None or len(bars) < 24 * 20:
        return None
    bars = market_data._normalize(bars)
    try:
        rates = rest.funding(symbol, start_ms, end_ms)
    except Exception:
        rates = None
    bars["funding"] = market_data.funding_per_bar(bars.open_time.to_numpy(), HOUR, rates) if rates is not None and len(rates) else 0.0
    return bars


def collect(start: datetime, end: datetime, min_volume: float = 10e6, workers: int = 4) -> dict[str, pd.DataFrame]:
    cache = settings.data_dir / "quant" / "live" / f"bars_{start:%Y%m%d%H}_{end:%Y%m%d%H}.parquet"
    if cache.exists():
        df = pd.read_parquet(cache)
        return {str(sym): g.drop(columns="symbol").reset_index(drop=True) for sym, g in df.groupby("symbol")}
    out = _collect(start, end, min_volume, workers)
    cache.parent.mkdir(parents=True, exist_ok=True)
    pd.concat([b.assign(symbol=sym) for sym, b in out.items()], ignore_index=True).to_parquet(cache, index=False)
    return out


def _collect(start: datetime, end: datetime, min_volume: float, workers: int) -> dict[str, pd.DataFrame]:
    rest = binance.FuturesREST()
    info = rest.exchange_info()
    symbols = [
        s["symbol"]
        for s in info["symbols"]
        if s.get("contractType") == "PERPETUAL" and s.get("quoteAsset") == "USDT" and s["symbol"].removesuffix("USDT") not in STABLES and int(s.get("onboardDate", 0)) < _ms(end)
    ]
    with ThreadPoolExecutor(workers) as pool:
        fetched = dict(zip(symbols, pool.map(lambda s: _fetch(rest, s, _ms(start), _ms(end)), symbols), strict=True))
    out = {}
    for sym, bars in fetched.items():
        if bars is None:
            continue
        daily = bars.quote_volume.rolling(720, min_periods=240).sum() / 30.0
        if (daily >= min_volume).any() or sym == "BTCUSDT":
            out[sym] = bars
    return out


def scores(bars: dict[str, pd.DataFrame], day_from: int, min_volume: float = 10e6) -> pd.DataFrame:
    long_m, short_m, label, _ = model.model_for(day_from)
    names = long_m.feature_name()
    xs_m = xsmodel.model_for(day_from)
    xs_names = xs_m.feature_name()
    btc = bars["BTCUSDT"]
    rows = []
    for sym, b in bars.items():
        f = features.frame(b, btc)
        t = f.index.to_numpy()
        daily = b.quote_volume.rolling(720, min_periods=240).sum().to_numpy() / 30.0
        ok = ((t % DAY) == DECISION_HOUR * HOUR) & (t >= day_from - 20 * DAY) & (daily >= min_volume) & (f.atr_pct.to_numpy() >= MIN_ATR_PCT)
        if not ok.any():
            continue
        x = f.reindex(columns=names)[ok]
        xx = f.reindex(columns=xs_names)[ok]
        rows.append(pd.DataFrame({"symbol": sym, "open_time": t[ok], "pred_long": long_m.predict(x), "pred_short": short_m.predict(x), "xs": xs_m.predict(xx)}))
    out = pd.concat(rows, ignore_index=True)
    out.attrs["model"] = label
    return out


def panel(bars: dict[str, pd.DataFrame]) -> Panel:
    frames = []
    for sym, b in bars.items():
        g = b.groupby(b.open_time // DAY * DAY)
        d = pd.DataFrame({
            "open": g.open.first(),
            "high": g.high.max(),
            "low": g.low.min(),
            "close": g.close.last(),
            "qv": g.quote_volume.sum(),
            "funding": g.funding.sum(),
            "hours": g.size(),
        })
        d = d[d.hours >= 20].drop(columns="hours")
        d["symbol"] = sym
        frames.append(d.rename_axis("day").reset_index())
    df = pd.concat(frames, ignore_index=True)
    wide = {k: df.pivot(index="day", columns="symbol", values=k).sort_index() for k in ("open", "high", "low", "close", "qv", "funding")}
    full = pd.RangeIndex(int(wide["close"].index.min()), int(wide["close"].index.max()) + DAY, DAY)
    wide = {k: v.reindex(full) for k, v in wide.items()}
    r = wide["close"].pct_change(fill_method=None)
    r = r.where((r > -0.95) & (r < 3.0))
    return Panel(full.to_numpy(), wide["close"].columns.to_numpy(), wide["open"], wide["high"], wide["low"], wide["close"], wide["qv"], wide["funding"].fillna(0.0), r)


def forward(first_day: datetime, last_day: datetime | None = None, capital: float = 1000.0) -> dict:
    now = datetime.now(UTC)
    last_day = last_day or datetime(now.year, now.month, now.day, tzinfo=UTC) - timedelta(days=1)
    bars = collect(first_day - timedelta(days=62), min(last_day + timedelta(days=1), now))
    p = panel(bars)
    raw = scores(bars, _ms(first_day))
    edge = neutral.daily_scores(raw, DECISION_HOUR)["edge"]
    xs7 = raw.pivot_table(index=(raw.open_time // DAY * DAY), columns="symbol", values="xs", aggfunc="last")
    family = {"blend": neutral.blend(xs7, edge), "edge": edge}
    w = neutral.production_weights(p, family)
    ret = neutral.weights_returns(p, w)
    ret_full = neutral.weights_returns(p, neutral.ensemble_weights(p, family, {**neutral.ENSEMBLE, "family": "edge"}))
    days = ret[(ret.index >= _ms(first_day)) & (ret.index <= _ms(last_day))]
    equity = capital * (1 + days).cumprod()
    latest = w.loc[w.index <= _ms(last_day)].iloc[-1]
    book = latest[latest.abs() > 1e-9].sort_values()
    doc = {
        "model": raw.attrs.get("model"),
        "symbols_scored": int(raw.symbol.nunique()),
        "period": [first_day.strftime("%Y-%m-%d"), last_day.strftime("%Y-%m-%d")],
        "stats": stats(ret, _ms(first_day), _ms(last_day) + DAY),
        "stats_edge_only": stats(ret_full, _ms(first_day), _ms(last_day) + DAY),
        "days": [
            {"day": datetime.fromtimestamp(int(t) / 1000, UTC).strftime("%Y-%m-%d"), "return_pct": round(100 * float(v), 3), "equity": round(float(e), 2)}
            for (t, v), e in zip(days.items(), equity.to_numpy(), strict=True)
        ],
        "book_for_next_day": {
            "decided_at": datetime.fromtimestamp(int(latest.name) / 1000 + 86_400, UTC).strftime("%Y-%m-%d 00:00 UTC"),
            "longs": {s: round(float(v), 4) for s, v in book[book > 0].sort_values(ascending=False).items()},
            "shorts": {s: round(float(v), 4) for s, v in book[book < 0].items()},
        },
    }
    out = settings.reports_dir / "quant"
    out.mkdir(parents=True, exist_ok=True)
    (out / "forward.json").write_text(json.dumps(doc, indent=2, default=str))
    return doc
