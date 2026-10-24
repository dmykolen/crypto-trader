import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from trader.core.config import settings
from trader.integrations import binance
from trader.quant import features, model, research, sim
from trader.quant.sim import Bars
from trader.services import market_data

HOUR = 3_600_000
WARMUP = timedelta(days=45)
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


def _explain(booster, x: pd.DataFrame, names: list[str], k: int, top: int = 4) -> list[str]:
    contrib = booster.predict(x.iloc[[k]], pred_contrib=True)[0][:-1]
    order = np.argsort(-np.abs(contrib))[:top]
    return [f"{names[j]}={x.iloc[k, j]:.3g} ({contrib[j]:+.3f}R)" for j in order]


def replay(symbol: str, day: datetime | None = None, csv: Path | None = None, theta: float | None = None, capital: float = 1000.0) -> dict:
    g = model.geometry()
    now = datetime.now(UTC)
    if csv is not None:
        bars = from_csv(csv)
        last = _dt(int(bars.open_time.max()))
        day = day or datetime(last.year, last.month, last.day, tzinfo=UTC)
    else:
        day = day or datetime(now.year, now.month, now.day, tzinfo=UTC) - timedelta(days=1)
        bars = quotes(symbol, day - WARMUP, min(day + timedelta(days=1, hours=g.horizon + 1), now - timedelta(minutes=1)))
    span = (_dt(int(bars.open_time.min())), _dt(int(bars.open_time.max())) + timedelta(hours=1))
    try:
        btc = bars if symbol == "BTCUSDT" and csv is None else quotes("BTCUSDT", *span)
    except Exception:
        btc = None
    f = features.frame(bars, btc)
    lo, hi = _ms(day), _ms(day) + 24 * HOUR
    long_m, short_m, trained, tag = model.model_for(lo)
    policy = research.chosen_policy(tag)
    if theta is not None:
        policy = replace(policy, theta=theta, theta_long=None, theta_short=None)
    th_long, th_short = policy.thresholds()
    names = long_m.feature_name()
    x = f.reindex(columns=names)
    decide = (f.index >= lo - HOUR) & (f.index < hi - HOUR)
    if not decide.any():
        raise ValueError(f"no quotes for {symbol} on {day:%Y-%m-%d}")
    xd = x[decide]
    pl, ps = long_m.predict(xd), short_m.predict(xd)
    preds = pd.DataFrame({"symbol": symbol, "open_time": f.index[decide], "pred_long": pl, "pred_short": ps})
    c = bars.close.to_numpy(np.float64)
    sb = Bars(
        bars.open_time.to_numpy(np.int64),
        bars.open.to_numpy(np.float64),
        bars.high.to_numpy(np.float64),
        bars.low.to_numpy(np.float64),
        c,
        f.atr_pct.to_numpy(np.float64) * c,
        bars.get("funding", pd.Series(0.0, index=bars.index)).fillna(0.0).to_numpy(np.float64),
    )
    last_t = int(bars.open_time.max())
    result = sim.simulate(preds, {symbol: sb}, g, policy, lo, min(hi + g.horizon * HOUR, last_t + HOUR), capital)
    opened = set(result.trades.entry_time.astype(int)) if len(result.trades) else set()
    close_at = dict(zip(bars.open_time.to_numpy(np.int64).tolist(), c.tolist(), strict=True))
    hours = []
    for k, t in enumerate(preds.open_time.to_numpy()):
        side, edge, booster = ("LONG", pl[k] - th_long, long_m) if pl[k] - th_long >= ps[k] - th_short else ("SHORT", ps[k] - th_short, short_m)
        entered = int(t) + HOUR in opened
        action = f"OPEN {side}" if entered else (f"signal {side}, not taken" if edge > 0 else "wait")
        hours.append({
            "bar": _dt(int(t) + HOUR).strftime("%H:%M"),
            "close": close_at.get(int(t)),
            "expected_r_long": round(float(pl[k]), 3),
            "expected_r_short": round(float(ps[k]), 3),
            "action": action,
            "why": _explain(booster, xd, names, k) if edge > 0 else [],
        })
    trades = []
    for r in result.trades.to_dict("records"):
        trades.append({
            **{k: r[k] for k in ("side", "entry", "exit", "leverage", "reason")},
            "entry_time": _dt(r["entry_time"]).strftime("%Y-%m-%d %H:%M"),
            "exit_time": _dt(r["exit_time"]).strftime("%Y-%m-%d %H:%M"),
            "margin": round(r["margin"], 2),
            "notional": round(r["notional"], 2),
            "pnl": round(r["pnl"], 2),
            "r": round(r["r"], 2),
            "stop": r["stop"],
            "take": r["take"],
        })
    pnl = float(result.trades.pnl.sum()) if len(result.trades) else 0.0
    doc = {
        "symbol": symbol,
        "day": f"{day:%Y-%m-%d}",
        "source": str(csv) if csv else "Binance USDⓈ-M 1h klines",
        "model": trained,
        "policy": policy.describe(),
        "summary": {
            "start_equity": capital,
            "trades": len(trades),
            "winners": sum(t["pnl"] > 0 for t in trades),
            "pnl": round(pnl, 2),
            "return_pct": round(100 * pnl / capital, 2),
            "day_move_pct": round(100 * (c[np.searchsorted(bars.open_time.to_numpy(), hi - HOUR)] / c[max(np.searchsorted(bars.open_time.to_numpy(), lo) - 1, 0)] - 1), 2)
            if hi - HOUR <= last_t
            else None,
        },
        "trades": trades,
        "hours": hours,
    }
    out = settings.reports_dir / "quant" / "day"
    out.mkdir(parents=True, exist_ok=True)
    stem = f"{symbol}_{day:%Y-%m-%d}"
    doc["report"], doc["chart"] = str(out / f"{stem}.md"), str(out / f"{stem}.html")
    (out / f"{stem}.json").write_text(json.dumps(doc, indent=2, default=str))
    (out / f"{stem}.md").write_text(markdown(doc))
    view = bars[(bars.open_time >= lo - 12 * HOUR) & (bars.open_time < max([hi] + [int(r["exit_time"]) + 2 * HOUR for r in result.trades.to_dict("records")]))]
    (out / f"{stem}.html").write_text(chart(doc, view, result.trades))
    return doc


