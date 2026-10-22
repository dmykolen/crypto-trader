"""Anthropic Claude — the only module that talks to the LLM provider. Structured outputs only: every call
returns a validated Pydantic model, so callers never parse free text."""

from typing import Literal, TypeVar

from anthropic import AsyncAnthropic
from pydantic import BaseModel

from trader.core.config import settings
from trader.core.metrics import llm_calls_total

T = TypeVar("T", bound=BaseModel)
Effort = Literal["low", "medium", "high", "xhigh", "max"]


class LLMUnavailable(RuntimeError):
    """ANTHROPIC_API_KEY is not configured."""


class LLM:
    def __init__(self) -> None:
        key = settings.anthropic_api_key
        self._client = AsyncAnthropic(api_key=key.get_secret_value(), max_retries=3, timeout=180) if key else None

    @property
    def enabled(self) -> bool:
        return self._client is not None

    async def structured(self, schema: type[T], prompt: str, *, system: str, deep: bool = False, effort: Effort = "low", max_tokens: int = 4000) -> T:
        if self._client is None:
            raise LLMUnavailable("set ANTHROPIC_API_KEY to enable LLM features")
        model = settings.llm_deep_model if deep else settings.llm_fast_model
        try:
            response = await self._client.messages.parse(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": prompt}],
                output_format=schema,
                output_config={"effort": effort},
                **({"thinking": {"type": "adaptive"}} if deep else {}),
            )
        except Exception:
            llm_calls_total.labels(model, "error").inc()
            raise
        llm_calls_total.labels(model, "ok").inc()
        return response.parsed_output

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.close()
