import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime

import numpy as np
import pandas as pd

from trader.core.config import settings
from trader.services import playbooks, ticks
from trader.services.events import EventType

LIVE_LATENCIES = (0.5, 1, 2, 3, 5)


@dataclass(frozen=True)
class FastPlaybook:
    side: int
    hold_s: int
    leverage: float
    stop: float
    take_profit: float

    def describe(self) -> str:
        return ticks.describe((self.side, self.hold_s, self.leverage, self.stop, self.take_profit))


def neighbourhood(latency: float) -> list[float]:
    return [x for x in ticks.LATENCIES_S if latency / 2 <= x <= latency * 2]


def fit(frame: pd.DataFrame, latency: float, z: float = playbooks.LCB_Z, min_history: int = playbooks.MIN_HISTORY) -> dict[str, dict]:
    latency = ticks.as_latency(latency)
    matrix = ticks.outcome_matrix(frame, latency)
    robust = np.nanmean(np.stack([ticks.outcome_matrix(frame, x) for x in neighbourhood(latency)]), axis=0)
    oos = ticks.walk_forward(frame, latency, z=z, min_history=min_history, select_matrix=robust).dropna(subset=["ret"])
    fitted = {}
    for etype in sorted(frame.type.unique()):
        idx = np.flatnonzero(frame.type.to_numpy() == etype)
        if len(idx) < min_history:
            continue
        best, score = playbooks._select(np.log1p(np.clip(np.nan_to_num(robust[idx], nan=0.0), -0.99, None)), z)
        wf = oos[oos.type == etype].ret.to_numpy()
        entry = {"events": len(idx), "score": round(score, 4), "oos_trades": len(wf), "oos_mean_ret": round(float(wf.mean()), 4) if len(wf) else None}
        if best is None or len(wf) < min_history or wf.mean() <= 0:
            fitted[etype] = entry | {"playbook": None}
            continue
        side, hold, lev, stop, tp = ticks.CANDIDATES[best]
        col = np.nan_to_num(matrix[idx, best])
        fitted[etype] = entry | {
            "playbook": asdict(FastPlaybook(side, hold, lev, stop, tp)),
            "describe": ticks.describe(ticks.CANDIDATES[best]),
            "in_sample_mean_ret": round(float(col.mean()), 4),
            "in_sample_win_rate": round(float((col > 0).mean()), 3),
        }
    return fitted


def fit_all(frame: pd.DataFrame, latencies: tuple[float, ...] = LIVE_LATENCIES) -> dict[str, dict[str, dict]]:
    return {str(latency): fit(frame, latency) for latency in latencies}


def _path():
    return settings.data_dir / "fast_playbooks.json"


def save(by_latency: dict[str, dict[str, dict]]) -> None:
    _path().parent.mkdir(parents=True, exist_ok=True)
    _path().write_text(json.dumps({"fitted_at": datetime.now(UTC).isoformat(timespec="seconds"), "by_latency": by_latency}, indent=2) + "\n")


def saved() -> dict:
    return json.loads(_path().read_text()) if _path().exists() else {}


def live() -> dict[EventType, list[tuple[float, FastPlaybook]]]:
    return to_live(saved().get("by_latency", {}))


def to_live(by_latency: dict[str, dict[str, dict]]) -> dict[EventType, list[tuple[float, FastPlaybook]]]:
    out: dict[EventType, list[tuple[float, FastPlaybook]]] = {}
    for latency, types in by_latency.items():
        for etype, entry in types.items():
            if entry.get("playbook"):
                out.setdefault(EventType(etype), []).append((float(latency), FastPlaybook(**entry["playbook"])))
    return {k: sorted(v, key=lambda x: x[0]) for k, v in out.items()}


def for_latency(options: list[tuple[float, FastPlaybook]], seen_after_s: float) -> FastPlaybook | None:
    return next((pb for latency, pb in options if seen_after_s <= latency), None)
