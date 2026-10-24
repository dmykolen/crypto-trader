"""One intelligence pass: every source → store new items → rule tags → optional Claude → series caches → hourly signals."""

import asyncio
import logging
from datetime import UTC, datetime, timedelta

import pandas as pd
from sqlmodel import Session

from trader.intel import analyze, history, signals, sources
from trader.intel.entities import Linker

log = logging.getLogger(__name__)

SERIES_CACHE = {"fear_greed": "fear_greed", "coingecko_trending": "trending", "binance_positioning": "positioning", "wikipedia_pageviews": "wiki", "gdelt": "gdelt"}


def health(results: list[sources.Result]) -> list[dict]:
    return [
        {"source": r.source.name, "kind": r.source.kind, "ok": r.ok, "items": r.items, "latency_s": round(r.latency_s, 2), **({"error": r.error} if r.error else {})}
        for r in sorted(results, key=lambda r: (r.source.kind, r.source.name))
    ]


async def fetch_pass(session: Session, linker: Linker, *, llm=None, llm_budget: int = 0, kinds: set[str] | None = None, signal_hours: int = 48) -> dict:
    """Run every source (or only `kinds`), persist what arrived, and refresh the last `signal_hours` of signals."""
    from trader.services.news import store_new

    chosen = [s for s in sources.registry() if kinds is None or s.kind in kinds]
    results = await sources.run(chosen)
    items = [i for r in results if r.ok and isinstance(r.payload, list) for i in r.payload]
    fresh = store_new(session, items)
    tagged = analyze.tag_items(session, fresh, linker)
    series_rows = {}
    for r in results:
        name = SERIES_CACHE.get(r.source.name)
        if r.ok and name and isinstance(r.payload, pd.DataFrame):
            series_rows[name] = history.upsert_series(name, r.payload)
    assessed = await analyze.deep_analyze(session, llm, fresh, budget=llm_budget) if llm is not None else 0
    now = datetime.now(UTC)
    written = signals.compute(session, now - timedelta(hours=signal_hours), now + timedelta(hours=1), linker)
    linked = sum(1 for i in fresh if (i.analysis or {}).get("intel", {}).get("symbols"))
    return {
        "fetched": len(items),
        "new": len(fresh),
        "tagged": tagged,
        "linked_to_perps": linked,
        "llm_assessed": assessed,
        "signal_rows": written,
        "series_cache_rows": series_rows,
        "new_by_source": pd.Series([i.source for i in fresh], dtype=str).value_counts().to_dict(),
        "sources": health(results),
    }


async def watch(session: Session, linker: Linker, seconds: float, *, llm=None, llm_budget: int = 0, series_every: int = 15, passes: int | None = None) -> None:
    """Text sources every `seconds`; numeric series every `series_every` passes."""
    n = 0
    while passes is None or n < passes:
        kinds = None if n % series_every == 0 else {"media", "board", "reddit"}
        try:
            report = await fetch_pass(session, linker, llm=llm, llm_budget=llm_budget, kinds=kinds, signal_hours=3)
            failed = [s["source"] for s in report["sources"] if not s["ok"]]
            log.info("intel pass %d: %d new items (%d linked), failed: %s", n, report["new"], report["linked_to_perps"], failed or "none")
        except Exception:
            log.exception("intel pass %d failed", n)
        n += 1
        if passes is None or n < passes:
            await asyncio.sleep(seconds)
