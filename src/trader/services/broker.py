"""Brokers — where orders go. Both expose the same small interface (`Broker`):

* `PaperBroker` fills at the live Binance price with the backtest's event cost model (taker fee + slippage), so
  paper results are comparable with the research reports;
* `LiveBroker` trades Binance USDⓈ-M through ccxt: isolated margin, leverage per trade, market orders, plus an
  exchange-side reduce-only stop as a safety net for when the bot is not running.
"""

import asyncio
from contextlib import suppress
from dataclasses import dataclass
from typing import Protocol

from trader.core.config import settings
from trader.integrations import binance
from trader.integrations.exchange import Exchange, InvalidOrder


@dataclass(frozen=True)
class Fill:
    price: float
    qty: float
    fee: float


class Broker(Protocol):
    mode: str

    async def price(self, symbol: str) -> float: ...
    async def equity(self) -> float | None: ...  # None → derive it from the trade journal (paper)
    async def open(self, symbol: str, side: int, qty: float, leverage: float) -> Fill: ...
    async def protect(self, symbol: str, side: int, qty: float, stop: float) -> None: ...
    async def close(self, symbol: str, side: int, qty: float) -> Fill | None: ...  # None → already flat on the exchange
    async def aclose(self) -> None: ...


class PaperBroker:
    mode = "paper"

    def __init__(self, rest: binance.FuturesREST | None = None) -> None:
        self._rest = rest or binance.FuturesREST()

    async def price(self, symbol: str) -> float:
        return await asyncio.to_thread(self._rest.last_price, symbol)

    async def equity(self) -> float | None:
        return None

    async def _fill(self, symbol: str, side: int, qty: float) -> Fill:
        px = await self.price(symbol) * (1 + side * settings.event_slippage)
        return Fill(px, qty, qty * px * settings.taker_fee)

    async def open(self, symbol: str, side: int, qty: float, leverage: float) -> Fill:
        return await self._fill(symbol, side, qty)

    async def protect(self, symbol: str, side: int, qty: float, stop: float) -> None:
        return None  # the trader's monitor enforces paper stops

    async def close(self, symbol: str, side: int, qty: float) -> Fill | None:
        return await self._fill(symbol, -side, qty)

    async def aclose(self) -> None:
        return None


def _filled(order: dict, fallback_price: float, fallback_qty: float) -> Fill:
    price = float(order.get("average") or order.get("price") or fallback_price)
    qty = float(order.get("filled") or order.get("amount") or fallback_qty)
    fee = (order.get("fee") or {}).get("cost")
    return Fill(price, qty, float(fee) if fee is not None else qty * price * settings.taker_fee)


class LiveBroker:
    mode = "live"

    def __init__(self, exchange: Exchange | None = None) -> None:
        self._ex = exchange or Exchange()

    async def price(self, symbol: str) -> float:
        return await self._ex.price(symbol)

    async def equity(self) -> float | None:
        return await self._ex.equity()

    async def open(self, symbol: str, side: int, qty: float, leverage: float) -> Fill:
        reference = await self.price(symbol)
        return _filled(await self._ex.market_order(symbol, side, qty, leverage=leverage), reference, qty)

    async def protect(self, symbol: str, side: int, qty: float, stop: float) -> None:
        await self._ex.stop_order(symbol, side, qty, stop)

    async def close(self, symbol: str, side: int, qty: float) -> Fill | None:
        with suppress(Exception):
            await self._ex.cancel_all(symbol)
        reference = await self.price(symbol)
        try:
            return _filled(await self._ex.market_order(symbol, -side, qty, reduce_only=True), reference, qty)
        except InvalidOrder:  # reduce-only rejected: the exchange stop or a liquidation already closed it
            return None

    async def aclose(self) -> None:
        await self._ex.aclose()
