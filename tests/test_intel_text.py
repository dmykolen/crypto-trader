"""Intel text pipeline: feed parsing, entity linking, rule tagging and the hourly signal timing contract."""

from datetime import UTC, datetime

import numpy as np
import pandas as pd
import pytest
from sqlmodel import Session

from trader.intel import analyze, history, signals, sources
from trader.intel.entities import Linker, base_assets
from trader.models import NewsItem

UNIVERSE = {"BTCUSDT", "ETHUSDT", "SOLUSDT", "1000PEPEUSDT", "ONEUSDT", "LINKUSDT", "XRPUSDT"}
COINS = [
    {"id": "bitcoin", "symbol": "btc", "name": "Bitcoin"},
    {"id": "ethereum", "symbol": "eth", "name": "Ethereum"},
    {"id": "solana", "symbol": "sol", "name": "Solana"},
    {"id": "pepe", "symbol": "pepe", "name": "Pepe"},
    {"id": "harmony", "symbol": "one", "name": "Harmony"},
    {"id": "chainlink", "symbol": "link", "name": "Chainlink"},
    {"id": "ripple", "symbol": "xrp", "name": "XRP"},
]
RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>
<item><title>Bitcoin surges past record</title><link>https://x/1</link><guid>g1</guid><pubDate>Tue, 03 Mar 2026 10:15:00 GMT</pubDate></item>
<item><title>No date here</title><link>https://x/2</link></item>
</channel></rss>"""


@pytest.fixture
def linker() -> Linker:
    return Linker(UNIVERSE, COINS)


def item(title: str, at: datetime, source: str = "rss:test", summary: str | None = None) -> NewsItem:
    return NewsItem(id=f"{source}:{title}", source=source, title=title, summary=summary, published_at=at)


def test_parse_feed_keeps_dated_entries_and_rejects_non_feeds():
    items = sources.parse_feed("rss:test", RSS)
    assert [i.title for i in items] == ["Bitcoin surges past record"]
    assert items[0].published_at == datetime(2026, 3, 3, 10, 15, tzinfo=UTC)
    assert items[0].id == "rss:test:g1"
    with pytest.raises(ValueError):
        sources.parse_feed("rss:test", b"<html>blocked</html>")


def test_series_parsers_produce_long_frames():
    fng = sources.parse_fear_greed({"data": [{"value": "25", "timestamp": "1700000000"}]})
    assert fng.to_dict("records") == [{"ts": 1700000000000, "key": "MARKET", "metric": "fear_greed", "value": 25.0}]
    doc = {"timeline": [{"data": [{"date": "20240101T000000Z", "value": 10, "norm": 1000}]}]}
    gd = sources.parse_gdelt("BTC", "gdelt_volume", doc)
    assert set(gd["metric"]) == {"gdelt_volume", "gdelt_total"}
    views = sources.parse_pageviews("ETH", {"items": [{"timestamp": "2024010200", "views": 7}]})
    assert views.iloc[0]["ts"] == int(datetime(2024, 1, 2, tzinfo=UTC).timestamp() * 1000)


def test_base_assets_strip_multiplier_prefixes():
    assert base_assets({"1000PEPEUSDT", "1INCHUSDT", "BTCUSDT"}) == {"PEPE": "1000PEPEUSDT", "1INCH": "1INCHUSDT", "BTC": "BTCUSDT"}


def test_linker_uses_cashtags_parens_and_names_but_not_common_words(linker):
    assert linker.link("$SOL and Ethereum (ETH) rally") == ["SOLUSDT", "ETHUSDT"]
    assert linker.link("bitcoin miners sell") == ["BTCUSDT"]
    assert linker.link("PEPE token jumps 20%") == ["1000PEPEUSDT"]
    assert linker.link("One more thing about the Fed") == []
    assert linker.link("Harmony (ONE) hacked") == ["ONEUSDT"]
    assert linker.link("SEC sues exchange over ETF") == []


def test_category_and_polarity_rules():
    assert analyze.category("Binance Will List Foo (FOO)")[0] == "listing"
    assert analyze.category("Binance will delist BAR")[0] == "delisting"
    assert analyze.category("Protocol drained in $10M exploit")[0] == "hack_exploit"
    assert analyze.category("Nothing to see")[0] == "other"
    assert analyze.polarity("Bitcoin surges to record high") > 0.5
    assert analyze.polarity("Exchange hacked, funds stolen") < -0.5
    assert analyze.polarity("SEC does not reject the filing") > 0


def test_tag_links_symbols_from_events_and_text(linker):
    news = item("Solana network outage halts blocks", datetime(2026, 1, 1, tzinfo=UTC))
    news.events = [{"type": "listing", "token": "XRP"}]
    tags = analyze.tag(news, linker)
    assert tags["category"] == "listing"
    assert "outage" in tags["categories"]
    assert tags["symbols"] == ["XRPUSDT", "SOLUSDT"]
    assert tags["polarity"] < 0


def test_burst_z_ignores_the_current_hour_and_floors_variance():
    counts = pd.Series([0.0] * 48 + [3.0])
    z = signals.burst_z(counts)
    assert z.iloc[-1] == pytest.approx(3.0 / np.sqrt(1 / 24))
    assert (z.iloc[:24] == 0).all()


def test_aggregate_buckets_by_publication_hour_and_dedups_titles(linker):
    t0 = datetime(2026, 2, 1, 10, tzinfo=UTC)
    items = [
        item("Bitcoin surges", t0.replace(minute=5), "rss:a"),
        item("Bitcoin surges", t0.replace(minute=7), "rss:b"),
        item("Bitcoin crashes", t0.replace(minute=59), "rss:a"),
        item("Solana listed on Foo", t0.replace(hour=11, minute=0), "rss:a"),
    ]
    frame = signals.aggregate(signals.records(items, linker), signals._ms(t0), signals._ms(t0.replace(hour=12)))
    btc = frame[frame["symbol"] == "BTCUSDT"].set_index("open_time")
    hour10 = signals._ms(t0)
    assert btc.loc[hour10, "mentions"] == 2
    assert btc.loc[hour10, "sources"] == 2
    assert hour10 + signals.HOUR_MS not in btc.index
    sol = frame[frame["symbol"] == "SOLUSDT"].set_index("open_time")
    assert list(sol.index) == [hour10 + signals.HOUR_MS]
    market = frame[frame["symbol"] == signals.MARKET]
    assert len(market) == 2


def test_features_join_signals_and_lagged_daily_series(linker):
    from trader.core.db import create_db_and_tables, engine

    create_db_and_tables()
    t0 = datetime(2025, 3, 10, tzinfo=UTC)
    day_ms = signals._ms(t0)
    history.upsert_series("fear_greed", pd.DataFrame({"ts": [day_ms], "key": "MARKET", "metric": "fear_greed", "value": [40.0]}))
    days = [day_ms - k * 24 * signals.HOUR_MS for k in range(30, -1, -1)]
    values = [100.0] * 30 + [1000.0]
    history.upsert_series("wiki", pd.DataFrame({"ts": days, "key": "SOL", "metric": "wiki_views", "value": values}))
    with Session(engine) as session:
        session.add_all([item("Solana surges", t0.replace(hour=3, minute=20)), item("Solana (SOL) jumps", t0.replace(hour=3, minute=40), "rss:b")])
        session.commit()
        signals.compute(session, t0, t0.replace(hour=12), linker)
        feats = signals.features("SOLUSDT", t0, datetime(2025, 3, 11, 12, tzinfo=UTC), session=session)
    hour = signals.HOUR_MS
    assert feats.loc[day_ms + 3 * hour, "news_mentions"] == 2
    assert feats.loc[day_ms + 2 * hour, "news_mentions"] == 0
    assert feats.loc[day_ms, "fear_greed"] == 40.0
    assert np.isnan(feats.loc[day_ms + 29 * hour, "wiki_z"]) or feats.loc[day_ms + 29 * hour, "wiki_z"] < 1
    assert feats.loc[day_ms + 30 * hour, "wiki_z"] > 2
