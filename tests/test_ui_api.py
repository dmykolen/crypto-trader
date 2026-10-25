import json
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from trader.quant import live_exec, paper
from trader.services import jobs, processes
from trader.transports.http import ui

PYTHON = "/x/.venv/bin/python3"
TRADER = "/x/.venv/bin/trader"


@pytest.fixture
def no_bots_running(monkeypatch):
    monkeypatch.setattr(processes, "_ps", lambda: [])


def test_process_command_lines_are_matched_to_bots_and_modes_but_not_their_launchers():
    assert processes.classify(f"{PYTHON} {TRADER} run") == ("notice", "paper")
    assert processes.classify(f"{PYTHON} {TRADER} quant paper --loop") == ("quant", "paper")
    assert processes.classify(f"{PYTHON} {TRADER} quant live --loop") == ("quant", "live")
    assert processes.classify("uv run trader quant paper --loop") is None
    assert processes.classify(f"{PYTHON} {TRADER} quant forward 2026-10-01") is None
    assert processes.classify("/usr/bin/vim notes.txt") is None


def test_the_api_only_answers_on_localhost_and_state_changes_need_the_ui_header(no_bots_running):
    from trader.main import app

    with TestClient(app, base_url="http://evil.example") as foreign:
        assert foreign.get("/api/v1/bots").status_code == 403
    with TestClient(app, base_url="http://127.0.0.1:8000") as bare:
        assert bare.get("/api/v1/bots").status_code == 200
        assert bare.post("/api/v1/bots/quant/stop").status_code == 403


def test_bots_report_their_process_state(client, monkeypatch):
    monkeypatch.setattr(processes, "_ps", lambda: [(4242, "Sun Oct 25 12:37:00 2026", f"{PYTHON} {TRADER} quant paper --loop")])
    bots = {b["key"]: b for b in client.get("/api/v1/bots").json()}
    assert bots["quant"]["running"] is True and bots["quant"]["pid"] == 4242 and bots["quant"]["mode"] == "paper"
    assert bots["notice"]["running"] is False
    assert bots["quant"]["confirm_phrase"] == "LIVE QUANT"


def test_real_money_needs_the_exact_phrase_and_api_keys(client, no_bots_running, monkeypatch):
    monkeypatch.setattr(processes, "live_ready", lambda: False)
    wrong = client.post("/api/v1/bots/quant/start", json={"mode": "live", "confirm": "live quant"})
    assert wrong.status_code == 400 and "LIVE QUANT" in wrong.json()["detail"]
    no_keys = client.post("/api/v1/bots/quant/start", json={"mode": "live", "confirm": "LIVE QUANT"})
    assert no_keys.status_code == 409 and "BINANCE_API_KEY" in no_keys.json()["detail"]


def test_a_job_is_created_run_and_read_back_with_its_result(client, monkeypatch):
    class FakeProcess:
        pid = 999_999

    monkeypatch.setattr(jobs.subprocess, "Popen", lambda *a, **k: FakeProcess())
    monkeypatch.setitem(jobs.RUNNERS, "quant_book", lambda params, report: {"day": params.day.isoformat(), "pnl": float("nan")})
    created = client.post("/api/v1/jobs", json={"kind": "quant_book", "params": {"day": "2026-09-29"}})
    assert created.status_code == 201
    job_id = created.json()["id"]
    jobs.run(job_id)
    done = client.get(f"/api/v1/jobs/{job_id}").json()
    assert done["status"] == "done"
    assert done["result"] == {"day": "2026-09-29", "pnl": None}
    assert any(j["id"] == job_id and "result" not in j for j in client.get("/api/v1/jobs").json())
    assert client.post("/api/v1/jobs", json={"kind": "nope", "params": {}}).status_code == 400
    assert client.post("/api/v1/jobs", json={"kind": "quant_period", "params": {"start": "2026-01-01", "end": "2025-01-01"}}).status_code == 422


