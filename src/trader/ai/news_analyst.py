"""Claude as a news analyst: structured price-impact assessment of free-text news.

Exchange notices with a template are classified by rules (`services/events.py`) — instant and exact. Everything
else (media headlines, regulatory news, hacks, macro) goes through Claude, which returns a typed `NewsImpact`
with the tokens affected, direction, expected move, horizon and its confidence.
"""

from typing import Literal

from pydantic import BaseModel, Field

from trader.integrations.llm import LLM

SYSTEM = """You are a senior crypto-markets news analyst on a derivatives desk trading Binance USDⓈ-M perpetuals.
Assess how a news item moves token prices. Be calibrated and sceptical: most headlines are already priced in,
recycled, or irrelevant — say so (confidence low, magnitude ~0). Exchange listings, delistings, hacks/exploits,
regulatory actions, ETF decisions, token unlocks, protocol failures, major partnerships and macro shocks are the
categories that genuinely move prices. Name tokens by their exchange ticker (BTC, ETH, SOL, WIF…).
Magnitudes are the expected absolute move of the token's price in percent over the stated horizon."""


class TokenImpact(BaseModel):
    ticker: str = Field(description="exchange ticker, uppercase, e.g. SOL")
    direction: Literal["bullish", "bearish", "neutral"]
    expected_move_pct: float = Field(description="expected absolute price move in percent over the horizon")
    horizon_minutes: int = Field(description="when the move should be mostly done")
    confidence: float = Field(description="0..1 — probability the direction is right")


class NewsImpact(BaseModel):
    category: Literal["listing", "delisting", "hack_exploit", "regulation", "etf", "macro", "unlock_supply", "partnership_adoption", "protocol", "market_structure", "other"]
    is_new_information: bool = Field(description="false when recycled, already known or pure opinion")
    impacts: list[TokenImpact]
    market_wide_direction: Literal["bullish", "bearish", "neutral"] = Field(description="effect on the crypto market as a whole")
    summary: str = Field(description="one sentence, why it matters (or why it does not)")


async def assess(llm: LLM, title: str, summary: str | None = None, source: str | None = None, published_at: str | None = None) -> NewsImpact:
    body = f"Source: {source or 'unknown'}\nPublished: {published_at or 'unknown'}\nHeadline: {title}\n"
    if summary:
        body += f"Summary: {summary[:1500]}\n"
    return await llm.structured(NewsImpact, body, system=SYSTEM, effort="low", max_tokens=1500)


def actionable(impact: NewsImpact, min_confidence: float = 0.7, min_move_pct: float = 3.0) -> list[TokenImpact]:
    """Token impacts strong enough to act on — the gate between the LLM's opinion and an order."""
    if not impact.is_new_information:
        return []
    return [t for t in impact.impacts if t.direction != "neutral" and t.confidence >= min_confidence and t.expected_move_pct >= min_move_pct]
