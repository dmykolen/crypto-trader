import json
import os
import plistlib
import time
from datetime import UTC, datetime, timedelta

import pytest

from trader.core.config import settings
from trader.services import jobs, processes, supervisor


@pytest.fixture
def data(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    monkeypatch.setattr(settings, "reports_dir", tmp_path / "reports")
    (tmp_path / "data" / "run").mkdir(parents=True)
    return tmp_path / "data"


def _bot(bot, running, pid=None):
    return {"bot": bot, "running": running, "pid": pid, "mode": "paper", "started_at": None, "uptime_s": None, "managed": True, "log": None, "last_stop": None, "last_log_at": None}


def test_the_inventory_lists_the_server_the_bots_jobs_and_any_other_trader_process(data, monkeypatch):
    monkeypatch.setattr(processes, "status", lambda: {"notice": _bot("notice", True, 11), "quant": _bot("quant", False)})
    monkeypatch.setattr(
        jobs,
        "listing",
        lambda n: [
            {"id": "j1", "status": "running", "title": "Пара за день", "pid": 12, "created_at": "2026-10-31T10:00:00+00:00"},
            {"id": "j0", "status": "done", "title": "x", "created_at": "2026-10-30T10:00:00+00:00"},
        ],
    )
    monkeypatch.setattr(supervisor, "_scan", lambda: [(11, ["run"], 0.0), (12, ["job", "run", "j1"], 0.0), (13, ["serve", "--port", "8711"], 0.0), (14, ["quant", "tactics"], 0.0)])
    monkeypatch.setattr(supervisor, "metrics", lambda pid: {"cpu": 1.0, "memory_mb": 50.0})
    rows = {r["key"]: r for r in supervisor.inventory()}
    assert rows["server"]["pid"] == os.getpid()
    assert rows["notice"]["running"] and not rows["quant"]["running"]
    assert rows["job:j1"]["kind"] == "job" and "job:j0" not in rows
    assert rows["server:13"]["port"] == 8711
    assert rows["cli:14"]["command"] == "quant tactics"
    assert len(rows) == 6


def test_only_known_trader_processes_can_be_stopped(data, monkeypatch):
    killed = []
    monkeypatch.setattr(supervisor, "_scan", lambda: [(4242, ["serve", "--port", "8711"], 0.0)])
    monkeypatch.setattr(supervisor.os, "kill", lambda pid, sig: killed.append(pid))
    assert supervisor.stop("server:4242") == {"key": "server:4242", "pid": 4242}
    with pytest.raises(supervisor.SupervisorError):
        supervisor.stop("cli:999")
    with pytest.raises(supervisor.SupervisorError):
        supervisor.stop(f"server:{os.getpid()}")
    with pytest.raises(supervisor.SupervisorError):
        supervisor.stop("rm -rf")
    assert killed == [4242]


def test_after_a_reboot_only_bots_that_were_running_on_virtual_money_come_back(data, monkeypatch):
    run = data / "run"
    (run / "quant.json").write_text(json.dumps({"pid": 5, "mode": "paper", "started_at": "2026-10-31T10:00:00+00:00"}))
    (run / "notice.json").write_text(json.dumps({"pid": 6, "mode": "paper", "started_at": "2026-10-31T10:00:00+00:00", "stopped_at": "2026-10-31T11:00:00+00:00"}))
    started = []
    monkeypatch.setattr(processes, "status", lambda: {"notice": _bot("notice", False), "quant": _bot("quant", False)})
    monkeypatch.setattr(processes, "start", lambda bot, mode: started.append((bot, mode)))
    assert processes.restore() == ["quant"]
    (run / "quant.json").write_text(json.dumps({"pid": 5, "mode": "live", "started_at": "2026-10-31T10:00:00+00:00"}))
    assert processes.restore() == []
    assert started == [("quant", "paper")]


def test_cleaning_removes_only_cached_quotes_older_than_thirty_days(data):
    live = data / "quant" / "live"
    live.mkdir(parents=True)
    old, fresh, book = live / "bars_2026080100_2026092900.parquet", live / "bars_2026090100_2026103100.parquet", live / "forward_book.parquet"
    for f in (old, fresh, book):
        f.write_bytes(b"x" * 100)
    stale = time.time() - 40 * 86400
    os.utime(old, (stale, stale))
    os.utime(book, (stale, stale))
    assert supervisor.disk()["stale"] == {"files": 1, "bytes": 100, "keep_days": 30}
    assert supervisor.clean_caches() == {"files": 1, "freed": 100}
    assert not old.exists() and fresh.exists() and book.exists()


def test_the_autostart_agent_boots_the_panel_and_keeps_it_alive(data):
    plist = plistlib.loads(plistlib.dumps(supervisor.agent()))
    assert plist["Label"] == supervisor.LABEL
    assert plist["ProgramArguments"][-3:] == ["boot", "--port", "8710"]
    assert plist["RunAtLoad"] and plist["KeepAlive"]
    assert plist["EnvironmentVariables"]["TRADER_SUPERVISED"] == "1"
    assert plist["StandardOutPath"].endswith("data/run/serve.log")


def _local(dt: datetime) -> str:
    return dt.astimezone().strftime("%Y-%m-%d %H:%M:%S")


def test_errors_count_only_the_last_day_and_name_what_followed(data):
    now = datetime(2026, 10, 31, 12, 0, tzinfo=UTC)
    recent, old = now - timedelta(hours=2), now - timedelta(days=3)
    (data / "run" / "quant.log").write_text(
        f"{_local(old)},001 ERROR trader.quant.paper: old failure\n"
        f"{_local(recent)},002 ERROR trader.quant.paper: quant paper rebalance failed, retrying in 15 minutes\n"
        "Traceback (most recent call last):\n  File x\nOSError: [Errno 28] No space left on device\n"
        f"{_local(recent)},003 WARNING trader.quant.paper: fine\n"
    )
    got = {e["source"]: e for e in supervisor.errors(now=now)}
    assert got["quant"]["count"] == 1
    assert got["quant"]["recent"][0]["detail"] == "OSError: [Errno 28] No space left on device"
    assert got["notice"]["count"] == 0


def test_errors_count_the_whole_day_of_a_log_far_longer_than_one_read(data):
    now = datetime(2026, 10, 31, 12, 0, tzinfo=UTC)
    failed = ",000 ERROR trader.services.trading: poll_upbit_fast failed\n"
    trace = "Traceback (most recent call last):\n  File x\nhttpcore.ConnectError: [Errno 8] nodename nor servname provided, or not known\n"
    old = "".join(f"{_local(now - timedelta(days=2, seconds=i))}{failed}" for i in range(4000, 0, -1))
    day = "".join(f"{_local(now - timedelta(seconds=10 * i))}{failed}{trace}" for i in range(3000, 0, -1))
    (data / "run" / "notice.log").write_text(old + day)
    got = {e["source"]: e for e in supervisor.errors(now=now)}["notice"]
    assert got["count"] == 3000
    assert got["recent"][-1]["detail"].startswith("httpcore.ConnectError")


def test_logs_are_served_only_for_known_sources(client, data):
    (data / "run" / "quant.log").write_text("a\nb\n")
    assert client.get("/api/v1/logs/quant?lines=10").json()["lines"] == ["a", "b"]
    assert client.get("/api/v1/logs/passwd").status_code == 404
    assert client.get("/api/v1/logs/job:..%2F..%2Fetc").status_code == 404


def test_the_live_log_stream_opens_with_the_tail(client, data):
    (data / "run" / "notice.log").write_text("first\nsecond\n")
    with client.stream("GET", "/api/v1/logs/notice/stream?poll=0.01") as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        for line in response.iter_lines():
            if line.startswith("data:"):
                assert json.loads(line[5:]) == {"lines": ["first", "second"], "reset": True}
                break


def test_the_schedule_names_the_next_rebalance_and_the_last_results(data):
    (data / "quant" / "paper").mkdir(parents=True)
    (data / "quant" / "paper" / "ledger.json").write_text(json.dumps({"history": [{"rebalanced_at": "2026-10-31T00:15:00+00:00", "pnl_since_last": -24.33}]}))
    items = {i["key"]: i for i in supervisor.schedule(now=datetime(2026, 10, 31, 16, 0, tzinfo=UTC))}
    assert items["rebalance"]["next"] == "2026-11-01T00:15:00+00:00"
    assert items["rebalance"]["last_pnl"] == -24.33
    assert items["limit_test"]["last"] is None


def test_the_notice_feed_shows_what_the_bot_decided_about_each_notice(client, data):
    from sqlmodel import Session

    from trader.core.db import create_db_and_tables, engine
    from trader.models import NewsItem
    from trader.services import trading

    create_db_and_tables()
    published = datetime.now(UTC) - timedelta(minutes=1)
    with Session(engine) as session:
        session.merge(
            NewsItem(
                id="binance:decided-1",
                source="binance",
                title="Binance Will List ABC",
                published_at=published,
                seen_at=published + timedelta(seconds=2),
                events=[{"type": "binance_spot_listing", "symbol": "ABC"}],
            )
        )
        session.commit()
    trading.record("binance:decided-1", "binance_spot_listing", "ABC", "no_perp")
    rows = {r["id"]: r for r in client.get("/api/v1/notice/feed?limit=500").json()}
    assert rows["binance:decided-1"]["decisions"][0]["outcome"] == "no_perp"
    assert rows["binance:decided-1"]["latency_s"] == 2.0
