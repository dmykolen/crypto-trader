"""Claude as a market analyst and strategy reviewer.

The analyst never invents numbers: it receives the app's own measurements — regime features, the multi-horizon
forecast with its out-of-sample accuracy, the walk-forward strategy choice, recent news — and writes a desk brief
with a structured view. The reviewer reads a research report and challenges it (overfitting, cost sensitivity,
regime dependence) before anything goes live.
"""

import json
from typing import Literal

from pydantic import BaseModel, Field

from trader.integrations.llm import LLM

ANALYST_SYSTEM = """You are the head of research on a crypto derivatives desk. You receive quantitative measurements
produced by the desk's own models for one Binance USDⓈ-M perpetual. Write a concise, decision-oriented brief.
Ground every statement in the numbers given; when model accuracy (out-of-sample AUC / hit-rate) is close to
coin-flip, say the forecast is weak and lower your conviction. Never recommend leverage above what the walk-forward
selection supports. Prefer "no trade" over a low-conviction trade."""

REVIEWER_SYSTEM = """You are a sceptical quantitative risk reviewer. You receive an out-of-sample backtest report of an
automated crypto strategy. Find what could make it fail live: overfitting / multiple testing, look-ahead, cost and
slippage sensitivity, latency assumptions, liquidity and capacity, regime dependence, survivorship, tail risk and
liquidation risk from leverage. Be concrete and quantitative where the report allows."""


class Horizon(BaseModel):
    horizon: str
    direction: Literal["up", "down", "flat"]
    conviction: float = Field(description="0..1")


class MarketBrief(BaseModel):
    symbol: str
    regime: Literal["trending_up", "trending_down", "ranging", "volatile_chop", "breakout"]
    outlook: list[Horizon]
    recommended_action: Literal["long", "short", "no_trade"]
    max_leverage: float
    key_levels: list[float] = Field(description="support/resistance prices worth watching")
    risks: list[str]
    brief: str = Field(description="3-6 sentences for the trader")


class StrategyReview(BaseModel):
    verdict: Literal["deploy", "deploy_small", "paper_trade_first", "reject"]
    strengths: list[str]
    weaknesses: list[str]
    failure_modes: list[str]
    suggested_tests: list[str]
    summary: str


async def market_brief(llm: LLM, symbol: str, measurements: dict) -> MarketBrief:
    prompt = f"Symbol: {symbol}\nMeasurements (JSON):\n{json.dumps(measurements, indent=1, default=str)[:30_000]}"
    return await llm.structured(MarketBrief, prompt, system=ANALYST_SYSTEM, deep=True, effort="medium", max_tokens=8000)


async def review_strategy(llm: LLM, report: dict) -> StrategyReview:
    prompt = f"Out-of-sample research report (JSON):\n{json.dumps(report, indent=1, default=str)[:60_000]}"
    return await llm.structured(StrategyReview, prompt, system=REVIEWER_SYSTEM, deep=True, effort="high", max_tokens=12000)
