"""Background jobs for the web UI — historical tests and retraining, each run as its own `trader job run <id>` process.

A job is a JSON file under `data/jobs/`: the request, its state, and the chart-ready result. The API creates it and
spawns the runner; the runner writes progress and the result back, so jobs survive page reloads and server restarts.
"""

import asyncio
import json
import os
import secrets
import signal
import subprocess
import sys
import traceback
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field, field_validator

from trader.core.config import settings

DAY = 86_400_000
MAIN_RANGE = ("2023-07-01", "2026-10-01")
PRE_RANGE = ("2021-07-01", "2023-07-01")


class QuantPeriod(BaseModel):
    start: date = date(2025, 1, 1)
    end: date = date(2026, 9, 30)
    capital: float = Field(default=1000.0, gt=0)
    gross: float = Field(default=2.0, gt=0, le=6)
    per_side: int = Field(default=30, ge=5, le=100)
    short_cap: float = Field(default=0.04, gt=0, le=1)
    band: float = Field(default=0.01, ge=0, le=0.1)
    beta_days: int = Field(default=60, ge=0, le=365)
    family: Literal["blend", "edge", "xs7"] = "blend"

    @field_validator("end")
    @classmethod
    def _order(cls, end: date, info) -> date:
        start = info.data.get("start")
        if start and end <= start:
            raise ValueError("end must be after start")
        return end


class QuantForward(BaseModel):
    start: date
    end: date | None = None
    capital: float = Field(default=1000.0, gt=0)


class QuantBook(BaseModel):
    day: date


class NoticeReplay(BaseModel):
    day: date
    days: int = Field(default=1, ge=1, le=90)


class QuantRetrain(BaseModel):
    skip_download: bool = False


class QuantEvidence(BaseModel):
    pass


class QuantDay(BaseModel):
    symbol: str = Field(pattern=r"^[A-Z0-9]{2,24}$")
    day: date | None = None
    days: int = Field(default=1, ge=1, le=30)
    leverage: float | None = Field(default=None, gt=0, le=20)
    upload: str | None = Field(default=None, pattern=r"^[0-9a-f]{16}$")


KINDS: dict[str, type[BaseModel]] = {
    "quant_period": QuantPeriod,
    "quant_forward": QuantForward,
    "quant_book": QuantBook,
    "notice_replay": NoticeReplay,
    "quant_retrain": QuantRetrain,
    "quant_evidence": QuantEvidence,
    "quant_day": QuantDay,
}
TITLES = {
    "quant_period": "Квант: період на історії",
    "quant_forward": "Квант: форвард-тест на свіжих котируваннях",
    "quant_book": "Квант: книга за день",
    "notice_replay": "Анонси: реплей днів",
    "quant_retrain": "Квант: перенавчання моделей",
    "quant_evidence": "Квант: перебудова доказів 2021–2026",
    "quant_day": "Пара за день: 305 тактик",
}


class JobError(RuntimeError):
    pass


def uploads_dir() -> Path:
    return settings.data_dir / "uploads"


def jobs_dir() -> Path:
    return settings.data_dir / "jobs"


def _path(job_id: str) -> Path:
    if not job_id.replace("-", "").isalnum():
        raise JobError("bad job id")
    return jobs_dir() / f"{job_id}.json"


def _write(doc: dict) -> None:
    jobs_dir().mkdir(parents=True, exist_ok=True)
    tmp = _path(doc["id"]).with_suffix(".tmp")
    tmp.write_text(json.dumps(clean(doc), default=_json, ensure_ascii=False, allow_nan=False))
    tmp.replace(_path(doc["id"]))


def clean(value):
    """JSON the browser can parse: NaN and infinities become null, numpy scalars plain numbers."""
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, (float, np.floating)):
        return float(value) if np.isfinite(value) else None
    return value


def _json(value):
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return None if not np.isfinite(value) else float(value)
    if isinstance(value, (datetime, date, pd.Timestamp)):
        return value.isoformat()
    return str(value)


def get(job_id: str) -> dict:
    path = _path(job_id)
    if not path.exists():
        raise JobError(f"job {job_id} not found")
    doc = json.loads(path.read_text())
    if doc["status"] in ("queued", "running") and doc.get("pid") and not _alive(doc["pid"]):
        doc.update({"status": "failed", "error": "the job process exited without a result", "finished_at": _now()})
        _write(doc)
    return doc


def listing(limit: int = 50) -> list[dict]:
    if not jobs_dir().exists():
        return []
    docs = []
    for path in sorted(jobs_dir().glob("*.json"), reverse=True)[:limit]:
        doc = get(path.stem)
        doc.pop("result", None)
        docs.append(doc)
    return docs


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def create(kind: str, params: dict, spawn: bool = True) -> dict:
    if kind not in KINDS:
        raise JobError(f"unknown job kind {kind}")
    clean = KINDS[kind](**params).model_dump(mode="json")
    job_id = f"{datetime.now(UTC):%Y%m%d-%H%M%S}-{secrets.token_hex(3)}"
    doc = {"id": job_id, "kind": kind, "title": TITLES[kind], "params": clean, "status": "queued", "created_at": _now(), "progress": None, "pid": None}
    _write(doc)
    if spawn:
        env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
        log = (jobs_dir() / f"{job_id}.log").open("w")
        proc = subprocess.Popen(
            [str(Path(sys.executable).parent / "trader"), "job", "run", job_id],
            stdout=log,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            env=env,
            cwd=Path.cwd(),
            start_new_session=True,
        )
        doc["pid"] = proc.pid
        _write(doc)
    return doc


