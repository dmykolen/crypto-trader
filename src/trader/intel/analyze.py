"""Item analysis: instant rule tagging of every item (category, polarity, linked symbols) and an optional, budgeted
Claude deep assessment (`ai/news_analyst.assess`) for the items most likely to matter.

Rule tags live in `NewsItem.analysis["intel"]`; Claude's `NewsImpact` is merged at the top level of the same dict,
the shape the trading loop already reads (`analysis["category"]`).
"""

import logging
import re
from datetime import UTC, datetime, timedelta

from sqlmodel import Session

from trader.intel.entities import Linker
from trader.models import NewsItem

log = logging.getLogger(__name__)

CATEGORIES: list[tuple[str, re.Pattern]] = [
    ("delisting", re.compile(r"\b(delist\w*|will remove|removal of|cease trading|trading halt for|monitoring tag|investment warning|caution designation)\b", re.I)),
    (
        "listing",
        re.compile(
            r"\b(will list|lists?\b|listing|listed|launch(?:es)? (?:spot|perpetual|futures)|new (?:spot|perpetual|futures) (?:pair|contract)"
            r"|token splash|launchpool|adds? support)\b",
            re.I,
        ),
    ),
    ("hack_exploit", re.compile(r"\b(hack\w*|exploit\w*|drain\w*|stolen|breach\w*|attacker|rug ?pull|phishing|compromised|vulnerabilit\w+)\b", re.I)),
    ("lawsuit", re.compile(r"\b(lawsuit|sues?|sued|charges?d?|indict\w*|court|judge|settle\w*|class action|plea|fraud trial|convicted|sentenced)\b", re.I)),
    ("etf", re.compile(r"\b(etfs?|etps?|exchange-traded|spot fund|grayscale trust|ishares|19b-4|s-1 filing)\b", re.I)),
    (
        "regulation",
        re.compile(r"\b(sec|cftc|regulat\w+|legislat\w+|bill|ban(?:s|ned)?|licen[cs]e\w*|mica|compliance|sanction\w*|treasury|congress|senate|stablecoin law|policy)\b", re.I),
    ),
    ("unlock_supply", re.compile(r"\b(unlock\w*|vesting|token release|emission|inflation schedule|supply shock|cliff)\b", re.I)),
    ("airdrop", re.compile(r"\b(airdrop\w*|claim(?:able)? tokens?|snapshot|retroactive)\b", re.I)),
    ("burn_buyback", re.compile(r"\b(burn\w*|buyback\w*|buy back|repurchase)\b", re.I)),
    ("outage", re.compile(r"\b(outage|halted|downtime|suspend\w*|maintenance|network stall\w*|chain halt|deposits? (?:and withdrawals? )?(?:closed|paused)|congestion)\b", re.I)),
    ("protocol_upgrade", re.compile(r"\b(upgrade|hard ?fork|mainnet|testnet|v\d(?:\.\d)?\b|launch(?:es|ed)? on|eip-\d+|improvement proposal|roadmap)\b", re.I)),
    ("partnership_adoption", re.compile(r"\b(partner\w*|integrat\w*|adopt\w*|collaborat\w*|accepts?|treasury (?:buys?|adds?)|reserve|acquir\w*|acquisition|onboard\w*)\b", re.I)),
    (
        "macro",
        re.compile(
            r"\b(fed|fomc|rate (?:cut|hike)s?|inflation|cpi|ppi|jobs report|nonfarm|payrolls|recession|tariffs?|treasury yields?|dollar index|dxy|powell|gdp|central bank)\b", re.I
        ),
    ),
]
EVENT_CATEGORY = {"listing": "listing", "delisting": "delisting", "warning": "delisting", "caution": "delisting", "monitoring": "delisting", "new_perp": "listing"}
HIGH_IMPACT = {"listing", "delisting", "hack_exploit", "regulation", "lawsuit", "etf", "unlock_supply", "outage", "burn_buyback", "macro"}

