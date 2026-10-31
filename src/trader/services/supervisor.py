import json
import os
import plistlib
import re
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import psutil

from trader.core.config import settings
from trader.services import jobs, processes

LABEL = "ua.crypto-trader"
KEEP_DAYS = 30
LOG_STAMP = re.compile(rb"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+ ", re.M)
LOG_FAILURE = re.compile(rb"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+ ((?:ERROR|CRITICAL) [^\n]*)", re.M)
_tracked: dict[int, psutil.Process] = {}
_sizes: tuple[float, list[dict]] | None = None


class SupervisorError(RuntimeError):
    pass


def metrics(pid: int | None) -> dict:
    if not pid:
        return {"cpu": None, "memory_mb": None}
    try:
        proc = _tracked.get(pid) or _tracked.setdefault(pid, psutil.Process(pid))
        with proc.oneshot():
            return {"cpu": round(proc.cpu_percent(None), 1), "memory_mb": round(proc.memory_info().rss / 2**20, 1)}
    except psutil.Error:
        _tracked.pop(pid, None)
        return {"cpu": None, "memory_mb": None}


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, UTC).isoformat(timespec="seconds")


def trader_args(cmdline: list[str]) -> list[str] | None:
    for i, token in enumerate(cmdline):
        if Path(token).name == "trader" and (i == 0 or Path(cmdline[i - 1]).name.startswith("python")):
            return cmdline[i + 1 :]
    return None


def _port(args: list[str]) -> int:
    return int(args[args.index("--port") + 1]) if "--port" in args and args.index("--port") + 1 < len(args) else 8710


def _server_port() -> int:
    return _port(trader_args(sys.argv) or sys.argv[1:])


def _scan() -> list[tuple[int, list[str], float]]:
    rows = []
    for proc in psutil.process_iter(["pid", "cmdline", "create_time"]):
        args = trader_args(proc.info["cmdline"] or [])
        if args is not None:
            rows.append((proc.info["pid"], args, proc.info["create_time"]))
    return rows


def inventory() -> list[dict]:
    me = os.getpid()
    out = [
        {
            "key": "server",
            "kind": "server",
            "pid": me,
            "port": _server_port(),
            "running": True,
            "started_at": _iso(psutil.Process(me).create_time()),
            "log": "serve" if processes.run_dir().joinpath("serve.log").exists() else None,
            **metrics(me),
        }
    ]
    for bot, state in processes.status().items():
        out.append({
            "key": bot,
            "kind": "bot",
            "pid": state["pid"],
            "mode": state["mode"],
            "running": state["running"],
            "started_at": state["started_at"],
            "last_stop": state["last_stop"],
            "last_log_at": state.get("last_log_at"),
            "managed": state["managed"],
            "log": bot if state["log"] else None,
            **metrics(state["pid"]),
        })
    bots = {row["pid"] for row in out if row["pid"]}
    active = {j["id"]: j for j in jobs.listing(50) if j["status"] in ("queued", "running")}
    for job in active.values():
        out.append({
            "key": f"job:{job['id']}",
            "kind": "job",
            "pid": job.get("pid"),
            "running": job["status"] == "running",
            "status": job["status"],
            "title": job["title"],
            "progress": job.get("progress"),
            "started_at": job.get("started_at") or job["created_at"],
            "log": f"job:{job['id']}",
            **metrics(job.get("pid")),
        })
    for pid, args, created in _scan():
        if pid in bots or pid == me or args[:2] == ["job", "run"] or processes.classify(shlex.join(["trader", *args])):
            continue
        kind = "server" if args[:1] == ["serve"] else "cli"
        out.append({
            "key": f"{kind}:{pid}",
            "kind": kind,
            "pid": pid,
            "port": _port(args) if kind == "server" else None,
            "running": True,
            "command": " ".join(args),
            "started_at": _iso(created),
            "log": None,
            **metrics(pid),
        })
    return out


def stop(key: str) -> dict:
    kind, _, ref = key.partition(":")
    if key in processes.BOTS:
        return processes.stop(key)
    if kind == "job":
        return jobs.cancel(ref)
    if kind in ("server", "cli") and ref.isdigit():
        pid = int(ref)
        if pid == os.getpid() or not any(p == pid for p, _, _ in _scan()):
            raise SupervisorError("not a stoppable trader process")
        os.kill(pid, signal.SIGTERM)
        return {"key": key, "pid": pid}
    raise SupervisorError(f"unknown process {key}")


