import io
import itertools
import logging
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import numpy as np
import pandas as pd
from sqlmodel import Session

from trader.core.config import settings
from trader.integrations import binance
from trader.services import market_data, playbooks
from trader.services.engine import liquidation_distance
from trader.services.playbooks import STOP_BEFORE_LIQ

log = logging.getLogger(__name__)

NAMES = ["agg_trade_id", "price", "quantity", "first_trade_id", "last_trade_id", "transact_time", "is_buyer_maker"]
LATENCIES_S = (0.5, 1, 2, 3, 5, 10, 20, 30, 60)
HOLDS_S = (5, 15, 30, 60, 120, 300, 600, 1800)
BEFORE_S, AFTER_S = 60, 2400


def as_latency(value: float) -> float:
    for latency in LATENCIES_S:
        if float(latency) == float(value):
            return latency
    raise ValueError(f"latency must be one of {LATENCIES_S}, got {value}")


def _day(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, UTC).strftime("%Y-%m-%d")


def window(symbol: str, ts: int) -> pd.DataFrame | None:
    path = settings.data_dir / "ticks" / symbol / f"{ts}.parquet"
    if path.exists():
        df = pd.read_parquet(path)
        return df if len(df) else None
    lo, hi = ts - BEFORE_S * 1000, ts + AFTER_S * 1000
    frames = []
    for day in sorted({_day(lo), _day(hi)}):
        raw = binance._archive_get(f"data/futures/um/daily/aggTrades/{symbol}/{symbol}-aggTrades-{day}.zip")
        if raw is None:
            continue
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            body = archive.read(archive.namelist()[0])
        df = pd.read_csv(io.BytesIO(body), header=None if body[:1].isdigit() else 0, names=NAMES, usecols=["price", "quantity", "transact_time", "is_buyer_maker"])
        del body, raw
        frames.append(df[(df.transact_time >= lo) & (df.transact_time < hi)])
    df = (
        pd.concat(frames, ignore_index=True).sort_values("transact_time", ignore_index=True)
        if frames
        else pd.DataFrame(columns=["price", "quantity", "transact_time", "is_buyer_maker"])
    )
    df["is_buyer_maker"] = df.is_buyer_maker.astype(str).str.lower().eq("true")
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)
    return df if len(df) else None


def clean(df: pd.DataFrame, band: float = 0.3) -> pd.DataFrame:
    if len(df) < 5:
        return df
    median = df.price.rolling(21, center=True, min_periods=3).median()
    return df[(df.price / median - 1).abs() <= band].reset_index(drop=True)


def reactions(df: pd.DataFrame, ts: int, fill_s: float = 0.5) -> dict:
    df = clean(df)
    t = df.transact_time.to_numpy(np.int64)
    p = df.price.to_numpy(np.float64)
    before = np.searchsorted(t, ts) - 1
    if before < 0:
        return {}
    ref = p[before]
    out = {"ref": ref, "first_trade_s": round((t[before + 1] - ts) / 1000, 3) if before + 1 < len(t) else None}
    for latency in LATENCIES_S:
        i = int(np.searchsorted(t, ts + latency * 1000))
        i_end = int(np.searchsorted(t, ts + (latency + fill_s) * 1000, side="right"))
        if i >= len(t):
            continue
        fill = p[i : max(i_end, i + 1)]
        entry_long, entry_short = fill.max(), fill.min()
        out[f"pre_{latency}"] = p[i] / ref - 1
        for hold in HOLDS_S:
            j = int(np.searchsorted(t, ts + (latency + hold) * 1000))
            j_end = int(np.searchsorted(t, ts + (latency + hold + fill_s) * 1000, side="right"))
            if j <= i or j >= len(t):
                continue
            seg = p[i : max(j_end, j + 1)]
            exit_fill = p[j : max(j_end, j + 1)]
            out[f"rl_{latency}_{hold}"] = exit_fill.min() / entry_long - 1
            out[f"rs_{latency}_{hold}"] = exit_fill.max() / entry_short - 1
            out[f"mfel_{latency}_{hold}"] = seg.max() / entry_long - 1
            out[f"mael_{latency}_{hold}"] = seg.min() / entry_long - 1
            out[f"mfes_{latency}_{hold}"] = seg.max() / entry_short - 1
            out[f"maes_{latency}_{hold}"] = seg.min() / entry_short - 1
    return out


