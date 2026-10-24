import json
from dataclasses import asdict
from datetime import UTC, datetime
from itertools import pairwise, product

import numpy as np
import pandas as pd

from trader.core.config import settings
from trader.quant import model, sim
from trader.quant.sim import Bars, Policy

DEV_END = int(datetime(2025, 1, 1, tzinfo=UTC).timestamp() * 1000)


def oos_window() -> tuple[int, int]:
    q = model.quarters()
    return q[0][0], q[-1][1]


def load_bars(symbols) -> dict[str, Bars]:
    folder = model.root() / "bars"
    return {s: Bars.of(pd.read_parquet(folder / f"{s}.parquet")) for s in symbols if (folder / f"{s}.parquet").exists()}


def calibration(preds: pd.DataFrame) -> dict:
    out = {}
    month = pd.to_datetime(preds.open_time, unit="ms", utc=True).dt.strftime("%Y-%m")
    for side in ("long", "short"):
        p, y = preds[f"pred_{side}"].to_numpy(), np.clip(preds[f"y_{side}"].to_numpy(), -3, 3)
        ok = np.isfinite(p) & np.isfinite(y)
        frame = pd.DataFrame({"p": p[ok], "y": y[ok], "m": month[ok].to_numpy(), "dev": preds.open_time.to_numpy()[ok] < DEV_END})
        frame["decile"] = pd.qcut(frame.p.rank(method="first"), 10, labels=False)
        ic = frame.groupby("m").apply(lambda g: g.p.corr(g.y, method="spearman"), include_groups=False)
        top = frame.p > np.quantile(frame.p, 0.99)
        out[side] = {
            "deciles_mean_r": frame.groupby("decile").y.mean().round(4).tolist(),
            "monthly_ic_mean": round(float(ic.mean()), 4),
            "monthly_ic_t": round(float(ic.mean() / ic.std() * np.sqrt(len(ic))), 2),
            "months_ic_positive": f"{int((ic > 0).sum())}/{len(ic)}",
            "top1pct_mean_r_dev": round(float(frame.y[top & frame.dev].mean()), 4),
            "top1pct_mean_r_holdout": round(float(frame.y[top & ~frame.dev].mean()), 4),
            "base_mean_r": round(float(frame.y.mean()), 4),
            "by_threshold": {
                f"{th:g}": {
                    "n": int((frame.p > th).sum()),
                    "mean_r_dev": round(float(frame.y[(frame.p > th) & frame.dev].mean()), 4),
                    "mean_r_holdout": round(float(frame.y[(frame.p > th) & ~frame.dev].mean()), 4),
                }
                for th in (0.0, 0.05, 0.1, 0.15, 0.2, 0.3, 0.4, 0.5)
            },
        }
    return out


QUANTILES = (0.97, 0.99, 0.995)


def grid() -> list[Policy]:
    return [Policy(theta=q, quantile=q, side=side, max_positions=m, risk=r, gate=True) for side, q, m, r in product(("both", "short", "long"), QUANTILES, (10, 20), (0.005, 0.01))]


def ranked(preds: pd.DataFrame) -> pd.DataFrame:
    out = preds.copy()
    t = preds.open_time.to_numpy()
    for side in ("long", "short"):
        values = preds[f"pred_{side}"].to_numpy()
        ranks = np.full(len(preds), np.nan, dtype=np.float32)
        for (plo, phi), (lo, hi) in pairwise(model.quarters()):
            ref = np.sort(values[(t >= plo) & (t < phi)])
            here = (t >= lo) & (t < hi)
            if len(ref) and here.any():
                ranks[here] = np.searchsorted(ref, values[here]) / len(ref)
        out[f"pred_{side}"] = ranks
    return out


def absolute_thresholds(preds: pd.DataFrame, q: float) -> dict[str, dict[str, float]]:
    t = preds.open_time.to_numpy()
    quarters = model.quarters()
    out = {}
    for (plo, phi), (lo, _) in pairwise(quarters):
        ref = (t >= plo) & (t < phi)
        out[str(lo)] = {side: float(np.quantile(preds[f"pred_{side}"].to_numpy()[ref], q)) for side in ("long", "short")}
    last = (t >= quarters[-1][0]) & (t < quarters[-1][1])
    out["final"] = {side: float(np.quantile(preds[f"pred_{side}"].to_numpy()[last], q)) for side in ("long", "short")}
    return out


def _brief(r: sim.Result) -> dict:
    keys = (
        "final_equity",
        "return_pct",
        "geo_daily_pct",
        "mean_daily_pct",
        "sharpe",
        "max_drawdown_pct",
        "positive_days_pct",
        "days_10pct_plus",
        "trades",
        "win_rate",
        "mean_r",
        "liquidations",
    )
    return {k: r.stats.get(k) for k in keys}