def restart_bot(bot: str) -> dict:
    state = processes.status()[bot]
    if state["running"] and state["mode"] == "live":
        raise SupervisorError("a real-money bot is restarted only by stopping it and arming it again")
    if state["running"]:
        processes.stop(bot)
    return processes.start(bot, "paper")


def restart_server() -> dict:
    me = os.getpid()
    if os.environ.get("TRADER_SUPERVISED") == "1":
        threading.Timer(0.5, lambda: os.kill(me, signal.SIGTERM)).start()
        return {"restarting": True, "supervised": True}
    log = processes.run_dir() / "serve.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    script = f"sleep 1; kill {me}; sleep 2; exec {shlex.join(sys.argv)}"
    with log.open("a") as out:
        out.write(f"\n=== {datetime.now(UTC).isoformat(timespec='seconds')} restart from the web UI ===\n")
        out.flush()
        subprocess.Popen(["/bin/sh", "-c", script], stdout=out, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, cwd=Path.cwd(), start_new_session=True)
    return {"restarting": True, "supervised": False}


def agent_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def agent() -> dict:
    log = str((Path.cwd() / processes.run_dir() / "serve.log").resolve())
    return {
        "Label": LABEL,
        "ProgramArguments": [str(Path(sys.executable).parent / "trader"), "boot", "--port", "8710"],
        "WorkingDirectory": str(Path.cwd()),
        "RunAtLoad": True,
        "KeepAlive": True,
        "ThrottleInterval": 10,
        "ProcessType": "Interactive",
        "EnvironmentVariables": {"TRADER_SUPERVISED": "1", "PATH": os.environ.get("PATH", "/usr/bin:/bin"), "PYTHONUNBUFFERED": "1"},
        "StandardOutPath": log,
        "StandardErrorPath": log,
    }


def _launchctl(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["launchctl", *args], capture_output=True, text=True, check=False)


def autostart() -> dict:
    path = agent_path()
    loaded = _launchctl("print", f"gui/{os.getuid()}/{LABEL}").returncode == 0 if path.exists() else False
    return {"enabled": path.exists(), "loaded": loaded, "supervised": os.environ.get("TRADER_SUPERVISED") == "1", "path": str(path)}


def set_autostart(enabled: bool) -> dict:
    path = agent_path()
    domain = f"gui/{os.getuid()}"
    if enabled:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(plistlib.dumps(agent()))
        me = os.getpid()
        _launchctl("bootout", f"{domain}/{LABEL}")
        result = _launchctl("bootstrap", domain, str(path))
        if result.returncode != 0:
            raise SupervisorError(result.stderr.strip() or "launchctl bootstrap failed")
        if os.environ.get("TRADER_SUPERVISED") != "1":
            threading.Timer(1.0, lambda: os.kill(me, signal.SIGTERM)).start()
        return autostart()
    if os.environ.get("TRADER_SUPERVISED") == "1":
        log = processes.run_dir() / "serve.log"
        script = f"sleep 1; launchctl bootout {domain}/{LABEL}; rm -f {shlex.quote(str(path))}; sleep 2; exec {shlex.quote(str(Path(sys.executable).parent / 'trader'))} serve"
        with log.open("a") as out:
            subprocess.Popen(["/bin/sh", "-c", script], stdout=out, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, cwd=Path.cwd(), start_new_session=True)
        return {**autostart(), "enabled": False}
    _launchctl("bootout", f"{domain}/{LABEL}")
    path.unlink(missing_ok=True)
    return autostart()