def flow(df: pd.DataFrame, ts: int, latency: float) -> dict:
    t = df.transact_time.to_numpy(np.int64)
    p = df.price.to_numpy(np.float64)
    usd = p * df.quantity.to_numpy(np.float64)
    taker_buy = ~df.is_buyer_maker.to_numpy(bool)
    start, now_, before = int(np.searchsorted(t, ts)), int(np.searchsorted(t, ts + latency * 1000, side="right")), int(np.searchsorted(t, ts - 60_000))
    window = slice(start, now_)
    total = float(usd[window].sum())
    rate_before = (start - before) / 60.0
    logret = np.diff(np.log(p[before:start])) if start - before > 2 else np.zeros(1)
    return {
        f"flow_n_{latency}": now_ - start,
        f"flow_usd_{latency}": total,
        f"flow_buy_{latency}": float(usd[window][taker_buy[window]].sum()) / total if total > 0 else 0.5,
        f"flow_accel_{latency}": ((now_ - start) / latency) / (rate_before + 1.0 / 60.0),
        "vol_before": float(logret.std()),
    }


def restudy(fill_s: float = 0.5) -> pd.DataFrame:
    base = pd.read_parquet(settings.reports_dir / "lab" / "tick_reactions.parquet")[["type", "symbol", "ts", "time", "title"]]
    rows = []
    for row in base.itertuples(index=False):
        path = settings.data_dir / "ticks" / row.symbol / f"{row.ts}.parquet"
        if not path.exists():
            continue
        df = pd.read_parquet(path)
        if df.empty:
            continue
        cleaned = clean(df)
        features = {k: v for latency in LATENCIES_S for k, v in flow(cleaned, int(row.ts), latency).items()}
        rows.append(row._asdict() | reactions(df, int(row.ts), fill_s) | features)
    frame = pd.DataFrame(rows).sort_values("ts", ignore_index=True)
    frame.to_parquet(settings.reports_dir / "lab" / "tick_reactions_v2.parquet", index=False)
    return frame


def study(session: Session, workers: int = 6) -> pd.DataFrame:
    events = playbooks.notice_events(session)
    universe = market_data.perp_universe()

    def one(event) -> dict | None:
        etype, token, ts, title = event
        symbol = market_data.perp_symbol(token, universe)
        if symbol is None or ts > (datetime.now(UTC).timestamp() - 3 * 86400) * 1000:
            return None
        try:
            df = window(symbol, ts)
        except Exception as exc:
            log.warning("ticks %s %s: %s", symbol, ts, exc)
            return None
        if df is None or df.transact_time.iloc[0] > ts - 5000:
            return None
        return {"type": etype.value, "symbol": symbol, "ts": ts, "time": datetime.fromtimestamp(ts / 1000, UTC).isoformat(timespec="seconds"), "title": title} | reactions(df, ts)

    with ThreadPoolExecutor(workers) as pool:
        rows = [r for r in pool.map(one, events) if r]
    frame = pd.DataFrame(rows).sort_values("ts", ignore_index=True)
    path = settings.reports_dir / "lab" / "tick_reactions.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False)
    return frame


LEVERAGES = (1.0, 2.0, 3.0, 5.0, 10.0)
CANDIDATES = [
    (side, hold, lev, stop, tp)
    for side, hold, lev, stop, tp in itertools.product((1, -1), HOLDS_S, LEVERAGES, (0.0, 0.02, 0.05, 0.1), (0.0, 0.05, 0.1, 0.2))
    if stop == 0.0 or stop < STOP_BEFORE_LIQ * liquidation_distance(lev, side)
]