def evaluate() -> dict:
    raw = pd.read_parquet(model.root() / "predictions.parquet")
    preds = ranked(raw)
    bars = load_bars(raw.symbol.unique())
    g = model.geometry()
    first, last = model.quarters()[1][0], model.quarters()[-1][1]
    doc: dict = {
        "geometry": asdict(g),
        "oos": [str(datetime.fromtimestamp(first / 1000, UTC).date()), str(datetime.fromtimestamp(last / 1000, UTC).date())],
        "dev_end": "2025-01-01",
    }
    doc["calibration"] = calibration(raw)
    runs = []
    for p in grid():
        r = sim.simulate(preds, bars, g, p, first, DEV_END)
        runs.append((p, r))
    eligible = [(p, r) for p, r in runs if r.stats.get("trades", 0) >= 50 and r.stats.get("max_drawdown_pct", -100) > -60]
    best_p, best_dev = max(eligible or runs, key=lambda x: x[1].stats.get("sharpe", -99))
    holdout = sim.simulate(preds, bars, g, best_p, DEV_END, last)
    full = sim.simulate(preds, bars, g, best_p, first, last)
    doc["grid_dev"] = [{"policy": p.describe(), **_brief(r)} for p, r in runs]
    doc["grid_holdout"] = [
        {"policy": p.describe(), **_brief(sim.simulate(preds, bars, g, p, DEV_END, last))} for p, _ in sorted(runs, key=lambda x: -x[1].stats.get("sharpe", -99))[:8]
    ]
    doc["chosen"] = {"policy": asdict(best_p), "describe": best_p.describe(), "dev": best_dev.stats, "holdout": holdout.stats, "full_oos": full.stats}
    if len(full.trades):
        tr = full.trades.assign(month=pd.to_datetime(full.trades.exit_time, unit="ms", utc=True).dt.strftime("%Y-%m"))
        doc["chosen"]["by_month_pnl"] = tr.groupby("month").pnl.sum().round(2).to_dict()
        by_sym = tr.groupby("symbol").agg(trades=("pnl", "size"), pnl=("pnl", "sum"), mean_r=("r", "mean")).sort_values("pnl")
        doc["chosen"]["worst_symbols"] = by_sym.head(10).round(3).reset_index().to_dict("records")
        doc["chosen"]["best_symbols"] = by_sym.tail(10).round(3).reset_index().to_dict("records")
        doc["chosen"]["by_reason"] = tr.groupby("reason").agg(n=("pnl", "size"), pnl=("pnl", "sum")).round(2).reset_index().to_dict("records")
        full.trades.to_parquet(model.root() / "trades_oos.parquet", index=False)
    full.equity.to_frame().to_parquet(model.root() / "equity_oos.parquet")
    (model.root() / "policy.json").write_text(json.dumps(asdict(best_p), indent=2))
    (model.root() / "thresholds.json").write_text(json.dumps(absolute_thresholds(raw, best_p.quantile or 0.99), indent=2))
    out = settings.reports_dir / "quant"
    out.mkdir(parents=True, exist_ok=True)
    (out / "research.json").write_text(json.dumps(doc, indent=2, default=str))
    (out / "research.md").write_text(markdown(doc))
    return doc


def chosen_policy(tag: str | None = None) -> Policy:
    path = model.root() / "policy.json"
    policy = Policy(**json.loads(path.read_text())) if path.exists() else Policy()
    table = model.root() / "thresholds.json"
    if tag is not None and policy.quantile is not None and table.exists():
        found = json.loads(table.read_text()).get(tag)
        if found:
            policy = Policy(**{**asdict(policy), "theta_long": found["long"], "theta_short": found["short"]})
    return policy


def markdown(doc: dict) -> str:
    c = doc["chosen"]
    lines = [
        "# Бот №2 «Квант»: walk-forward дослідження",
        "",
        f"Модель: LightGBM на ~135 ознаках (індикатори, математика, патерни, контекст BTC), мітки — потрійний бар'єр ({doc['geometry']}).",
        f"Позавибірковий період: {doc['oos'][0]} → {doc['oos'][1]}; політику обрано на {doc['oos'][0]} → {doc['dev_end']}, перевірено на {doc['dev_end']} → {doc['oos'][1]}.",
        "",
        "## Чи бачить модель щось (калібрування на нових даних)",
        "",
        "| сторона | середнє R по децилях прогнозу (1 → 10) | IC/міс | t | міс. з IC>0 | топ-1% R dev | топ-1% R holdout | база |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for side, cal in doc["calibration"].items():
        deciles = " ".join(f"{x:+.2f}" for x in cal["deciles_mean_r"])
        cells = [
            side,
            deciles,
            f"{cal['monthly_ic_mean']:+.3f}",
            str(cal["monthly_ic_t"]),
            cal["months_ic_positive"],
            f"{cal['top1pct_mean_r_dev']:+.3f}",
            f"{cal['top1pct_mean_r_holdout']:+.3f}",
            f"{cal['base_mean_r']:+.3f}",
        ]
        lines.append("| " + " | ".join(cells) + " |")
    lines += [
        "",
        f"## Обрана політика: {c['describe']}",
        "",
        "| період | капітал | дохід | сер. день | Sharpe | макс. DD | днів ≥ +10% | угод | win | сер. R |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for name, s in (("dev", c["dev"]), ("holdout", c["holdout"]), ("весь OOS", c["full_oos"])):
        cells = [
            name,
            f"${s.get('final_equity', 0):,.0f}",
            f"{s.get('return_pct', 0):+.1f}%",
            f"{s.get('mean_daily_pct', 0):+.3f}%",
            str(s.get("sharpe", 0)),
            f"{s.get('max_drawdown_pct', 0)}%",
        ]
        cells += [str(s.get("days_10pct_plus", 0)), str(s.get("trades", 0)), str(s.get("win_rate", 0)), str(s.get("mean_r", 0))]
        lines.append("| " + " | ".join(cells) + " |")
    lines += ["", "## Топ-8 політик dev → їхній holdout", "", "| політика | holdout капітал | holdout Sharpe | holdout DD | угод |", "|---|---|---|---|---|"]
    for row in doc["grid_holdout"]:
        lines.append(f"| {row['policy']} | ${row['final_equity'] or 0:,.0f} | {row['sharpe']} | {row['max_drawdown_pct']}% | {row['trades']} |")
    return "\n".join(lines) + "\n"