def wait_for_port(port: int, timeout: float = 60.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return True
        time.sleep(1)
    return False


def _size(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file():
        return path.stat().st_size
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def stale_caches(now: float | None = None) -> list[Path]:
    cutoff = (now or time.time()) - KEEP_DAYS * 86400
    return sorted(p for p in (settings.data_dir / "quant" / "live").glob("bars_*.parquet") if p.stat().st_mtime < cutoff)


def disk() -> dict:
    global _sizes
    if _sizes is None or time.monotonic() - _sizes[0] > 60:
        root = settings.data_dir
        parts = {
            "quotes_cache": root / "quant" / "live",
            "quant": root / "quant",
            "klines": root / "klines",
            "ticks": root / "ticks",
            "funding": root / "funding",
            "universe": root / "universe",
            "pre_period": root.parent / "data_pre",
            "reports": settings.reports_dir,
            "logs": processes.run_dir(),
            "jobs": jobs.jobs_dir(),
            "journal": root / "trader.db",
        }
        _sizes = (time.monotonic(), [{"key": k, "bytes": _size(p)} for k, p in parts.items()])
    usage = shutil.disk_usage(settings.data_dir if settings.data_dir.exists() else Path.cwd())
    stale = stale_caches()
    return {
        "total": usage.total,
        "used": usage.used,
        "free": usage.free,
        "folders": _sizes[1],
        "stale": {"files": len(stale), "bytes": sum(p.stat().st_size for p in stale), "keep_days": KEEP_DAYS},
    }


def clean_caches() -> dict:
    global _sizes
    stale = stale_caches()
    freed = sum(p.stat().st_size for p in stale)
    for p in stale:
        p.unlink(missing_ok=True)
    _sizes = None
    return {"files": len(stale), "freed": freed}


LOGS = {"serve": "serve.log", "quant": "quant.log", "notice": "notice.log"}


def log_file(source: str) -> Path:
    if source in LOGS:
        return processes.run_dir() / LOGS[source]
    kind, _, ref = source.partition(":")
    if kind == "job":
        return jobs._path(ref).with_suffix(".log")
    raise SupervisorError(f"unknown log {source}")


def tail(path: Path, lines: int = 300, chunk: int = 256_000) -> tuple[list[str], int]:
    if not path.exists():
        return [], 0
    size = path.stat().st_size
    with path.open("rb") as f:
        f.seek(max(0, size - chunk))
        text = f.read().decode("utf-8", errors="replace").splitlines()
    return text[-lines:], size


def _stamp(raw: bytes) -> datetime:
    return datetime.strptime(raw.decode(), "%Y-%m-%d %H:%M:%S").astimezone(UTC)


def _since(path: Path, since: datetime, probe: int = 65_536) -> bytes:
    if not path.exists():
        return b""
    with path.open("rb") as f:
        lo, hi = 0, path.stat().st_size
        while hi - lo > probe:
            mid = (lo + hi) // 2
            f.seek(mid)
            m = LOG_STAMP.search(f.read(probe))
            lo, hi = (mid, hi) if m and _stamp(m.group(1)) < since else (lo, mid)
        f.seek(lo)
        return f.read()


def _detail(data: bytes, end: int) -> str:
    follow = data[end : end + 16_000].decode("utf-8", errors="replace").splitlines()[1:40]
    return next((x for x in follow if x and not x.startswith((" ", "Traceback"))), "").strip()


def errors(hours: int = 24, now: datetime | None = None) -> list[dict]:
    since = (now or datetime.now(UTC)) - timedelta(hours=hours)
    out = []
    for source, name in LOGS.items():
        data = _since(processes.run_dir() / name, since)
        hits = [m for m in LOG_FAILURE.finditer(data) if _stamp(m.group(1)) >= since]
        recent = [
            {"at": _stamp(m.group(1)).isoformat(timespec="seconds"), "line": m.group(2).decode("utf-8", errors="replace").strip(), "detail": _detail(data, m.end())}
            for m in hits[-3:]
        ]
        out.append({"source": source, "count": len(hits), "last_at": recent[-1]["at"] if recent else None, "recent": recent})
    return out


def schedule(now: datetime | None = None) -> list[dict]:
    from trader.quant import limit_test, paper, retrain

    now = now or datetime.now(UTC)
    due = datetime(now.year, now.month, now.day, 0, 15, tzinfo=UTC)
    due = due if now < due else due + timedelta(days=1)
    ledger = paper.ledger_path()
    history = json.loads(ledger.read_text())["history"] if ledger.exists() else []
    last = history[-1] if history else None
    orders = limit_test.path()
    last_limit = None
    if orders.exists() and orders.stat().st_size:
        last_limit = _iso(json.loads(orders.read_text().splitlines()[-1])["decided_at"] / 1000)
    meta = retrain.meta()
    return [
        {"key": "rebalance", "next": due.isoformat(timespec="seconds"), "last": last["rebalanced_at"] if last else None, "last_pnl": last.get("pnl_since_last") if last else None},
        {"key": "limit_test", "next": (due + timedelta(minutes=30)).isoformat(timespec="seconds"), "last": last_limit},
        {"key": "retrain", "next": "2027-01-02T00:00:00+00:00", "last": meta.get("trained_at")},
    ]