def describe(c: tuple) -> str:
    side, hold, lev, stop, tp = c
    return f"{'LONG' if side > 0 else 'SHORT'} {lev:g}x hold {hold}s" + (f" SL {stop:.0%}" if stop else "") + (f" TP {tp:.0%}" if tp else "")


def outcome_matrix(frame: pd.DataFrame, latency: float, fee: float = 0.0005, slip: float | None = None) -> np.ndarray:
    slip = slip if slip is not None else (0.005 if latency < 10 else 0.0015)
    out = np.full((len(frame), len(CANDIDATES)), np.nan)
    for j, (side, hold, lev, stop, tp) in enumerate(CANDIDATES):
        key, leg = f"{latency}_{hold}", "l" if side > 0 else "s"
        if f"r{leg}_{key}" not in frame:
            continue
        r, mfe, mae = (frame[f"{p}{leg}_{key}"].to_numpy(np.float64) for p in ("r", "mfe", "mae"))
        favorable, adverse = (mfe, -mae) if side > 0 else (-mae, mfe)
        stop_hit = (stop > 0) & (adverse >= stop)
        take_hit = (tp > 0) & (favorable >= tp) & ~stop_hit
        liquidated = (adverse >= liquidation_distance(lev, side)) & ~stop_hit
        move = np.where(stop_hit, -stop - slip, np.where(take_hit, tp, side * r))
        out[:, j] = np.maximum(np.where(liquidated, -1.0, lev * (move - 2 * slip - 2 * fee)), -1.0)
    return out


def walk_forward(
    frame: pd.DataFrame, latency: float, z: float = 1.0, min_history: int = 10, slip: float | None = None, top_k: int = 1, select_matrix: np.ndarray | None = None
) -> pd.DataFrame:
    matrix = outcome_matrix(frame, latency, slip=slip)
    chooser = matrix if select_matrix is None else select_matrix
    rows = []
    gap = (max(HOLDS_S) + max(LATENCIES_S)) * 1000
    for etype in sorted(frame.type.unique()):
        idx = np.flatnonzero(frame.type.to_numpy() == etype)
        ts = frame.ts.to_numpy()[idx]
        growth = np.log1p(np.clip(np.nan_to_num(chooser[idx], nan=0.0), -0.99, None))
        zero = np.zeros((1, growth.shape[1]))
        total, total2 = np.vstack([zero, np.cumsum(growth, axis=0)]), np.vstack([zero, np.cumsum(growth**2, axis=0)])
        for k, i in enumerate(idx):
            known = int(np.searchsorted(ts, ts[k] - gap, side="right"))
            picks: list[int] = []
            if known >= min_history:
                mean = total[known] / known
                score = mean - z * np.sqrt(np.maximum(total2[known] - known * mean**2, 0.0) / (known - 1) / known)
                order = np.argsort(-score)[:top_k]
                picks = [int(j) for j in order if score[j] > 0]
            rets = [matrix[i, j] for j in picks if not np.isnan(matrix[i, j])]
            ret = float(np.mean(rets)) if rets else None
            best = picks[0] if picks else None
            rows.append({
                "i": int(i),
                "type": etype,
                "ts": int(frame.ts.iat[i]),
                "symbol": frame.symbol.iat[i],
                "known": known,
                "j": best,
                "candidate": describe(CANDIDATES[best]) if best is not None else None,
                "hold_s": CANDIDATES[best][1] if best is not None else None,
                "lev": max(CANDIDATES[j][2] for j in picks) if picks else None,
                "ret": ret,
            })
    return pd.DataFrame(rows).sort_values("ts", ignore_index=True)


def bucketed(frame: pd.DataFrame, latency: float, threshold: float = 0.02) -> pd.DataFrame:
    pre = frame[f"pre_{latency}"].fillna(0.0)
    bucket = np.where(pre >= threshold, "up", np.where(pre <= -threshold, "down", "flat"))
    return frame.assign(type=frame.type + "|" + bucket)