POSITIVE = {
    "surge": 1.0,
    "surges": 1.0,
    "soar": 1.0,
    "soars": 1.0,
    "rally": 0.8,
    "rallies": 0.8,
    "jump": 0.7,
    "jumps": 0.7,
    "gain": 0.5,
    "gains": 0.5,
    "bullish": 1.0,
    "breakout": 0.7,
    "record": 0.5,
    "high": 0.3,
    "highs": 0.4,
    "ath": 0.8,
    "approve": 0.8,
    "approved": 0.8,
    "approval": 0.7,
    "inflow": 0.6,
    "inflows": 0.6,
    "partnership": 0.5,
    "adoption": 0.6,
    "launch": 0.3,
    "launches": 0.3,
    "list": 0.5,
    "listing": 0.5,
    "upgrade": 0.4,
    "win": 0.6,
    "wins": 0.6,
    "won": 0.6,
    "recover": 0.5,
    "recovers": 0.5,
    "rebound": 0.6,
    "rebounds": 0.6,
    "buy": 0.3,
    "buys": 0.4,
    "accumulate": 0.6,
    "accumulation": 0.6,
    "outperform": 0.6,
    "boost": 0.5,
    "boosts": 0.5,
    "growth": 0.4,
    "positive": 0.5,
    "optimism": 0.5,
    "dismissed": 0.6,
    "buyback": 0.6,
    "burn": 0.3,
    "green": 0.3,
    "climb": 0.5,
    "climbs": 0.5,
    "rise": 0.4,
    "rises": 0.4,
}
NEGATIVE = {
    "crash": 1.0,
    "crashes": 1.0,
    "plunge": 1.0,
    "plunges": 1.0,
    "dump": 0.8,
    "dumps": 0.8,
    "drop": 0.6,
    "drops": 0.6,
    "fall": 0.5,
    "falls": 0.5,
    "slide": 0.5,
    "slides": 0.5,
    "slump": 0.7,
    "bearish": 1.0,
    "loss": 0.5,
    "losses": 0.6,
    "hack": 1.0,
    "hacked": 1.0,
    "exploit": 1.0,
    "exploited": 1.0,
    "stolen": 1.0,
    "drained": 1.0,
    "lawsuit": 0.7,
    "sues": 0.7,
    "sued": 0.7,
    "charged": 0.7,
    "fraud": 0.9,
    "ban": 0.8,
    "bans": 0.8,
    "banned": 0.8,
    "delist": 1.0,
    "delists": 1.0,
    "delisting": 1.0,
    "reject": 0.8,
    "rejects": 0.8,
    "rejected": 0.8,
    "outflow": 0.6,
    "outflows": 0.6,
    "liquidation": 0.6,
    "liquidations": 0.6,
    "liquidated": 0.6,
    "sell-off": 0.8,
    "selloff": 0.8,
    "fear": 0.5,
    "warning": 0.5,
    "warns": 0.5,
    "risk": 0.3,
    "outage": 0.7,
    "halt": 0.7,
    "halted": 0.7,
    "suspend": 0.6,
    "suspends": 0.6,
    "suspended": 0.6,
    "unlock": 0.4,
    "investigation": 0.6,
    "probe": 0.5,
    "decline": 0.5,
    "declines": 0.5,
    "red": 0.3,
    "sink": 0.6,
    "sinks": 0.6,
    "tumble": 0.8,
    "tumbles": 0.8,
    "collapse": 1.0,
    "bankrupt": 1.0,
    "bankruptcy": 1.0,
    "insolvent": 1.0,
}
NEGATORS = {"not", "no", "never", "without", "denies", "deny", "fails", "failed"}
WORD = re.compile(r"[a-z][a-z\-]*")


def category(text: str, events: list[dict] | None = None) -> tuple[str, list[str]]:
    """Primary category (first matching rule, or the rule event's) and every category that matched."""
    found = [name for name, pattern in CATEGORIES if pattern.search(text)]
    for event in events or []:
        etype = str(event.get("type", ""))
        for needle, cat in EVENT_CATEGORY.items():
            if needle in etype and cat not in found:
                found.insert(0, cat)
    return (found[0] if found else "other"), found


