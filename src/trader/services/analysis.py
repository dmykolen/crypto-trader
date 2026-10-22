"""Market analysis on demand — the multi-horizon forecast, Claude's desk brief, headline triage."""

import asyncio
import json
import re
from datetime import UTC, datetime, timedelta

from sqlmodel import Session, col, select

from trader.ai import analyst, news_analyst
from trader.core.config import settings
from trader.core.db import engine
from trader.integrations.binance import INTERVAL_MS
from trader.integrations.llm import LLM
from trader.models import NewsItem
from trader.services import features, forecast, market_data, playbooks
from trader.services.events import Notice, classify

HORIZONS_MS = {"1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000, "3d": 259_200_000, "1w": 604_800_000}


def base_asset(symbol: str) -> str:
    """WIFUSDT → WIF, 1000PEPEUSDT → PEPE, 1MBABYDOGEUSDT → BABYDOGE."""
    base = symbol.upper().removesuffix("USDT")
    for prefix in ("1000000", "1000", "1M"):
        if base.startswith(prefix) and len(base) > len(prefix) + 1 and not base[len(prefix)].isdigit():
            return base.removeprefix(prefix)
    return base


def forecast_symbol(symbol: str, interval: str = "1h", days: int = 365) -> dict:
    """Regime + LightGBM forecast for every horizon ≥ one bar, each with its out-of-sample AUC / hit-rate."""
    step = INTERVAL_MS[interval]
    end = market_data.from_ms(int(datetime.now(UTC).timestamp() * 1000) // step * step)  # only completed bars
    bars, funding = market_data.load_bars(symbol, interval, end - timedelta(days=days), end)
    if len(bars) < 1000:
        raise ValueError(f"{symbol}: only {len(bars)} {interval} bars of history")
    horizons = {name: ms // step for name, ms in HORIZONS_MS.items() if ms >= step}
    return {
        "symbol": symbol,
        "interval": interval,
        "as_of": end.isoformat(),
        "last_close": float(bars.close.iloc[-1]),
        "regime": features.regime(bars),
        "forecast": forecast.forecast(bars, funding, horizons),
    }


def _strategy_choice(symbol: str) -> dict | None:
    path = settings.reports_dir / "strategy_selection.json"
    study = json.loads(path.read_text()).get("symbols", {}).get(symbol) if path.exists() else None
    return None if study is None else {"out_of_sample": study["oos"], "selected_now": study["current"], "recent_folds": study["folds"][-6:]}


def recent_news(token: str, limit: int = 15) -> list[dict]:
    """Latest stored news that mention `token` (rule-classified events or the title)."""
    with Session(engine) as session:
        items = session.exec(select(NewsItem).order_by(col(NewsItem.published_at).desc()).limit(3000)).all()
    mentions = re.compile(rf"\b{re.escape(token)}\b")
    hits = [i for i in items if any(e["token"] == token for e in i.events) or mentions.search(i.title.upper())]
    return [
        {"time": i.published_at.isoformat(timespec="minutes"), "source": i.source, "title": i.title, "events": i.events, "llm": (i.analysis or {}).get("summary")}
        for i in hits[:limit]
    ]


async def brief(llm: LLM, symbol: str, interval: str = "1h") -> analyst.MarketBrief:
    measurements = await asyncio.to_thread(forecast_symbol, symbol, interval)
    measurements["strategy_selection"] = _strategy_choice(symbol)
    measurements["event_playbooks"] = {k: v.get("describe", "skip — no edge") for k, v in playbooks.saved().get("types", {}).items()}
    measurements["recent_news"] = recent_news(base_asset(symbol))
    return await analyst.market_brief(llm, symbol, measurements)


async def analyze_headline(llm: LLM, title: str, summary: str | None = None, source: str | None = None) -> dict:
    """Rule-based events (with the playbook that would trade them) + Claude's impact assessment when configured."""
    live = playbooks.live_playbooks()
    events = [
        {"type": e.type.value, "token": e.token, "playbook": live[e.type].describe() if e.type in live else None}
        for e in classify(Notice(source or "media", "adhoc", title, datetime.now(UTC)))
    ]
    impact = await news_analyst.assess(llm, title, summary, source) if llm.enabled else None
    return {
        "rule_events": events,
        "llm": impact.model_dump() if impact else None,
        "actionable": [t.model_dump() for t in news_analyst.actionable(impact)] if impact else [],
    }