def cancel(job_id: str) -> dict:
    doc = get(job_id)
    if doc["status"] not in ("queued", "running"):
        raise JobError(f"job {job_id} is already {doc['status']}")
    if doc.get("pid") and _alive(doc["pid"]):
        os.kill(doc["pid"], signal.SIGTERM)
    doc.update({"status": "cancelled", "finished_at": _now()})
    _write(doc)
    return doc


def progress(doc: dict, text: str) -> None:
    doc["progress"] = text
    _write(doc)


def run(job_id: str) -> dict:
    doc = get(job_id)
    doc.update({"status": "running", "started_at": _now(), "pid": os.getpid()})
    _write(doc)
    try:
        params = KINDS[doc["kind"]](**doc["params"])
        doc["result"] = RUNNERS[doc["kind"]](params, lambda text: progress(doc, text))
        doc.update({"status": "done", "finished_at": _now(), "progress": None})
    except Exception as exc:
        doc.update({"status": "failed", "finished_at": _now(), "error": f"{type(exc).__name__}: {exc}", "trace": traceback.format_exc()[-4000:]})
    _write(doc)
    return doc


def _ms(day: date) -> int:
    return int(datetime(day.year, day.month, day.day, tzinfo=UTC).timestamp() * 1000)


def _iso(ms: int) -> str:
    return datetime.fromtimestamp(int(ms) / 1000, UTC).strftime("%Y-%m-%d")


def series(ret: pd.Series, capital: float) -> dict:
    """Daily returns → the chart-ready equity, drawdown and monthly table every quant result shares."""
    ret = ret.fillna(0.0)
    equity = capital * (1 + ret).cumprod()
    drawdown = equity / equity.cummax() - 1
    months = pd.to_datetime(ret.index, unit="ms", utc=True).strftime("%Y-%m")
    monthly = ret.groupby(months).apply(lambda r: float((1 + r).prod() - 1))
    days = len(ret)
    total = float(equity.iloc[-1] / capital - 1) if days else 0.0
    vol = float(ret.std()) if days > 1 else 0.0
    return {
        "days": [_iso(t) for t in ret.index],
        "returns": [round(float(v), 6) for v in ret],
        "equity": [round(float(v), 2) for v in equity],
        "drawdown": [round(float(v), 5) for v in drawdown],
        "monthly": [{"month": m, "return": round(v, 5)} for m, v in monthly.items()],
        "stats": {
            "start_equity": capital,
            "final_equity": round(float(equity.iloc[-1]), 2) if days else capital,
            "return_pct": round(100 * total, 2),
            "annual_return_pct": round(100 * ((1 + total) ** (365 / days) - 1), 2) if days > 30 and total > -1 else None,
            "sharpe": round(float(ret.mean() / vol * np.sqrt(365)), 2) if vol > 0 else None,
            "max_drawdown_pct": round(100 * float(drawdown.min()), 2) if days else 0.0,
            "worst_day_pct": round(100 * float(ret.min()), 2) if days else 0.0,
            "best_day_pct": round(100 * float(ret.max()), 2) if days else 0.0,
            "positive_days_pct": round(100 * float((ret > 0).mean()), 1) if days else 0.0,
            "positive_months": int((monthly > 0).sum()),
            "months": len(monthly),
            "days": days,
        },
    }


def _book(w: pd.Series, top: int = 40) -> dict:
    w = w[w.abs() > 1e-9]
    longs = w[w > 0].sort_values(ascending=False).head(top)
    shorts = w[w < 0].sort_values().head(top)
    return {
        "longs": [{"symbol": s, "weight": round(float(v), 5)} for s, v in longs.items()],
        "shorts": [{"symbol": s, "weight": round(float(v), 5)} for s, v in shorts.items()],
        "gross": round(float(w.abs().sum()), 4),
        "net": round(float(w.sum()), 4),
        "positions": len(w),
    }


def _sources(start: date, end: date) -> list[tuple[Path, int, int]]:
    """Which data directory holds which part of the requested window (the untouched 2021-07…2023-06 rebuild lives in data_pre)."""
    lo, hi = _ms(start), _ms(end) + DAY
    out = []
    pre = Path(str(settings.data_dir) + "_pre")
    for directory, (a, b) in ((pre, PRE_RANGE), (settings.data_dir, MAIN_RANGE)):
        a_ms, b_ms = _ms(date.fromisoformat(a)), _ms(date.fromisoformat(b))
        s, e = max(lo, a_ms), min(hi, b_ms)
        if s < e and (directory / "quant" / "predictions.parquet").exists():
            out.append((directory, s, e))
    return out


