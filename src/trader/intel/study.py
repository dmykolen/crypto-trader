"""Out-of-sample study: do the intel signals predict 1h price moves of liquid perps?

Protocol, fixed before looking at the test period:

* Universe: `UNIVERSE` (liquid since 2022, delisted names included until their last bar), hourly bars from
  data/universe/1h. Forward return of bar t = log(close[t+h] / close[t]): the signal row of bar t is known at its close.
* Discovery (train) = `TRAIN`, out-of-sample (test) = `TEST`. Each feature's sign is chosen on train only; the test
  period is scored once with that sign. Nothing (thresholds, windows, feature list) is tuned on test.
* Rank IC per calendar month (cross-sectional: Spearman across symbols each hour vs market-relative return, averaged;
  time-series: Spearman within the month per symbol, averaged; market: Spearman vs the equal-weight market return).
  t-statistics are taken across monthly ICs, which absorbs the overlap of multi-hour forward windows.
* Event studies for discrete news (categories, bursts): mean market-relative forward return, one event per symbol per
  24 h, and the same with the return signed by headline polarity.
* Holm correction over every (feature, horizon) scored on test; a signal is `robust` only when it keeps its train sign
  with a Holm-adjusted one-sided p < 0.05 AND a simple daily long/short (or timing) rule stays positive after costs.
"""

import json
import math
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from trader.core.config import settings

UNIVERSE = [
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "LUNAUSDT",
    "DOGEUSDT",
    "XRPUSDT",
    "ETCUSDT",
    "BNBUSDT",
    "ADAUSDT",
    "AVAXUSDT",
    "NEARUSDT",
    "FTMUSDT",
    "MATICUSDT",
    "1000SHIBUSDT",
    "GALAUSDT",
    "ATOMUSDT",
    "SANDUSDT",
    "LINKUSDT",
    "LTCUSDT",
    "DOTUSDT",
    "TRXUSDT",
    "UNIUSDT",
    "FILUSDT",
    "AAVEUSDT",
    "BCHUSDT",
    "XLMUSDT",
]
TRAIN = ("2022-01-01", "2024-07-01")
TEST = ("2024-07-01", "2026-10-01")
HORIZONS = (1, 4, 24)
HOUR_MS = 3_600_000
COST_BPS = 5.0
MIN_CS_SYMBOLS = 8
EVENT_CATEGORIES = ("listing", "delisting", "hack_exploit", "regulation", "lawsuit", "etf", "unlock_supply", "partnership_adoption", "macro", "outage")

FEATURES: dict[str, tuple[str, str]] = {
    "news_mentions_24h": ("cs", "distinct headlines naming the perp, trailing 24 h"),
    "news_burst_z": ("cs", "this hour's mentions vs the trailing 7-day baseline"),
    "news_polarity_24h": ("cs", "mention-weighted lexicon polarity, trailing 24 h"),
    "oi_chg_1h": ("cs", "open-interest change over 1 h (metrics archive)"),
    "oi_chg_24h": ("cs", "open-interest change over 24 h"),
    "top_position_ratio_z": ("cs", "top-trader long/short position ratio vs its own 30-day history"),
    "top_account_ratio_z": ("cs", "top-trader long/short account ratio vs its own 30-day history"),
    "global_account_ratio_z": ("cs", "all-account long/short ratio vs its own 30-day history"),
    "taker_ratio_24h": ("cs", "log taker buy/sell volume ratio, trailing 24 h mean"),
    "oi_chg_24h_ts": ("ts", "open-interest change over 24 h, within-symbol timing"),
    "top_position_ratio_ts": ("ts", "top-trader position ratio z, within-symbol timing"),
    "news_mentions_24h_ts": ("ts", "own headline count, within-symbol timing"),
    "wiki_z": ("ts", "Wikipedia pageviews vs 28-day baseline (9 large tokens)"),
    "gdelt_z": ("ts", "GDELT article volume vs 28-day baseline (5 large tokens)"),
    "fear_greed": ("mkt", "alternative.me Fear & Greed index level"),
    "fear_greed_chg_7d": ("mkt", "Fear & Greed change over 7 days"),
    "mkt_mentions_24h": ("mkt", "all stored headlines, trailing 24 h"),
    "mkt_polarity_24h": ("mkt", "market-wide mention-weighted polarity, trailing 24 h"),
    "ref_ret_24h": ("cs", "REFERENCE (not intel): own past 24 h return"),
    "ref_funding": ("cs", "REFERENCE (not intel): last funding rate"),
}


