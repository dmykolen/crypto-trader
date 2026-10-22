"""Exchange notices → typed, tradable events.

Exchange notices follow strict templates, so a rule-based parser classifies them in microseconds with no
false positives — that matters because the reaction happens in the first seconds. Free-text media news has
no template; `ai/news_analyst.py` triages it with Claude instead.

Every event type here has a playbook learned from history (`services/playbooks.py`).
"""

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum


class EventType(StrEnum):
    UPBIT_KRW_LISTING = "upbit_krw_listing"  # new KRW market on Upbit — the strongest retail-flow catalyst
    UPBIT_LISTING = "upbit_listing"  # BTC/USDT-market only listing on Upbit
    UPBIT_WARNING = "upbit_warning"  # 유의 종목 지정 — investment-warning designation (delisting risk)
    UPBIT_DELISTING = "upbit_delisting"  # 거래지원 종료 — end of trading support
    BINANCE_SPOT_LISTING = "binance_spot_listing"
    BINANCE_SPOT_DELISTING = "binance_spot_delisting"
    BINANCE_MONITORING_TAG = "binance_monitoring_tag"
    BINANCE_PERP_DELISTING = "binance_perp_delisting"


@dataclass(frozen=True)
class Notice:
    source: str  # "upbit" | "binance"
    source_id: str
    title: str
    published_at: datetime
    url: str | None = None


@dataclass(frozen=True)
class Event:
    type: EventType
    token: str  # base asset, e.g. "WIF"
    notice: Notice


_TICKER = r"[A-Z0-9][A-Z0-9.]{1,14}"
_NOT_TOKENS = {"KRW", "BTC", "USDT", "USDC", "ETH", "USD", "NFT", "API", "VIP", "UTC", "KST", "M", "COIN", "USDⓈ", "ALL", "AND"}


def _tickers(text: str) -> list[str]:
    found = re.findall(rf"\(({_TICKER})\)", text) or re.findall(rf"\b({_TICKER})\b", text)
    return list(dict.fromkeys(t for t in found if t not in _NOT_TOKENS and not t.isdigit()))


def _strip_updates(title: str) -> str:
    """Drop trailing "(… 안내)" / "(완료)" update notes Upbit appends to a notice after it was first published —
    the market reacted to the original title, so history must be classified on that."""
    while title.endswith(")"):
        depth, i = 0, len(title) - 1
        for i in range(len(title) - 1, -1, -1):
            depth += {")": 1, "(": -1}.get(title[i], 0)
            if depth == 0:
                break
        note = title[i + 1 : -1]
        if not any(word in note for word in ("안내", "완료", "변경", "연기")):
            break
        title = title[:i].rstrip()
    return title


def _upbit(notice: Notice) -> list[Event]:
    title = _strip_updates(notice.title)
    if "해제" in title or "연장" in title or "취소" in title:  # lifted / extended / cancelled: no new information
        return []
    if "신규 거래지원" in title or "디지털 자산 추가" in title or "코인 추가" in title:
        head = title.split("안내")[0] if "신규 거래지원" in title else title
        markets_part = re.search(r"\(([A-Z, ]+)\s*마켓\)", title) or re.search(r"([A-Z, ]+)\s*마켓", title)
        markets = markets_part.group(1) if markets_part else ""
        krw = "KRW" in markets or "원화" in title
        if "마켓 신규 거래지원 안내" in title or "마켓 디지털 자산 추가 (" in title or "마켓 코인 추가 (" in title:
            listed = re.search(r"\(([^()]*)\)\s*(?:\(|$)", title.split("마켓", 1)[1])  # "(BICO, BMT, …)" after the market list
            names = _tickers(listed.group(1)) if listed else []
        else:
            names = _tickers(head)
        kind = EventType.UPBIT_KRW_LISTING if krw else EventType.UPBIT_LISTING
        return [Event(kind, t, notice) for t in names]
    if "유의 종목 지정" in title or "유의종목 지정" in title:
        return [Event(EventType.UPBIT_WARNING, t, notice) for t in _tickers(title)]
    if "거래지원 종료" in title or "거래 지원 종료" in title:
        return [Event(EventType.UPBIT_DELISTING, t, notice) for t in _tickers(title.split(" - ")[0])]
    return []


def _binance(notice: Notice) -> list[Event]:
    title = notice.title
    if title.startswith("Binance Will List "):
        return [Event(EventType.BINANCE_SPOT_LISTING, t, notice) for t in re.findall(rf"\(({_TICKER})\)", title)]
    if title.startswith("Binance Will Delist "):
        body = title.removeprefix("Binance Will Delist ").split(" on ")[0]
        return [Event(EventType.BINANCE_SPOT_DELISTING, t, notice) for t in _tickers(body.replace("&", ","))]
    if title.startswith("Binance Will Extend the Monitoring Tag to Include "):
        body = title.removeprefix("Binance Will Extend the Monitoring Tag to Include ").split(" on ")[0].split(", Remove")[0]
        return [Event(EventType.BINANCE_MONITORING_TAG, t, notice) for t in _tickers(body.replace("&", ","))]
    perp = re.match(r"^Binance Futures Will Delist (.*?)(?:USDⓈ-M|Perpetual)", title)
    if perp:
        return [Event(EventType.BINANCE_PERP_DELISTING, s.removesuffix("USDT"), notice) for s in re.findall(r"\b([A-Z0-9]{2,20}USDT)\b", title)]
    return []


def classify(notice: Notice) -> list[Event]:
    """All tradable events a notice announces (one per token); empty when it is not tradable."""
    return _upbit(notice) if notice.source == "upbit" else _binance(notice) if notice.source == "binance" else []


def upbit_notice(raw: dict) -> Notice:
    return Notice("upbit", str(raw["id"]), raw["title"], datetime.fromisoformat(raw["first_listed_at"]).astimezone(UTC), f"https://upbit.com/service_center/notice?id={raw['id']}")


def binance_notice(raw: dict) -> Notice:
    published = datetime.fromtimestamp(raw["releaseDate"] / 1000, UTC)
    return Notice("binance", str(raw["id"]), raw["title"], published, f"https://www.binance.com/en/support/announcement/{raw['code']}")