def polarity(text: str) -> float:
    """Lexicon polarity in [-1, 1]: (pos - neg) / (pos + neg + 1), a preceding negator flips a word."""
    words = WORD.findall(text.lower())
    pos = neg = 0.0
    for i, word in enumerate(words):
        flip = any(w in NEGATORS for w in words[max(0, i - 2) : i])
        if word in POSITIVE:
            pos, neg = (pos, neg + POSITIVE[word]) if flip else (pos + POSITIVE[word], neg)
        elif word in NEGATIVE:
            pos, neg = (pos + NEGATIVE[word], neg) if flip else (pos, neg + NEGATIVE[word])
    return round((pos - neg) / (pos + neg + 1.0), 4)


def tag(item: NewsItem, linker: Linker) -> dict:
    title = item.title or ""
    text = f"{title}. {_plain(item.summary)[:600]}"
    primary, cats = category(title, item.events)
    if primary == "other":
        primary, cats = category(text, item.events)
    symbols = linker.link(title) or linker.link(text)
    events_symbols = [s for s in (linker.bases.get(str(e.get("token", "")).upper()) for e in item.events or []) if s]
    return {"category": primary, "categories": cats, "polarity": polarity(title) if title else 0.0, "symbols": list(dict.fromkeys(events_symbols + symbols))}


def _plain(html: str | None) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html or "")).strip()


def tag_items(session: Session, items: list[NewsItem], linker: Linker, *, force: bool = False) -> int:
    """Write rule tags into `analysis["intel"]` for items that lack them (all of them with `force`)."""
    n = 0
    for item in items:
        if not force and (item.analysis or {}).get("intel"):
            continue
        item.analysis = {**(item.analysis or {}), "intel": tag(item, linker)}
        session.add(item)
        n += 1
    session.commit()
    return n


def deep_candidates(items: list[NewsItem], max_age: timedelta = timedelta(hours=6), now: datetime | None = None) -> list[NewsItem]:
    """Items worth a Claude call: recent, not yet assessed, high-impact category or linked to a perp; boards first."""
    now = now or datetime.now(UTC)
    out = []
    for item in items:
        analysis = item.analysis or {}
        intel = analysis.get("intel") or {}
        if "impacts" in analysis or now - item.published_at.astimezone(UTC) > max_age:
            continue
        if intel.get("category") in HIGH_IMPACT or intel.get("symbols"):
            out.append(item)
    board = ("binance", "upbit", "bybit", "okx", "kucoin")
    return sorted(out, key=lambda i: (i.source not in board, (i.analysis or {}).get("intel", {}).get("category") not in HIGH_IMPACT, -i.published_at.timestamp()))


async def deep_analyze(session: Session, llm, items: list[NewsItem], budget: int = 20) -> int:
    """Claude assessment of at most `budget` candidates; results merged into `analysis` (rule tags kept)."""
    from trader.ai.news_analyst import assess

    if llm is None or not llm.enabled or budget <= 0:
        return 0
    done = 0
    for item in deep_candidates(items)[:budget]:
        try:
            impact = await assess(llm, item.title, _plain(item.summary), item.source, item.published_at.isoformat())
        except Exception as exc:
            log.warning("Claude assessment of %s failed: %s", item.id, exc)
            continue
        item.analysis = {**(item.analysis or {}), **impact.model_dump()}
        session.add(item)
        session.commit()
        done += 1
    return done


def llm_scores(analysis: dict | None, linker: Linker) -> dict[str, float]:
    """Per-symbol signed Claude score: sum of direction * confidence * expected move %, zero when not new information."""
    analysis = analysis or {}
    if not analysis.get("impacts") or not analysis.get("is_new_information", False):
        return {}
    out: dict[str, float] = {}
    for impact in analysis["impacts"]:
        symbol = linker.bases.get(str(impact.get("ticker", "")).upper())
        sign = {"bullish": 1.0, "bearish": -1.0}.get(impact.get("direction"), 0.0)
        if symbol and sign:
            out[symbol] = out.get(symbol, 0.0) + sign * float(impact.get("confidence", 0)) * float(impact.get("expected_move_pct", 0))
    return out