def markdown(doc: dict) -> str:
    s = doc["summary"]
    lines = [
        f"# Бот «Квант» на {doc['symbol']} за {doc['day']}",
        "",
        f"Котирування: {doc['source']}. Модель: {doc['model']}. Політика: {doc['policy']}.",
        "",
        f"**Угод: {s['trades']}, прибуткових: {s['winners']}, P&L: ${s['pnl']:+,.2f} ({s['return_pct']:+.2f}% від ${s['start_equity']:,.0f}).**",
        f"Рух ціни за день: {s['day_move_pct']}%.",
        "",
    ]
    if doc["trades"]:
        lines += ["| вхід (UTC) | сторона | плече | маржа | вхід | вихід (UTC) | вихід | причина | P&L | R |", "|---|---|---|---|---|---|---|---|---|---|"]
        for t in doc["trades"]:
            cells = [t["entry_time"], t["side"], f"{t['leverage']:g}x", f"${t['margin']:,.0f}", f"{t['entry']:.6g}", t["exit_time"], f"{t['exit']:.6g}", t["reason"]]
            lines.append("| " + " | ".join([*cells, f"${t['pnl']:+,.2f}", f"{t['r']:+.2f}"]) + " |")
    lines += ["", "## Що бот бачив щогодини", "", "| бар (UTC) | очікуване R лонг | очікуване R шорт | рішення | чому (внесок ознак) |", "|---|---|---|---|---|"]
    for h in doc["hours"]:
        lines.append(f"| {h['bar']} | {h['expected_r_long']:+.3f} | {h['expected_r_short']:+.3f} | {h['action']} | {'; '.join(h['why'])} |")
    return "\n".join(lines) + "\n"


