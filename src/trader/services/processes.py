"""Bot processes run from the web UI: one background process per bot, in paper or live mode, with its own log."""

import json
import os
import shlex
import signal
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from trader.core.config import settings

COMMANDS = {
    ("notice", "paper"): ["run"],
    ("notice", "live"): ["run"],
    ("quant", "paper"): ["quant", "paper", "--loop"],
    ("quant", "live"): ["quant", "live", "--loop"],
}
BOTS = ("notice", "quant")


class ProcessError(RuntimeError):
    pass


def run_dir() -> Path:
    return settings.data_dir / "run"


def log_path(bot: str) -> Path:
    return run_dir() / f"{bot}.log"


def _state_path(bot: str) -> Path:
    return run_dir() / f"{bot}.json"


def _script() -> str:
    return str(Path(sys.executable).parent / "trader")


def classify(command: str) -> tuple[str, str] | None:
    """Which bot (and, where the arguments say it, which mode) a process command line belongs to."""
    try:
        tokens = shlex.split(command)
    except ValueError:
        return None
    for i, token in enumerate(tokens):
        if Path(token).name == "trader" and (i == 0 or Path(tokens[i - 1]).name.startswith("python")):
            args = tokens[i + 1 :]
            for (bot, mode), expected in COMMANDS.items():
                if args == expected:
                    return bot, mode
    return None


def _ps() -> list[tuple[int, str, str]]:
    out = subprocess.run(["ps", "-axo", "pid=,lstart=,command="], capture_output=True, text=True, check=False).stdout
    rows = []
    for line in out.splitlines():
        parts = line.split(None, 6)
        if len(parts) == 7 and parts[0].isdigit():
            rows.append((int(parts[0]), " ".join(parts[1:6]), parts[6]))
    return rows


def _env_live(pid: int) -> bool:
    out = subprocess.run(["ps", "eww", "-o", "command=", "-p", str(pid)], capture_output=True, text=True, check=False).stdout
    return "TRADING_MODE=live" in out


def _started(lstart: str) -> datetime | None:
    try:
        return datetime.strptime(lstart, "%a %b %d %H:%M:%S %Y").astimezone(UTC)
    except ValueError:
        return None


def status() -> dict[str, dict]:
    found: dict[str, dict] = {}
    for pid, lstart, command in _ps():
        hit = classify(command)
        if hit is None or pid == os.getpid():
            continue
        bot, mode = hit
        if bot == "notice" and _env_live(pid):
            mode = "live"
        started = _started(lstart)
        found[bot] = {"pid": pid, "mode": mode, "started_at": started.isoformat(timespec="seconds") if started else None}
    out = {}
    for bot in BOTS:
        state = json.loads(_state_path(bot).read_text()) if _state_path(bot).exists() else {}
        proc = found.get(bot)
        managed = bool(proc and state.get("pid") == proc["pid"])
        started_at = proc["started_at"] if proc else None
        uptime = (datetime.now(UTC) - datetime.fromisoformat(started_at)).total_seconds() if started_at else None
        out[bot] = {
            "bot": bot,
            "running": proc is not None,
            "pid": proc["pid"] if proc else None,
            "mode": proc["mode"] if proc else state.get("mode", "paper"),
            "started_at": started_at,
            "uptime_s": round(uptime) if uptime is not None else None,
            "managed": managed,
            "log": str(log_path(bot)) if log_path(bot).exists() else None,
            "last_log_at": datetime.fromtimestamp(log_path(bot).stat().st_mtime, UTC).isoformat(timespec="seconds") if log_path(bot).exists() else None,
            "last_stop": state.get("stopped_at"),
        }
    return out


def live_ready() -> bool:
    return bool(settings.binance_api_key and settings.binance_api_secret)


def start(bot: str, mode: str) -> dict:
    if (bot, mode) not in COMMANDS:
        raise ProcessError(f"unknown bot or mode: {bot}/{mode}")
    if status()[bot]["running"]:
        raise ProcessError(f"bot {bot} is already running; stop it first")
    if mode == "live" and not live_ready():
        raise ProcessError("real-money mode needs BINANCE_API_KEY and BINANCE_API_SECRET in .env")
    run_dir().mkdir(parents=True, exist_ok=True)
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env["TRADING_MODE"] = mode
    env["PYTHONUNBUFFERED"] = "1"
    with log_path(bot).open("a") as log:
        log.write(f"\n=== {datetime.now(UTC).isoformat(timespec='seconds')} start {bot} in {mode} mode ===\n")
        log.flush()
        proc = subprocess.Popen(
            [_script(), *COMMANDS[(bot, mode)]], stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, env=env, cwd=Path.cwd(), start_new_session=True
        )
    _state_path(bot).write_text(json.dumps({"pid": proc.pid, "mode": mode, "started_at": datetime.now(UTC).isoformat(timespec="seconds")}))
    return {"bot": bot, "mode": mode, "pid": proc.pid}


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def stop(bot: str, timeout: float = 15.0) -> dict:
    current = status().get(bot)
    if current is None or not current["running"]:
        raise ProcessError(f"bot {bot} is not running")
    pid = current["pid"]
    os.kill(pid, signal.SIGTERM)
    deadline = time.monotonic() + timeout
    while _alive(pid) and time.monotonic() < deadline:
        time.sleep(0.2)
    forced = _alive(pid)
    if forced:
        os.kill(pid, signal.SIGKILL)
    state = json.loads(_state_path(bot).read_text()) if _state_path(bot).exists() else {}
    state.update({"stopped_at": datetime.now(UTC).isoformat(timespec="seconds"), "mode": current["mode"]})
    run_dir().mkdir(parents=True, exist_ok=True)
    _state_path(bot).write_text(json.dumps(state))
    if log_path(bot).exists():
        with log_path(bot).open("a") as log:
            log.write(f"=== {state['stopped_at']} stopped {bot} (pid {pid}{', killed' if forced else ''}) ===\n")
    return {"bot": bot, "pid": pid, "forced": forced}


def restore() -> list[str]:
    started = []
    for bot in BOTS:
        state = json.loads(_state_path(bot).read_text()) if _state_path(bot).exists() else {}
        if state.get("pid") and not state.get("stopped_at") and state.get("mode") == "paper" and not status()[bot]["running"]:
            start(bot, "paper")
            started.append(bot)
    return started


def logs(bot: str, lines: int = 200) -> list[str]:
    path = log_path(bot)
    if not path.exists():
        return []
    with path.open("rb") as f:
        f.seek(0, os.SEEK_END)
        size = f.tell()
        f.seek(max(0, size - 256_000))
        tail = f.read().decode("utf-8", errors="replace").splitlines()
    return tail[-lines:]
