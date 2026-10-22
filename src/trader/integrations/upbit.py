"""Upbit (Korea's largest exchange) notices. A KRW-market listing or an investment-warning designation there
moves the token's Binance perpetual within seconds, so the notice board is a first-class news source."""

import asyncio

import httpx

NOTICES = "https://api-manager.upbit.com/api/v1/announcements"
NOTICE_URL = "https://upbit.com/service_center/notice?id={id}"
_HEADERS = {"User-Agent": "Mozilla/5.0 (trader research bot)", "Accept": "application/json"}


async def notices(client: httpx.AsyncClient, page: int = 1, per_page: int = 20, category: str = "trade") -> tuple[list[dict], int]:
    """One page, newest first → ([{id, title, first_listed_at, listed_at, ...}], total_pages)."""
    for attempt in range(8):
        response = await client.get(NOTICES, params={"os": "web", "page": page, "per_page": per_page, "category": category}, headers=_HEADERS)
        if response.status_code in (418, 429):
            await asyncio.sleep(3 * (attempt + 1))
            continue
        response.raise_for_status()
        data = response.json()["data"]
        return data["notices"], data["total_pages"]
    raise RuntimeError("Upbit kept rate-limiting the notice board")