def report_path() -> Path:
    return settings.reports_dir / "intel_study.md"


def _ms(day: str) -> int:
    return int(datetime.fromisoformat(day).replace(tzinfo=UTC).timestamp() * 1000)


def load_prices(symbol: str) -> pd.DataFrame | None:
    path = settings.data_dir / "universe" / "1h" / f"{symbol}.parquet"
    if not path.exists():
        return None
    frame = pd.read_parquet(path, columns=["open_time", "close", "funding"]).drop_duplicates("open_time").set_index("open_time").sort_index()
    return frame[(frame.index >= _ms(TRAIN[0])) & (frame.index < _ms(TEST[1]))]


def _rolling_z(series: pd.Series, window: int = 720) -> pd.Series:
    mean = series.rolling(window, min_periods=window // 4).mean()
    std = series.rolling(window, min_periods=window // 4).std()
    return (series - mean) / std.replace(0.0, np.nan)


def derive(prices: pd.DataFrame, feats: pd.DataFrame) -> pd.DataFrame:
    """Raw hourly `signals.features` + price bars → the study's feature columns and forward returns (no look-ahead)."""
    f = feats.reindex(prices.index)
    out = pd.DataFrame(index=prices.index)
    mentions = f["news_mentions"].fillna(0.0)
    out["news_mentions_24h"] = mentions.rolling(24, min_periods=1).sum()
    out["news_burst_z"] = f["news_burst_z"].fillna(0.0)
    weighted = (f["news_polarity"].fillna(0.0) * mentions).rolling(24, min_periods=1).sum()
    out["news_polarity_24h"] = (weighted / out["news_mentions_24h"].replace(0.0, np.nan)).fillna(0.0)
    out["oi_chg_1h"] = f["oi_chg_1h"]
    out["oi_chg_24h"] = f["oi_chg_24h"]
    for name in ("top_position_ratio", "top_account_ratio", "global_account_ratio"):
        out[f"{name}_z"] = _rolling_z(f[name].astype(float))
    out["taker_ratio_24h"] = np.log(f["taker_ratio"].astype(float).where(lambda s: s > 0)).rolling(24, min_periods=12).mean()
    out["oi_chg_24h_ts"] = out["oi_chg_24h"]
    out["top_position_ratio_ts"] = out["top_position_ratio_z"]
    out["news_mentions_24h_ts"] = out["news_mentions_24h"]
    out["wiki_z"] = f["wiki_z"]
    out["gdelt_z"] = f["gdelt_z"]
    out["fear_greed"] = f["fear_greed"]
    out["fear_greed_chg_7d"] = f["fear_greed"] - f["fear_greed"].shift(168)
    mkt_mentions = f["mkt_mentions"].fillna(0.0)
    out["mkt_mentions_24h"] = mkt_mentions.rolling(24, min_periods=1).sum()
    mkt_weighted = (f["mkt_polarity"].fillna(0.0) * mkt_mentions).rolling(24, min_periods=1).sum()
    out["mkt_polarity_24h"] = (mkt_weighted / out["mkt_mentions_24h"].replace(0.0, np.nan)).fillna(0.0)
    logp = np.log(prices["close"].astype(float))
    out["ref_ret_24h"] = logp - logp.shift(24)
    out["ref_funding"] = prices["funding"].astype(float).ffill() if "funding" in prices else np.nan
    for cat in EVENT_CATEGORIES:
        out[f"cat_{cat}"] = f[f"news_cat_{cat}"].fillna(0).astype(int)
    out["news_polarity"] = f["news_polarity"].fillna(0.0)
    out["news_mentions"] = mentions
    for h in HORIZONS:
        out[f"fwd_{h}"] = logp.shift(-h) - logp
    return out.replace([np.inf, -np.inf], np.nan)


def build_panel(symbols: list[str] | None = None, feature_fn=None) -> pd.DataFrame:
    """Long panel (symbol, open_time) of study features + forward returns, with market-relative returns added."""
    from trader.intel import signals

    feature_fn = feature_fn or signals.features
    frames = []
    for symbol in symbols or UNIVERSE:
        prices = load_prices(symbol)
        if prices is None or len(prices) < 24 * 60:
            continue
        frame = derive(prices, feature_fn(symbol, int(prices.index[0]), int(prices.index[-1]) + HOUR_MS))
        frames.append(frame.assign(symbol=symbol).reset_index())
    panel = pd.concat(frames, ignore_index=True)
    for h in HORIZONS:
        market = panel.groupby("open_time")[f"fwd_{h}"].transform("mean")
        panel[f"mkt_{h}"] = market
        panel[f"rel_{h}"] = panel[f"fwd_{h}"] - market
    panel["month"] = pd.to_datetime(panel["open_time"], unit="ms", utc=True).dt.strftime("%Y-%m")
    return panel


def _row_rank_corr(x: pd.DataFrame, y: pd.DataFrame, min_n: int) -> pd.Series:
    """Spearman across columns for every row (NaN pairs dropped; rows with < min_n pairs or no variance → NaN)."""
    mask = x.notna() & y.notna()
    xr = x.where(mask).rank(axis=1)
    yr = y.where(mask).rank(axis=1)
    xc = xr.sub(xr.mean(axis=1), axis=0)
    yc = yr.sub(yr.mean(axis=1), axis=0)
    denom = np.sqrt((xc**2).sum(axis=1) * (yc**2).sum(axis=1))
    corr = (xc * yc).sum(axis=1) / denom.replace(0.0, np.nan)
    return corr.where(mask.sum(axis=1) >= min_n)


def _spearman(x: pd.Series, y: pd.Series) -> float:
    ok = x.notna() & y.notna()
    if ok.sum() < 20 or x[ok].nunique() < 2 or y[ok].nunique() < 2:
        return math.nan
    return float(x[ok].rank().corr(y[ok].rank()))


def monthly_ic(panel: pd.DataFrame, feature: str, mode: str, h: int) -> pd.Series:
    """One rank IC per calendar month (index = 'YYYY-MM')."""
    if mode == "cs":
        x = panel.pivot_table(index="open_time", columns="symbol", values=feature, aggfunc="last", dropna=False)
        y = panel.pivot_table(index="open_time", columns="symbol", values=f"rel_{h}", aggfunc="last", dropna=False).reindex_like(x)
        hourly = _row_rank_corr(x, y, MIN_CS_SYMBOLS)
        months = pd.to_datetime(hourly.index, unit="ms", utc=True).strftime("%Y-%m")
        return hourly.groupby(months).mean().dropna()
    if mode == "ts":
        per = panel.groupby(["month", "symbol"]).apply(lambda g: _spearman(g[feature], g[f"fwd_{h}"]), include_groups=False)
        return per.groupby(level="month").mean().dropna()
    market = panel.groupby("open_time").agg(month=("month", "first"), x=(feature, "first"), y=(f"mkt_{h}", "first"))
    return market.groupby("month").apply(lambda g: _spearman(g["x"], g["y"]), include_groups=False).dropna()


def t_stat(values: pd.Series) -> float:
    values = values.dropna()
    if len(values) < 6 or values.std() == 0:
        return math.nan
    return float(values.mean() / values.std() * math.sqrt(len(values)))


def p_one_sided(t: float) -> float:
    """Upper-tail normal p-value (monthly ICs ≥ 24 per period make the normal approximation adequate)."""
    return math.nan if math.isnan(t) else 0.5 * math.erfc(t / math.sqrt(2))


def holm(pvalues: dict[str, float]) -> dict[str, float]:
    """Holm step-down adjusted p-values (NaN entries stay NaN and do not count)."""
    valid = sorted(((p, k) for k, p in pvalues.items() if not math.isnan(p)))
    out = {k: math.nan for k in pvalues}
    running = 0.0
    m = len(valid)
    for i, (p, k) in enumerate(valid):
        running = max(running, min(1.0, (m - i) * p))
        out[k] = running
    return out


def _split(panel: pd.DataFrame, period: tuple[str, str]) -> pd.DataFrame:
    return panel[(panel["open_time"] >= _ms(period[0])) & (panel["open_time"] < _ms(period[1]))]


def period_rule(panel: pd.DataFrame, feature: str, mode: str, sign: float, h: int = 24, *, scale: tuple[float, float] | None = None) -> dict:
    """Rule rebalanced every `h` hours (on UTC multiples of h), held h hours, `COST_BPS` per unit of turnover.

    cs: weights ∝ demeaned cross-sectional rank of sign·feature (market-neutral, gross 1; ties — e.g. hours without
    news — share the middle rank, so sparse features trade only the names that differ).
    ts/mkt: position = clip(sign·(x - mean)/std, -1, 1) with mean/std from train (`scale`), per symbol or on the market.
    """
    day = panel[(panel["open_time"] % (h * HOUR_MS)) == 0]
    if mode == "cs":
        x = day.pivot_table(index="open_time", columns="symbol", values=feature, aggfunc="last") * sign
        r = day.pivot_table(index="open_time", columns="symbol", values=f"fwd_{h}", aggfunc="last").reindex_like(x)
        ranks = x.where(r.notna()).rank(axis=1)
        enough = ranks.notna().sum(axis=1) >= MIN_CS_SYMBOLS
        centered = ranks.sub(ranks.mean(axis=1), axis=0)
        weights = centered.div(centered.abs().sum(axis=1).replace(0.0, np.nan), axis=0)
        weights = weights.where(enough, 0.0).fillna(0.0)
    else:
        mean, std = scale or (0.0, 1.0)
        if mode == "mkt":
            day = day.groupby("open_time").agg(x=(feature, "first"), fwd=(f"mkt_{h}", "first"))
            x = day[["x"]].rename(columns={"x": "MKT"})
            r = day[["fwd"]].rename(columns={"fwd": "MKT"})
        else:
            x = day.pivot_table(index="open_time", columns="symbol", values=feature, aggfunc="last")
            r = day.pivot_table(index="open_time", columns="symbol", values=f"fwd_{h}", aggfunc="last").reindex_like(x)
        weights = (sign * (x - mean) / (std or 1.0)).clip(-1, 1).where(r.notna()).fillna(0.0)
        weights = weights.div(weights.abs().sum(axis=1).clip(lower=1.0), axis=0)
    gross = (weights * r.fillna(0.0)).sum(axis=1)
    turnover = weights.diff().abs().sum(axis=1).fillna(weights.abs().sum(axis=1))
    net = gross - turnover * COST_BPS / 1e4
    per_day = 24 / h
    if len(net) < 30 or net.std() == 0:
        return {"horizon_h": h, "periods": len(net)}
    return {
        "horizon_h": h,
        "periods": len(net),
        "gross_bps_per_day": round(float(gross.mean() * 1e4 * per_day), 2),
        "net_bps_per_day": round(float(net.mean() * 1e4 * per_day), 2),
        "net_sharpe": round(float(net.mean() / net.std() * math.sqrt(365 * per_day)), 2),
        "turnover_per_day": round(float(turnover.mean() * per_day), 3),
    }


def coverage(panel: pd.DataFrame, feature: str) -> float:
    values = panel[feature]
    nonzero = values.notna() & (values != 0)
    return round(float(nonzero.mean()), 4)


def score_features(panel: pd.DataFrame) -> list[dict]:
    train, test = _split(panel, TRAIN), _split(panel, TEST)
    rows = []
    for feature, (mode, about) in FEATURES.items():
        for h in HORIZONS:
            ic_train, ic_test = monthly_ic(train, feature, mode, h), monthly_ic(test, feature, mode, h)
            t_train = t_stat(ic_train)
            sign = 1.0 if (ic_train.mean() if len(ic_train) else 0.0) >= 0 else -1.0
            t_test = t_stat(ic_test * sign)
            rows.append({
                "feature": feature,
                "mode": mode,
                "about": about,
                "horizon_h": h,
                "coverage_train": coverage(train, feature),
                "coverage_test": coverage(test, feature),
                "months_train": len(ic_train),
                "months_test": len(ic_test),
                "ic_train": round(float(ic_train.mean()), 4) if len(ic_train) else None,
                "t_train": None if math.isnan(t_train) else round(t_train, 2),
                "sign": int(sign),
                "ic_test_signed": round(float((ic_test * sign).mean()), 4) if len(ic_test) else None,
                "t_test": None if math.isnan(t_test) else round(t_test, 2),
                "p_test": p_one_sided(t_test),
            })
    adjusted = holm({f"{r['feature']}|{r['horizon_h']}": r["p_test"] for r in rows})
    for r in rows:
        r["p_test_holm"] = adjusted[f"{r['feature']}|{r['horizon_h']}"]
        r["p_test"] = None if math.isnan(r["p_test"]) else round(r["p_test"], 4)
        r["p_test_holm"] = None if math.isnan(r["p_test_holm"]) else round(r["p_test_holm"], 4)
    return rows


def rules(panel: pd.DataFrame, scores: list[dict]) -> dict[str, dict]:
    """One trading rule per feature: the horizon and sign come from TRAIN only (best train net return after costs among
    the horizons, each with its own train IC sign); the test period is then scored once with that choice."""
    train, test = _split(panel, TRAIN), _split(panel, TEST)
    out = {}
    for feature, (mode, _) in FEATURES.items():
        values = train[feature].replace([np.inf, -np.inf], np.nan).dropna()
        scale = (float(values.mean()), float(values.std())) if len(values) and values.std() > 0 else None
        candidates = []
        for r in (r for r in scores if r["feature"] == feature):
            fit = period_rule(train, feature, mode, r["sign"], r["horizon_h"], scale=scale)
            candidates.append((fit.get("net_bps_per_day", -math.inf), r["horizon_h"], r["sign"], fit))
        _, h, sign, fit = max(candidates, key=lambda c: c[0])
        out[feature] = {"horizon_h": h, "sign": sign, "train": fit, "test": period_rule(test, feature, mode, sign, h, scale=scale)}
    return out


def event_study(panel: pd.DataFrame) -> list[dict]:
    """Per category (and for bursts): market-relative forward returns after the first event per symbol per 24 h."""
    triggers = {f"cat_{c}": panel[f"cat_{c}"] > 0 for c in EVENT_CATEGORIES}
    triggers["burst_z>=3 & mentions>=2"] = (panel["news_burst_z"] >= 3) & (panel["news_mentions"] >= 2)
    triggers["any_mention"] = panel["news_mentions"] >= 1
    rows = []
    for name, hit in triggers.items():
        events = panel[hit].sort_values(["symbol", "open_time"])
        keep = events.groupby("symbol")["open_time"].diff().fillna(np.inf) >= 24 * HOUR_MS
        events = events[keep]
        for label, period in (("train", TRAIN), ("test", TEST)):
            part = _split(events, period)
            row = {"event": name, "period": label, "n": len(part)}
            for h in HORIZONS:
                rel = part[f"rel_{h}"].dropna()
                signed = (rel * np.sign(part.loc[rel.index, "news_polarity"])).loc[lambda s: s != 0]
                row[f"rel_{h}h_bps"] = round(float(rel.mean() * 1e4), 1) if len(rel) else None
                row[f"t_{h}h"] = round(float(rel.mean() / rel.std() * math.sqrt(len(rel))), 2) if len(rel) > 5 and rel.std() > 0 else None
                row[f"polarity_signed_{h}h_bps"] = round(float(signed.mean() * 1e4), 1) if len(signed) else None
                row[f"polarity_t_{h}h"] = round(float(signed.mean() / signed.std() * math.sqrt(len(signed))), 2) if len(signed) > 5 and signed.std() > 0 else None
            rows.append(row)
    return rows


def verdict(feature_rows: list[dict], rule: dict | None) -> str:
    """robust: Holm p<0.05 on test in the train direction at some horizon AND the train-chosen rule nets > 0 on test.
    untradeable: the Holm test passes but the rule loses after costs. weak: only an unadjusted p<0.05 on test.
    fails: no test support in the train direction. no-data: never scored on test."""
    scored = [r for r in feature_rows if r["t_test"] is not None]
    if not scored:
        return "no-data"
    net = ((rule or {}).get("test") or {}).get("net_bps_per_day")
    if any(r["p_test_holm"] is not None and r["p_test_holm"] < 0.05 for r in scored):
        return "robust" if net is not None and net > 0 else "untradeable"
    if any(r["p_test"] is not None and r["p_test"] < 0.05 for r in scored):
        return "weak"
    return "fails"


def _fmt(value, spec: str = "") -> str:
    return "–" if value is None or (isinstance(value, float) and math.isnan(value)) else format(value, spec)


def render(doc: dict) -> str:
    lines = [
        "# Intel signals — out-of-sample study",
        "",
        f"Generated {doc['generated_at']} by `trader intel study`. Universe: {len(doc['universe'])} perps, {doc['panel_rows']:,} symbol-hours.",
        f"Train (sign selection) {TRAIN[0]} → {TRAIN[1]}, test (scored once) {TEST[0]} → {TEST[1]}. Costs {COST_BPS:g} bps per unit turnover.",
        "",
        "## Verdicts",
        "",
        "| feature | mode | verdict | rank corr with past 24 h return | what |",
        "|---|---|---|---|---|",
    ]
    for feature, (mode, about) in FEATURES.items():
        lines.append(f"| `{feature}` | {mode} | **{doc['verdicts'][feature]}** | {_fmt(doc['overlap_with_reversal'].get(feature), '+.2f')} | {about} |")
    lines += ["", *doc["summary"], "", "## Rank IC by horizon (monthly ICs; test IC signed by the train direction)", ""]
    lines += ["| feature | h | cov train | cov test | IC train | t train | IC test (signed) | t test | p test | p Holm |", "|---|---|---|---|---|---|---|---|---|---|"]
    for r in doc["ic"]:
        lines.append(
            f"| `{r['feature']}` | {r['horizon_h']} | {_fmt(r['coverage_train'], '.1%')} | {_fmt(r['coverage_test'], '.1%')} | {_fmt(r['ic_train'], '+.4f')} "
            f"| {_fmt(r['t_train'])} | {_fmt(r['ic_test_signed'], '+.4f')} | {_fmt(r['t_test'])} | {_fmt(r['p_test'])} | {_fmt(r['p_test_holm'])} |"
        )
    lines += ["", "## Trading rule (horizon + sign picked on train by net return; cs = rank-weighted long/short, ts/mkt = clipped z timing)", ""]
    lines += ["| feature | h | train net bps/day | train Sharpe | test gross bps/day | test net bps/day | test Sharpe | test turnover/day |", "|---|---|---|---|---|---|---|---|"]
    for feature, rule in doc["rules"].items():
        tr, te = rule["train"], rule["test"]
        lines.append(
            f"| `{feature}` | {rule['horizon_h']} | {_fmt(tr.get('net_bps_per_day'))} | {_fmt(tr.get('net_sharpe'))} | {_fmt(te.get('gross_bps_per_day'))} "
            f"| {_fmt(te.get('net_bps_per_day'))} | {_fmt(te.get('net_sharpe'))} | {_fmt(te.get('turnover_per_day'))} |"
        )
    lines += ["", "## Event study (market-relative forward return, one event per symbol per 24 h)", ""]
    lines += ["| event | period | n | 1h bps | t | 4h bps | t | 24h bps | t | polarity-signed 24h bps | t |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in doc["events"]:
        lines.append(
            f"| {r['event']} | {r['period']} | {r['n']} | {_fmt(r['rel_1h_bps'])} | {_fmt(r['t_1h'])} | {_fmt(r['rel_4h_bps'])} | {_fmt(r['t_4h'])} "
            f"| {_fmt(r['rel_24h_bps'])} | {_fmt(r['t_24h'])} | {_fmt(r['polarity_signed_24h_bps'])} | {_fmt(r['polarity_t_24h'])} |"
        )
    lines += ["", "## Data coverage and caveats", "", *[f"- {c}" for c in doc["caveats"]], ""]
    return "\n".join(lines)


def summarize(doc: dict) -> list[str]:
    counts = pd.Series(doc["verdicts"]).value_counts().to_dict()
    intel = {k: v for k, v in doc["verdicts"].items() if not k.startswith("ref_")}

    def names(label: str) -> str:
        return ", ".join(f"`{k}`" for k, v in intel.items() if v == label) or "none"

    return [
        f"Verdict counts (all {len(doc['verdicts'])} features incl. 2 price references): " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())) + ".",
        "",
        f"- **robust** (Holm-significant on test in the train direction AND the train-chosen rule is net positive on test): {names('robust')}.",
        f"- **untradeable** (Holm-significant rank IC on test, but the rule loses after {COST_BPS:g} bps costs): {names('untradeable')}.",
        f"- **weak** (only unadjusted p < 0.05 on test): {names('weak')}.",
        f"- **fails**: {names('fails')}. **no-data**: {names('no-data')}.",
        f"- References: short-term reversal `ref_ret_24h` is **{doc['verdicts']['ref_ret_24h']}**, funding `ref_funding` is **{doc['verdicts']['ref_funding']}**"
        + (
            " — the harness does detect known price effects, so the intel results are not a power failure."
            if {doc["verdicts"]["ref_ret_24h"], doc["verdicts"]["ref_funding"]} <= {"robust", "untradeable"}
            else "."
        ),
    ]


def overlap_with_reversal(panel: pd.DataFrame, n: int = 200_000) -> dict[str, float | None]:
    """Pooled Spearman of each feature with the past 24 h return: a signal that is mostly reversal in disguise shows a large |rho|."""
    sample = panel.sample(min(n, len(panel)), random_state=0)
    out = {}
    for feature in FEATURES:
        rho = _spearman(sample[feature], sample["ref_ret_24h"])
        out[feature] = None if math.isnan(rho) else round(rho, 3)
    return out


def _gdelt_note() -> str:
    from trader.intel import history

    gd = history.load_series("gdelt")
    if gd.empty:
        return "GDELT: no data cached (the API throttled/refused this host); gdelt_z is unscored. `trader intel backfill` resumes it."
    span = pd.to_datetime(gd["ts"], unit="ms", utc=True)
    return (
        f"GDELT: only {gd['key'].nunique()} token(s), {span.min():%Y-%m-%d} → {span.max():%Y-%m-%d} cached — the API throttled and then refused this host during"
        " the backfill (HTTP 429 / connect timeouts even at one request per minute), so gdelt_z has no test-period data. `trader intel backfill` resumes it."
    )


def caveats(panel: pd.DataFrame) -> list[str]:
    from trader.intel import history

    test = _split(panel, TEST)
    gd = history.load_series("gdelt")
    wiki = history.load_series("wiki")
    return [
        "Stored text history 2022–2026 is almost entirely Binance + Upbit announcement boards; media RSS, Reddit and the other boards only go back"
        " weeks or months, so the news_* features here measure exchange-announcement attention, not media sentiment.",
        "Polarity is a title lexicon, not a model; Claude assessments (llm_score) exist for too few items to be studied and are excluded.",
        f"Wikipedia pageviews cover {wiki['key'].nunique() if len(wiki) else 0} tokens, so wiki_z is time-series only (test coverage {coverage(test, 'wiki_z'):.1%}"
        f" of symbol-hours); GDELT rows cached: {len(gd)}.",
        _gdelt_note(),
        "Positioning signals partly overlap with short-term price reversal (rank-correlation column; oi_chg_24h most of all); like the reversal"
        f" reference itself, the Holm-significant ones are real at 1–4 h but too small to pay {COST_BPS:g} bps per unit of turnover.",
        "Positioning (OI, long/short ratios) comes from the data.binance.vision metrics archive, last 5-minute snapshot inside each hour.",
        "Entity linking uses today's perp list and CoinGecko names; universe symbols all traded through both periods except LUNA (to 2022-05),"
        " MATIC (to 2024-09) and FTM (migrated to S), so survivorship effects on linking are limited to them.",
        "Monthly-IC t-stats treat months as independent; persistent features (Fear & Greed, ratios) have autocorrelated monthly ICs, so their t is optimistic.",
    ]


def run(symbols: list[str] | None = None, feature_fn=None, write: bool = True) -> dict:
    panel = build_panel(symbols, feature_fn)
    scores = score_features(panel)
    rule = rules(panel, scores)
    events = event_study(panel)
    verdicts = {f: verdict([r for r in scores if r["feature"] == f], rule.get(f)) for f in FEATURES}
    doc = {
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "universe": sorted(panel["symbol"].unique().tolist()),
        "panel_rows": len(panel),
        "train": TRAIN,
        "test": TEST,
        "horizons_h": list(HORIZONS),
        "cost_bps": COST_BPS,
        "verdicts": verdicts,
        "ic": scores,
        "rules": rule,
        "events": events,
        "caveats": caveats(panel),
        "overlap_with_reversal": overlap_with_reversal(panel),
    }
    doc["summary"] = summarize(doc)
    if write:
        path = report_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render(doc))
        path.with_suffix(".json").write_text(json.dumps(doc, indent=2, default=str))
    return doc
