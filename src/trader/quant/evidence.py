"""The evidence behind bot #2: the production book's daily returns on every period, cached for the web UI."""

import json
from datetime import UTC, date, datetime

import pandas as pd

from trader.core.config import settings

PERIODS = (
    {"key": "untouched", "name": "Незайманий", "note": "жодного вибору, весь конвеєр заново", "start": "2021-07-01", "end": "2023-07-01"},
    {"key": "dev", "name": "Перевірочний", "note": "тут обирались налаштування — оптимістично", "start": "2023-07-01", "end": "2025-01-01"},
    {"key": "holdout", "name": "Новий період", "note": "лише вето для змін", "start": "2025-01-01", "end": "2026-10-01"},
    {"key": "forward", "name": "Форвард", "note": "дні, яких не бачила жодна модель", "start": "2026-10-01", "end": None},
)


def path():
    return settings.data_dir / "quant" / "evidence.json"


def load() -> dict | None:
    return json.loads(path().read_text()) if path().exists() else None


def _ms(text: str) -> int:
    return int(datetime.fromisoformat(text).replace(tzinfo=UTC).timestamp() * 1000)


def build(report=lambda text: None) -> dict:
    from trader.services import jobs

    books: list[pd.DataFrame] = []
    history = jobs.run_quant_period(jobs.QuantPeriod(start=date(2021, 7, 1), end=date(2026, 9, 30)), report, books)
    pd.concat(books, ignore_index=True).to_parquet(settings.data_dir / "quant" / "book_history.parquet", index=False)
    ret = pd.Series(history["returns"], index=[_ms(d) for d in history["days"]])
    forward = settings.reports_dir / "quant" / "forward.json"
    if forward.exists():
        days = json.loads(forward.read_text())["days"]
        extra = pd.Series({_ms(d["day"]): d["return_pct"] / 100 for d in days})
        ret = pd.concat([ret, extra[~extra.index.isin(ret.index)]]).sort_index()
    whole = jobs.series(ret, 1000.0)
    periods = []
    for period in PERIODS:
        lo = _ms(period["start"])
        hi = _ms(period["end"]) if period["end"] else 1 << 62
        part = ret[(ret.index >= lo) & (ret.index < hi)]
        if len(part):
            periods.append({
                **period,
                "stats": jobs.series(part, 1000.0)["stats"],
                "from": whole["days"][list(ret.index).index(part.index[0])],
                "to": whole["days"][list(ret.index).index(part.index[-1])],
            })
    doc = {
        "built_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "days": whole["days"],
        "equity": whole["equity"],
        "drawdown": whole["drawdown"],
        "stats": whole["stats"],
        "periods": periods,
    }
    path().parent.mkdir(parents=True, exist_ok=True)
    path().write_text(json.dumps(jobs.clean(doc)))
    return doc