def test_the_quant_ledger_is_marked_to_live_prices(client, monkeypatch):
    path = paper.ledger_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    state = {
        "start_equity": 1000.0,
        "equity": 1000.0,
        "positions": {"AUSDT": {"weight": 0.5, "entry": 10.0}, "BUSDT": {"weight": -0.5, "entry": 20.0}},
        "history": [
            {
                "day": "2026-10-25",
                "rebalanced_at": datetime(2026, 10, 25, 0, 15, tzinfo=UTC).isoformat(),
                "equity": 1000.0,
                "pnl_since_last": 0.0,
                "cost": 0.5,
                "longs": 1,
                "shorts": 1,
            }
        ],
    }
    path.write_text(json.dumps(state))
    monkeypatch.setattr(ui, "live_prices", lambda: {"AUSDT": 11.0, "BUSDT": 19.0})
    doc = client.get("/api/v1/quant/ledger").json()
    assert doc["unrealized"] == pytest.approx(0.5 * 1000 * 0.1 + 0.5 * 1000 * 0.05)
    assert doc["equity_now"] == pytest.approx(1075.0)
    assert {p["symbol"]: p["side"] for p in doc["positions"]} == {"AUSDT": "long", "BUSDT": "short"}


def test_the_built_web_ui_is_served_with_a_single_page_fallback_that_never_hides_the_api(tmp_path):
    from trader.main import local_only, mount_web

    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<div id=root></div>")
    (tmp_path / "assets" / "app.js").write_text("console.log(1)")
    app = FastAPI()
    app.middleware("http")(local_only)

    @app.get("/api/v1/ping")
    def ping() -> dict:
        return {"ok": True}

    mount_web(app, tmp_path)
    with TestClient(app, base_url="http://127.0.0.1:8000") as client:
        assert client.get("/bots/quant").text == "<div id=root></div>"
        assert client.get("/assets/app.js").text == "console.log(1)"
        assert client.get("/api/v1/ping").json() == {"ok": True}
        assert client.get("/api/v1/missing").status_code == 404


def _round(symbol: str, qty: float) -> float:
    return round(qty, 3)


LIMITS = live_exec.Limits(min_notional=5.0, max_gross=3.0, max_position=0.3)


def test_live_plan_opens_a_book_from_flat_and_skips_orders_below_the_exchange_minimum():
    orders = live_exec.plan({"AUSDT": 0.2, "BUSDT": -0.2, "TINYUSDT": 0.001}, {}, {"AUSDT": 10.0, "BUSDT": 20.0, "TINYUSDT": 1.0}, 1000.0, 0.01, LIMITS, _round)
    assert [(o.symbol, o.side, o.qty, o.reduce_only, o.reason) for o in orders] == [("AUSDT", 1, 20.0, False, "open"), ("BUSDT", -1, 10.0, False, "open")]


def test_live_plan_reduces_before_it_grows_closes_dropped_names_and_flips_through_flat():
    positions = {"AUSDT": 20.0, "BUSDT": -10.0, "CUSDT": 5.0}
    prices = {"AUSDT": 10.0, "BUSDT": 20.0, "CUSDT": 40.0, "DUSDT": 50.0}
    target = {"AUSDT": 0.1, "BUSDT": 0.2, "DUSDT": 0.1}
    orders = live_exec.plan(target, positions, prices, 1000.0, 0.01, LIMITS, _round)
    reasons = [(o.symbol, o.reason, o.side, o.reduce_only) for o in orders]
    assert reasons[:3] == [("AUSDT", "reduce", -1, True), ("BUSDT", "flip-close", 1, True), ("CUSDT", "close", -1, True)]
    assert reasons[3:] == [("BUSDT", "flip-open", 1, False), ("DUSDT", "open", 1, False)]
    assert next(o for o in orders if o.reason == "reduce").qty == pytest.approx(10.0)


def test_live_plan_leaves_positions_inside_the_band_and_caps_an_oversized_book():
    assert live_exec.plan({"AUSDT": 0.205}, {"AUSDT": 20.0}, {"AUSDT": 10.0}, 1000.0, 0.01, LIMITS, _round) == []
    big = live_exec.plan({"AUSDT": 2.0, "BUSDT": -2.0}, {}, {"AUSDT": 10.0, "BUSDT": 10.0}, 1000.0, 0.01, LIMITS, _round)
    assert sum(o.notional for o in big) == pytest.approx(2 * 0.3 * 1000.0)
