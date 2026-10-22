"""HTTP surface: probes, metrics, journals, reports and headline analysis (LLM stubbed)."""

from datetime import UTC, datetime

from sqlmodel import Session

from trader.ai.news_analyst import NewsImpact
from trader.core.db import engine
from trader.services.events import Notice
from trader.services.news import store_new, to_item


class StubLLM:
    enabled = True

    async def structured(self, schema, prompt, **_):
        assert schema is NewsImpact and "Delist" in prompt
        return NewsImpact.model_validate({
            "category": "delisting",
            "is_new_information": True,
            "impacts": [{"ticker": "ABC", "direction": "bearish", "expected_move_pct": 15, "horizon_minutes": 240, "confidence": 0.8}],
            "market_wide_direction": "neutral",
            "summary": "Spot delisting of ABC.",
        })


def test_health_ready_metrics(client):
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/ready").json() == {"status": "ready"}
    client.get("/api/v1/news")
    body = client.get("/metrics").text
    assert "http_request_duration_seconds" in body
    assert "news_items_total" in body and "trades_closed_total" in body


def test_news_journal_filters_tradable_events(client):
    with Session(engine) as session:
        store_new(session, [
            to_item(Notice("upbit", "t1", "에이피아이쓰리(API3) KRW 마켓 디지털 자산 추가", datetime.now(UTC))),
            to_item(Notice("binance", "t2", "Introducing a new Launchpool project", datetime.now(UTC))),
        ])  # fmt: skip
    rows = client.get("/api/v1/news", params={"events_only": True}).json()
    assert [r["id"] for r in rows] == ["upbit:t1"]
    assert rows[0]["events"] == [{"type": "upbit_krw_listing", "token": "API3"}]
    assert len(client.get("/api/v1/news").json()) == 2


def test_empty_trading_state(client):
    assert client.get("/api/v1/trades").json() == []
    assert client.get("/api/v1/portfolio").json()["paper_equity"] == 1000.0
    assert client.get("/api/v1/playbooks").json() == {}
    assert client.get("/api/v1/reports/event_research").status_code == 404
    assert client.get("/api/v1/reports/../../etc").status_code == 404


def test_analyze_combines_rules_and_llm(client):
    from trader.main import app
    from trader.transports.http import api

    app.dependency_overrides[api.get_llm] = StubLLM
    doc = client.post("/api/v1/analyze", json={"title": "Binance Will Delist ABC, DEF on 2026-11-01", "source": "binance"}).json()
    assert [e["token"] for e in doc["rule_events"]] == ["ABC", "DEF"]
    assert doc["rule_events"][0]["type"] == "binance_spot_delisting"
    assert doc["actionable"][0]["ticker"] == "ABC"
