import itertools
import json
import logging
import math
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from trader.core.config import settings
from trader.services import playbooks, universe
from trader.services.engine import Costs, liquidation_distance
from trader.services.events import EventType
from trader.services.playbooks import STOP_BEFORE_LIQ, Decision, Playbook

log = logging.getLogger(__name__)

DEV_START = "2022-02-01"
HOLDOUT = "2026-07-01"
END = "2026-09-30"


def _grid_1h() -> list[Playbook]:
    combos = itertools.product((1, -1), (0, 1, 3, 6), (0.05, 0.1, 0.2, 0.35), (0.0, 0.1, 0.2, 0.4), (0.0, 0.1), (1, 4, 8, 16, 23), (1.0, 2.0, 3.0, 5.0))
    return [Playbook(*c) for c in combos if c[1] + c[5] <= 24 and c[2] <= STOP_BEFORE_LIQ * liquidation_distance(c[6], c[0])]


GRID_1H = _grid_1h()


def lab_dir() -> Path:
    path = settings.reports_dir / "lab"
    path.mkdir(parents=True, exist_ok=True)
    return path


def save(name: str, doc: dict | list) -> None:
    (lab_dir() / f"{name}.json").write_text(json.dumps(doc, indent=1, default=str, ensure_ascii=False) + "\n")


def load_decisions(name: str) -> list[Decision]:
    path = lab_dir() / f"{name}.json"
    rows = json.loads(path.read_text()) if path.exists() else []
    return [Decision(**r) for r in rows]


def news_decisions() -> list[Decision]:
    path = settings.reports_dir / "event_research.json"
    return [Decision(**r) for r in json.loads(path.read_text())["decisions"]] if path.exists() else []


def daily(trades: list[dict], capital: float = 1000.0, first: str = DEV_START, last: str = HOLDOUT) -> dict:
    days = pd.date_range(first, last, freq="D", inclusive="left").strftime("%Y-%m-%d")
    pnl = pd.Series(0.0, index=days)
    for t in trades:
        day = t["exit_time"][:10]
        if day in pnl.index:
            pnl[day] += t["pnl"]
    equity = capital + pnl.cumsum()
    ret = pnl / equity.shift(1).fillna(capital).clip(lower=1e-9)
    curve = np.concatenate([[capital], equity.to_numpy()])
    final = float(equity.iloc[-1]) if len(equity) else capital
    std = float(ret.std()) if len(ret) > 1 else 0.0
    return {
        "days": len(ret),
        "final_equity": round(final, 2),
        "geo_daily_pct": round(((final / capital) ** (1 / max(len(ret), 1)) - 1) * 100, 4) if final > 0 else -100.0,
        "mean_daily_pct": round(float(ret.mean()) * 100, 4),
        "median_daily_pct": round(float(ret.median()) * 100, 4),
        "sharpe_annual": round(float(ret.mean()) / std * math.sqrt(365), 2) if std > 0 else None,
        "share_days_positive": round(float((ret > 0).mean()), 3),
        "share_days_ge_10pct": round(float((ret >= 0.1).mean()), 4),
        "share_days_le_minus_10pct": round(float((ret <= -0.1).mean()), 4),
        "best_day_pct": round(float(ret.max()) * 100, 2),
        "worst_day_pct": round(float(ret.min()) * 100, 2),
        "max_drawdown_pct": round(float((curve / np.maximum.accumulate(curve) - 1).min()) * 100, 2),
    }


def account(decisions: list[Decision], fraction: float = 0.2, max_open: int = 5, notice_cap: float = 0.3, first: str = DEV_START, last: str = HOLDOUT) -> dict:
    chosen = [d for d in decisions if first <= d.time < last]
    run = playbooks.replay_account(chosen, "fraction", fraction=fraction, max_open=max_open, notice_cap=notice_cap)
    return {"trades": len(run.trades), "skipped": run.skipped, "win_rate": run.summary["win_rate"]} | daily(run.trades, first=first, last=last)


def _stats(r: list[float]) -> dict:
    if not r:
        return {"n": 0}
    a = np.asarray(r)
    sd = float(a.std(ddof=1)) if len(a) > 1 else 0.0
    return {
        "n": len(a),
        "mean": round(float(a.mean()), 4),
        "median": round(float(np.median(a)), 4),
        "win": round(float((a > 0).mean()), 3),
        "t": round(float(a.mean()) / (sd / math.sqrt(len(a))), 2) if sd > 0 else None,
        "sum_on_1000": round(float(a.sum()) * 1000),
    }


def per_type(decisions: list[Decision]) -> dict:
    out = {}
    for etype in sorted({d.type for d in decisions}):
        ds = [d for d in decisions if d.type == etype]
        taken = [(d.time, float(d.ret)) for d in ds if d.ret is not None]
        out[etype] = {
            "events": len(ds),
            "dev": _stats([r for t, r in taken if t < HOLDOUT]),
            "holdout": _stats([r for t, r in taken if t >= HOLDOUT]),
            "last_playbook": next((Playbook(**d.playbook).describe() for d in reversed(ds) if d.playbook), None),
        }
    return out


def scan(types: set[EventType] | None = None, z: float = playbooks.LCB_Z, name: str = "scan", costs: Costs | None = None) -> dict:
    panel = universe.load()
    events = universe.detect(panel, types)
    samples = universe.samples(panel, events)
    log.info("%d events, %d samples, grid %d", len(events), len(samples), len(GRID_1H))
    out = playbooks.evaluate(samples, GRID_1H, costs or Costs.for_events())
    decisions = playbooks.walk_forward(samples, out, GRID_1H, z)
    save(f"{name}_decisions", [asdict(d) for d in decisions])
    by_type = per_type(decisions)
    doc = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "symbols": len(panel),
        "events": len(events),
        "samples": len(samples),
        "z": z,
        "per_type": by_type,
        "dev_accounts": {t: account([d for d in decisions if d.type == t]) for t in by_type},
        "holdout_accounts": {t: account([d for d in decisions if d.type == t], first=HOLDOUT, last=END) for t in by_type},
    }
    save(name, doc)
    return doc


def combine(groups: dict[str, list[Decision]], fractions=(0.1, 0.2, 0.35, 0.5), max_opens=(5, 10, 20), first: str = DEV_START, last: str = HOLDOUT) -> dict:
    merged = sorted((d for ds in groups.values() for d in ds), key=lambda d: d.time)
    return {f"f{f}_open{m}": account(merged, fraction=f, max_open=m, first=first, last=last) for f in fractions for m in max_opens}
