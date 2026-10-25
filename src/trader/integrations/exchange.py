"""Binance USDⓈ-M trading through ccxt (async, authenticated). Only TRADING_MODE=live uses it.

Public market data lives in `integrations/binance.py`; this module places orders. Symbols are Binance ids
("WIFUSDT", "1000PEPEUSDT") on the way in and mapped to ccxt market symbols ("WIF/USDT:USDT") here.
"""

from contextlib import suppress

import ccxt.async_support as ccxt

from trader.core.config import settings


class Exchange:
    def __init__(self) -> None:
        if not (settings.binance_api_key and settings.binance_api_secret):
            raise RuntimeError("TRADING_MODE=live needs BINANCE_API_KEY / BINANCE_API_SECRET (or CCXT_API_KEY / CCXT_SECRET)")
        self._ex = ccxt.binanceusdm({
            "apiKey": settings.binance_api_key.get_secret_value(),
            "secret": settings.binance_api_secret.get_secret_value(),
            "enableRateLimit": True,
        })
        if settings.binance_testnet:
            self._ex.enable_demo_trading(True)

    async def market(self, symbol_id: str) -> str:
        await self._ex.load_markets()
        return self._ex.markets_by_id[symbol_id][0]["symbol"]

    async def price(self, symbol_id: str) -> float:
        ticker = await self._ex.fetch_ticker(await self.market(symbol_id))
        return float(ticker["last"] or ticker["close"])

    async def equity(self) -> float:
        balance = await self._ex.fetch_balance()
        return float(balance["total"].get("USDT") or 0.0)

    async def market_order(self, symbol_id: str, side: int, qty: float, *, leverage: float | None = None, reduce_only: bool = False, margin: str = "isolated") -> dict:
        """Market buy (side > 0) / sell. With `leverage` the symbol is first switched to `margin` mode at that leverage."""
        symbol = await self.market(symbol_id)
        if leverage is not None:
            with suppress(ccxt.ExchangeError):
                await self._ex.set_margin_mode(margin, symbol)
            await self._ex.set_leverage(int(leverage), symbol)
        amount = float(self._ex.amount_to_precision(symbol, qty))
        return await self._ex.create_order(symbol, "market", "buy" if side > 0 else "sell", amount, None, {"reduceOnly": True} if reduce_only else {})

    async def positions(self) -> dict[str, float]:
        """Open positions as Binance ids → signed contracts (long > 0)."""
        await self._ex.load_markets()
        out = {}
        for position in await self._ex.fetch_positions():
            qty = float(position.get("contracts") or 0.0)
            if qty:
                out[position["info"]["symbol"]] = qty if position.get("side") == "long" else -qty
        return out

    async def prices(self) -> dict[str, float]:
        """Last price of every perpetual in one request, keyed by Binance id."""
        await self._ex.load_markets()
        tickers = await self._ex.fetch_tickers()
        out = {}
        for symbol, ticker in tickers.items():
            market = self._ex.markets.get(symbol)
            price = ticker.get("last") or ticker.get("close")
            if market and price:
                out[market["id"]] = float(price)
        return out

    async def min_notional(self, symbol_id: str) -> float:
        market = self._ex.market(await self.market(symbol_id))
        return float(((market.get("limits") or {}).get("cost") or {}).get("min") or 5.0)

    def round_amount(self, symbol_id: str, qty: float) -> float:
        """Contracts rounded down to the symbol's step; 0 when below the smallest tradable amount."""
        try:
            return float(self._ex.amount_to_precision(self._ex.markets_by_id[symbol_id][0]["symbol"], qty))
        except (ccxt.InvalidOrder, KeyError, IndexError):
            return 0.0

    async def stop_order(self, symbol_id: str, position_side: int, qty: float, stop_price: float) -> dict:
        """Reduce-only stop-market that closes a `position_side` position when the price reaches `stop_price`."""
        symbol = await self.market(symbol_id)
        amount = float(self._ex.amount_to_precision(symbol, qty))
        trigger = float(self._ex.price_to_precision(symbol, stop_price))
        return await self._ex.create_order(symbol, "market", "sell" if position_side > 0 else "buy", amount, None, {"stopLossPrice": trigger, "reduceOnly": True})

    async def cancel_all(self, symbol_id: str) -> None:
        await self._ex.cancel_all_orders(await self.market(symbol_id))

    async def aclose(self) -> None:
        await self._ex.close()


InvalidOrder = ccxt.InvalidOrder