def latency_report(frame: pd.DataFrame, holdout: str = "2026-07-01", caps: tuple[float | None, ...] = (None, 25_000.0, 10_000.0)) -> dict:
    report = {}
    for latency in LATENCIES_S:
        row = {}
        for variant, data in (("by_type", frame), ("by_type_and_premove", bucketed(frame, latency))):
            decisions = walk_forward(data, latency)
            stamp = pd.to_datetime(decisions.ts, unit="ms", utc=True).dt.strftime("%Y-%m-%d")
            per_type = {}
            for etype, group in decisions.dropna(subset=["ret"]).groupby("type"):
                r = group.ret.to_numpy()
                per_type[etype] = {
                    "n": len(r),
                    "mean": round(float(r.mean()), 4),
                    "median": round(float(np.median(r)), 4),
                    "win": round(float((r > 0).mean()), 3),
                    "last": group.candidate.iloc[-1],
                }
            row[variant] = {"per_type": per_type}
            for cap in caps:
                tag = "uncapped" if cap is None else f"cap{int(cap / 1000)}k"
                row[variant][tag] = {
                    "all": account(decisions, cap_notional=cap),
                    "dev": account(decisions[stamp < holdout], last="2026-06-30", cap_notional=cap),
                    "holdout": account(decisions[stamp >= holdout], first=holdout, cap_notional=cap),
                }
        report[str(latency)] = row
    return report


def meta_filter(frame: pd.DataFrame, decisions: pd.DataFrame, latency: float, threshold: float = 0.5, min_train: int = 60, refit_every: int = 10) -> pd.DataFrame:
    import lightgbm as lgb

    columns = [f"pre_{latency}", f"flow_n_{latency}", f"flow_usd_{latency}", f"flow_buy_{latency}", f"flow_accel_{latency}", "vol_before"]
    types = sorted(frame.type.unique())
    taken = decisions.dropna(subset=["ret"]).sort_values("ts")
    X = frame.loc[taken.i, columns].to_numpy(np.float64)
    X = np.column_stack([X, np.array([types.index(t) for t in frame.loc[taken.i, "type"]])])
    y = (taken.ret.to_numpy() > 0).astype(int)
    ts = taken.ts.to_numpy()
    gap = (max(HOLDS_S) + max(LATENCIES_S)) * 1000
    keep = np.ones(len(taken), dtype=bool)
    model, trained_on = None, -1
    for k in range(len(taken)):
        known = int(np.searchsorted(ts, ts[k] - gap, side="right"))
        if known < min_train:
            continue
        if model is None or known - trained_on >= refit_every:
            model = lgb.LGBMClassifier(n_estimators=150, learning_rate=0.05, num_leaves=7, min_child_samples=10, subsample=0.8, subsample_freq=1, verbose=-1)
            model.fit(X[:known], y[:known], categorical_feature=[X.shape[1] - 1])
            trained_on = known
        keep[k] = model.predict_proba(X[k : k + 1])[0, 1] >= threshold
    out = decisions.copy()
    out.loc[taken.index[~keep], "ret"] = None
    return out


def _iso_ms(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, UTC).isoformat(timespec="milliseconds")