def _extreme(panel, book: pd.DataFrame, lo: int, hi: int) -> list[dict]:
    r = panel.r[(panel.r.index >= lo) & (panel.r.index < hi)]
    held = book.shift(1).reindex(index=r.index, columns=r.columns).fillna(0.0)
    hits = r.where((r >= 3.0) | (r <= -0.95)).stack()
    return [{"day": _iso(t), "symbol": s, "move_pct": round(100 * float(v), 1), "weight": round(float(held.at[t, s]), 5)} for (t, s), v in hits.items()]


def run_quant_period(p: QuantPeriod, report, books: list | None = None) -> dict:
    from trader.quant import model, neutral, trend

    config = {**neutral.ENSEMBLE, "gross": p.gross, "per_side": p.per_side, "short_cap": p.short_cap, "band": p.band, "beta_days": p.beta_days, "family": p.family}
    sources = _sources(p.start, p.end)
    if not sources:
        raise JobError(f"no walk-forward predictions cover {p.start}…{p.end}; history spans {PRE_RANGE[0]}…{MAIN_RANGE[1]}")
    parts, last_book, extreme, original = [], None, [], settings.data_dir
    try:
        for directory, lo, hi in sources:
            settings.data_dir = directory
            report(f"завантажую панель і прогнози з {directory.name} …")
            panel = trend.load_panel()
            scores = neutral.all_scores(panel, pd.read_parquet(model.root() / "predictions.parquet"))
            report("рахую книгу …")
            ret, book = neutral.drift(panel, neutral.production_weights(panel, scores, config), band=config["band"])
            parts.append(ret[(ret.index >= lo) & (ret.index < hi)])
            held = book.loc[(book.index >= lo - DAY) & (book.index < hi - DAY)]
            if len(held):
                last_book = _book(held.iloc[-1])
            extreme.extend(_extreme(panel, book, lo, hi))
            if books is not None:
                books.append(neutral.held_long(book, lo, hi))
    finally:
        settings.data_dir = original
    ret = pd.concat(parts).sort_index()
    out = series(ret, p.capital)
    out["sources"] = [{"data": d.name, "from": _iso(lo), "to": _iso(hi - DAY)} for d, lo, hi in sources]
    out["book_last_day"] = last_book
    out["extreme_moves"] = extreme
    out["config"] = config
    return out


def run_quant_forward(p: QuantForward, report) -> dict:
    from trader.quant import live

    report("качаю свіжі котирування всіх ліквідних ф'ючерсів (перший раз — кілька хвилин) …")
    first = datetime(p.start.year, p.start.month, p.start.day, tzinfo=UTC)
    last = datetime(p.end.year, p.end.month, p.end.day, tzinfo=UTC) if p.end else None
    doc = live.forward(first, last, p.capital)
    days = pd.Series({_ms(date.fromisoformat(d["day"])): d["return_pct"] / 100 for d in doc["days"]})
    out = series(days, p.capital)
    out.update({"model": doc["model"], "symbols_scored": doc["symbols_scored"], "book_next_day": doc["book_for_next_day"]})
    return out


def run_quant_book(p: QuantBook, report) -> dict:
    from trader.quant import neutral

    report("рахую книгу дня …")
    return neutral.day_view(_ms(p.day))


def run_notice_replay(p: NoticeReplay, report) -> dict:
    from trader.core.db import create_db_and_tables
    from trader.services import replay

    create_db_and_tables()
    report("відтворюю анонси й тики …")
    return asyncio.run(replay.replay(datetime(p.day.year, p.day.month, p.day.day, tzinfo=UTC), p.days))


def run_quant_retrain(p: QuantRetrain, report) -> dict:
    from trader.quant import retrain

    report("дозавантажую архіви, перебудовую панелі й моделі (десятки хвилин) …")
    return retrain.run(p.skip_download)


def run_quant_evidence(p: QuantEvidence, report) -> dict:
    from trader.quant import evidence

    doc = evidence.build(report)
    return {"stats": doc["stats"], "periods": doc["periods"], "built_at": doc["built_at"]}


def run_quant_day(p: QuantDay, report) -> dict:
    from trader.quant import day

    report("качаю котирування пари й BTC, рахую 305 тактик …")
    start = datetime(p.day.year, p.day.month, p.day.day, tzinfo=UTC) if p.day else None
    return day.run(p.symbol, start, p.days, uploads_dir() / f"{p.upload}.csv" if p.upload else None, p.leverage)


RUNNERS = {
    "quant_period": run_quant_period,
    "quant_forward": run_quant_forward,
    "quant_book": run_quant_book,
    "notice_replay": run_notice_replay,
    "quant_retrain": run_quant_retrain,
    "quant_evidence": run_quant_evidence,
    "quant_day": run_quant_day,
}