def chart(doc: dict, view: pd.DataFrame, trades: pd.DataFrame) -> str:
    if view.empty:
        return "<p>no bars</p>"
    w, h, pad = 760, 300, 46
    t = view.open_time.to_numpy()
    lo_p, hi_p = float(view.low.min()), float(view.high.max())
    span = (hi_p - lo_p) or hi_p * 0.01
    lo_p, hi_p = lo_p - span * 0.05, hi_p + span * 0.05
    step = (w - pad - 10) / len(view)

    def x(ms: float) -> float:
        return pad + (float(ms) - t[0]) / HOUR * step + step / 2

    def y(p: float) -> float:
        return 10 + (h - 40) * (1 - (p - lo_p) / (hi_p - lo_p))

    parts = [f'<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}">']
    for frac in (0.0, 0.5, 1.0):
        p = lo_p + (hi_p - lo_p) * frac
        parts.append(f'<line x1="{pad}" x2="{w - 10}" y1="{y(p):.1f}" y2="{y(p):.1f}" stroke="var(--border)"/>')
        parts.append(f'<text x="{pad - 4}" y="{y(p) + 4:.1f}" font-size="10" text-anchor="end" fill="var(--muted-foreground)">{p:.5g}</text>')
    day_lo = x(_ms(datetime.fromisoformat(doc["day"]).replace(tzinfo=UTC))) - step / 2
    parts.append(f'<rect x="{day_lo:.1f}" y="10" width="{min(24 * step, w - 10 - day_lo):.1f}" height="{h - 40}" fill="var(--accent)" opacity="0.06"/>')
    for r in view.itertuples(index=False):
        color = "#16a34a" if r.close >= r.open else "#dc2626"
        cx = x(r.open_time)
        parts.append(f'<line x1="{cx:.1f}" x2="{cx:.1f}" y1="{y(r.high):.1f}" y2="{y(r.low):.1f}" stroke="{color}"/>')
        top, bottom = y(max(r.open, r.close)), y(min(r.open, r.close))
        parts.append(f'<rect x="{cx - step * 0.35:.1f}" y="{top:.1f}" width="{step * 0.7:.1f}" height="{max(bottom - top, 1):.1f}" fill="{color}"/>')
    for r in trades.to_dict("records") if len(trades) else []:
        x0, x1 = x(r["entry_time"]), x(r["exit_time"])
        up = r["side"] == "LONG"
        parts.append(f'<line x1="{x0:.1f}" x2="{x1:.1f}" y1="{y(r["stop"]):.1f}" y2="{y(r["stop"]):.1f}" stroke="#dc2626" stroke-dasharray="4 3"/>')
        parts.append(f'<line x1="{x0:.1f}" x2="{x1:.1f}" y1="{y(r["take"]):.1f}" y2="{y(r["take"]):.1f}" stroke="#16a34a" stroke-dasharray="4 3"/>')
        ye = y(r["entry"])
        tri = f"{x0:.1f},{ye + (8 if up else -8):.1f} {x0 - 6:.1f},{ye + (16 if up else -16):.1f} {x0 + 6:.1f},{ye + (16 if up else -16):.1f}"
        parts.append(f'<polygon points="{tri}" fill="var(--accent)"/>')
        parts.append(f'<circle cx="{x1:.1f}" cy="{y(r["exit"]):.1f}" r="5" fill="{"#16a34a" if r["pnl"] > 0 else "#dc2626"}" stroke="var(--foreground)"/>')
    parts.append(f'<text x="{pad}" y="{h - 8}" font-size="10" fill="var(--muted-foreground)">{_dt(int(t[0])):%d.%m %H:%M}</text>')
    parts.append(f'<text x="{w - 10}" y="{h - 8}" font-size="10" text-anchor="end" fill="var(--muted-foreground)">{_dt(int(t[-1])):%d.%m %H:%M} UTC</text>')
    parts.append("</svg>")
    s = doc["summary"]
    tone = "#16a34a" if s["pnl"] > 0 else ("#dc2626" if s["pnl"] < 0 else "inherit")
    title = f'<b>{doc["symbol"]} · {doc["day"]}</b> — угод: {s["trades"]}, P&amp;L: <b style="color:{tone}">${s["pnl"]:+,.2f}</b> ({s["return_pct"]:+.2f}%)'
    head = f'<p style="font-size:13px;margin:0 0 6px">{title}, рух ціни за день {s["day_move_pct"]}%</p>'
    legend = (
        '<p style="font-size:11px;color:var(--muted-foreground);margin:4px 0 0">'
        "▲ вхід · ● вихід (зелений — прибуток) · пунктир: стоп (червоний) і тейк (зелений) · підсвічено обраний день</p>"
    )
    return head + "".join(parts) + legend