def trade_log(frame: pd.DataFrame, decisions: pd.DataFrame, latency: float, fill_s: float = 0.5) -> pd.DataFrame:
    rows = []
    for d in decisions.dropna(subset=["ret"]).itertuples(index=False):
        side, hold, lev, stop, tp = CANDIDATES[int(d.j)]
        event = frame.iloc[int(d.i)]
        ts = int(event.ts)
        ticks_ = clean(pd.read_parquet(settings.data_dir / "ticks" / event.symbol / f"{ts}.parquet"))
        t, p = ticks_.transact_time.to_numpy(np.int64), ticks_.price.to_numpy(np.float64)
        i0, i1 = int(np.searchsorted(t, ts + latency * 1000)), int(np.searchsorted(t, ts + (latency + fill_s) * 1000, side="right"))
        j0, j1 = int(np.searchsorted(t, ts + (latency + hold) * 1000)), int(np.searchsorted(t, ts + (latency + hold + fill_s) * 1000, side="right"))
        entry_window, exit_window = p[i0 : max(i1, i0 + 1)], p[j0 : max(j1, j0 + 1)]
        k_entry = i0 + int(np.argmax(entry_window) if side > 0 else np.argmin(entry_window))
        k_exit = j0 + int(np.argmin(exit_window) if side > 0 else np.argmax(exit_window))
        path = p[i0 : max(j1, j0 + 1)]
        entry, exit_ = p[k_entry], p[k_exit]
        favorable = path.max() / entry - 1 if side > 0 else 1 - path.min() / entry
        adverse = 1 - path.min() / entry if side > 0 else path.max() / entry - 1
        day = datetime.fromtimestamp(ts / 1000, UTC).strftime("%Y-%m-%d")
        rows.append({
            "announced": _iso_ms(ts),
            "type": event.type,
            "symbol": event.symbol,
            "title": event.title,
            "side": "LONG" if side > 0 else "SHORT",
            "leverage": lev,
            "hold_s": hold,
            "stop": stop,
            "take_profit": tp,
            "entry_time": _iso_ms(int(t[k_entry])),
            "entry_price": entry,
            "exit_time": _iso_ms(int(t[k_exit])),
            "exit_price": exit_,
            "price_move_for_side": side * (exit_ / entry - 1),
            "max_favorable": favorable,
            "max_adverse": adverse,
            "stop_hit": bool(stop > 0 and adverse >= stop),
            "take_profit_hit": bool(tp > 0 and favorable >= tp and not (stop > 0 and adverse >= stop)),
            "liquidated": bool(adverse >= liquidation_distance(lev, side) and not (stop > 0 and adverse >= stop)),
            "ret_on_margin": d.ret,
            "archive": f"https://data.binance.vision/data/futures/um/daily/aggTrades/{event.symbol}/{event.symbol}-aggTrades-{day}.zip",
        })
    return pd.DataFrame(rows)


def _account(decisions: pd.DataFrame, fraction: float, notice_cap: float, capital: float, first: str, last: str, cap_notional: float | None) -> dict:
    from trader.services.xsection import stats

    taken = decisions.dropna(subset=["ret"])
    equity, pnl_by_day = capital, {}
    for ts, group in taken.groupby("ts", sort=True):
        budget = min(fraction, notice_cap / len(group)) * equity
        pnl = 0.0
        for r, lev in zip(group.ret, group.lev, strict=True):
            margin = budget if cap_notional is None else min(budget, cap_notional / lev)
            pnl += margin * max(r, -1.0)
        equity += pnl
        day = datetime.fromtimestamp(ts / 1000, UTC).strftime("%Y-%m-%d")
        pnl_by_day[day] = pnl_by_day.get(day, 0.0) + pnl
    days = pd.date_range(first, last, freq="D").strftime("%Y-%m-%d")
    pnl = pd.Series(0.0, index=days).add(pd.Series(pnl_by_day, dtype="float64"), fill_value=0.0).loc[days]
    eq = capital + pnl.cumsum()
    ret = pnl / eq.shift(1).fillna(capital).clip(lower=1e-9)
    trades = taken.ret.to_numpy()
    return {
        "trades": len(trades),
        "mean_ret": round(float(trades.mean()), 4) if len(trades) else None,
        "median_ret": round(float(np.median(trades)), 4) if len(trades) else None,
        "win": round(float((trades > 0).mean()), 3) if len(trades) else None,
        "mean_daily_usd": round(float(pnl.mean()), 2),
        "share_days_ge_100usd": round(float((pnl >= 100).mean()), 4),
    } | stats(ret, capital)


def account(
    decisions: pd.DataFrame,
    fraction: float = 0.2,
    notice_cap: float = 0.3,
    capital: float = 1000.0,
    first: str = "2021-01-01",
    last: str = "2026-10-20",
    cap_notional: float | None = None,
) -> dict:
    return _account(decisions, fraction, notice_cap, capital, first, last, cap_notional)
