import asyncio
import hashlib
import hmac
import json
import logging
import secrets
import time
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import websockets

from trader.services.events import Notice

log = logging.getLogger(__name__)

URL = "wss://api.binance.com/sapi/wss"
TOPIC = "com_announcement_en"


def signed_url(secret: str, topic: str = TOPIC, recv_window: int = 30000) -> str:
    params = {"random": secrets.token_hex(16), "recvWindow": str(recv_window), "timestamp": str(int(time.time() * 1000)), "topic": topic}
    payload = "&".join(f"{k}={params[k]}" for k in sorted(params))
    signature = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{URL}?{payload}&signature={signature}"


def parse(message: str | bytes) -> Notice | None:
    outer = json.loads(message)
    if outer.get("type") != "DATA":
        return None
    data = outer.get("data")
    inner = json.loads(data) if isinstance(data, str) else (data or {})
    title = inner.get("title")
    if not title:
        return None
    published = int(inner.get("publishDate") or time.time() * 1000)
    source_id = str(inner.get("id") or inner.get("code") or f"ws-{hashlib.sha1(title.encode()).hexdigest()[:16]}")
    return Notice("binance", source_id, title, datetime.fromtimestamp(published / 1000, UTC), None)


async def announcements(api_key: str, secret: str, topic: str = TOPIC) -> AsyncIterator[tuple[Notice, float, dict]]:
    backoff = 1.0
    while True:
        try:
            async with websockets.connect(signed_url(secret, topic), additional_headers={"X-MBX-APIKEY": api_key}, ping_interval=25, open_timeout=15) as ws:
                backoff = 1.0
                log.info("binance announcement stream connected")
                async for message in ws:
                    received = time.time()
                    raw = json.loads(message)
                    notice = parse(message)
                    if notice is not None:
                        yield notice, received, raw
                    elif raw.get("type") not in ("COMMAND", "PING", None):
                        log.info("binance announcement stream: %s", str(raw)[:300])
        except (websockets.ConnectionClosed, websockets.InvalidStatus, OSError, TimeoutError) as exc:
            log.warning("binance announcement stream dropped: %s", exc)
        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, 60.0)
