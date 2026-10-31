"""Bot #2 with real money: the day's target book → exchange orders, with guards.

`plan` is pure — it turns target weights, the held positions, prices and equity into an ordered list of market orders
(reduce-only first so margin frees up before anything grows). `LiveBook` reads the account, plans and executes on
cross margin: isolated margin at ordinary leverage would liquidate every short on a ~20 % squeeze, which is exactly
the stop that the research showed destroys this book (docs/RESEARCH.md Q22). A drawdown kill switch on the whole account
closes everything and halts the bot instead.
"""

import asyncio
import json
import logging
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta

from trader.core.config import settings
from trader.quant import neutral, paper

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Order:
    symbol: str
    side: int
    qty: float
    reduce_only: bool
    notional: float
    reason: str


@dataclass(frozen=True)
class Limits:
    min_notional: float = 5.0
    max_gross: float = 3.0
    max_position: float = 0.3
    leverage: int = 5
    kill_drawdown: float = 0.35


def _sign(x: float) -> int:
    return 1 if x > 0 else -1 if x < 0 else 0


def plan(target: dict[str, float], positions: dict[str, float], prices: dict[str, float], equity: float, band: float, limits: Limits, round_qty) -> list[Order]:
    """Orders that move `positions` (signed contracts) to `target` (weights of equity); reduce-only orders come first."""
    if equity <= 0:
        return []
    wanted = {s: max(-limits.max_position, min(limits.max_position, w)) for s, w in target.items() if abs(w) > 1e-9 and prices.get(s)}
    gross = sum(abs(w) for w in wanted.values())
    if gross > limits.max_gross:
        wanted = {s: w * limits.max_gross / gross for s, w in wanted.items()}
    reduce, grow = [], []
    for sym in sorted(set(positions) | set(wanted)):
        price = prices.get(sym)
        if not price:
            continue
        cur_q = positions.get(sym, 0.0)
        cur_w = cur_q * price / equity
        tgt_w = wanted.get(sym, 0.0)
        if tgt_w == 0.0:
            if cur_q:
                reduce.append(Order(sym, -_sign(cur_q), abs(cur_q), True, abs(cur_q) * price, "close"))
            continue
        if cur_q and _sign(cur_w) == _sign(tgt_w) and abs(tgt_w - cur_w) <= band:
            continue
        tgt_q = tgt_w * equity / price
        flipped = bool(cur_q) and _sign(cur_q) != _sign(tgt_q)
        if flipped:
            reduce.append(Order(sym, -_sign(cur_q), abs(cur_q), True, abs(cur_q) * price, "flip-close"))
            cur_q = 0.0
        delta = tgt_q - cur_q
        qty = round_qty(sym, abs(delta))
        if qty <= 0:
            continue
        notional = qty * price
        if cur_q and abs(tgt_q) < abs(cur_q):
            reduce.append(Order(sym, _sign(delta), qty, True, notional, "reduce"))
        elif notional >= limits.min_notional:
            grow.append(Order(sym, _sign(delta), qty, False, notional, "flip-open" if flipped else "increase" if cur_q else "open"))
    return reduce + grow


def ledger_path():
    return settings.data_dir / "quant" / "live" / "ledger.json"


def load_ledger() -> dict:
    path = ledger_path()
    return json.loads(path.read_text()) if path.exists() else {"peak_equity": None, "halted": False, "history": []}


def save_ledger(state: dict) -> None:
    ledger_path().parent.mkdir(parents=True, exist_ok=True)
    ledger_path().write_text(json.dumps(state, indent=2, default=str))


class LiveBook:
    def __init__(self, exchange=None, limits: Limits | None = None) -> None:
        if exchange is None:
            from trader.integrations.exchange import Exchange

            exchange = Exchange()
        self.ex = exchange
        self.limits = limits or Limits()

    async def rebalance(self, target: dict[str, float], band: float, dry_run: bool = False) -> dict:
        equity = await self.ex.equity()
        positions = await self.ex.positions()
        prices = await self.ex.prices()
        orders = plan(target, positions, prices, equity, band, self.limits, self.ex.round_amount)
        fills = []
        for order in [] if dry_run else orders:
            try:
                leverage = None if order.reduce_only else self.limits.leverage
                done = await self.ex.market_order(order.symbol, order.side, order.qty, leverage=leverage, reduce_only=order.reduce_only, margin="cross")
                fills.append({**asdict(order), "status": "filled", "price": done.get("average"), "order_id": done.get("id")})
            except Exception as exc:
                log.warning("live order %s failed: %s", order, exc)
                fills.append({**asdict(order), "status": "error", "error": str(exc)})
        return {"equity": equity, "positions_before": len(positions), "orders": [asdict(o) for o in orders], "fills": fills, "dry_run": dry_run}

    async def aclose(self) -> None:
        await self.ex.aclose()


def step(now: datetime | None = None, dry_run: bool = False, exchange=None) -> dict:
    """One live rebalance: the same target book as the paper bot, checked against the account's kill switch."""
    now = now or datetime.now(UTC)
    today = f"{now:%Y-%m-%d}"
    state = load_ledger()
    if not dry_run and state["history"] and state["history"][-1]["day"] == today:
        return {"skipped": "already rebalanced today", **state["history"][-1]}
    if state.get("halted") and not dry_run:
        return {"skipped": "halted by the drawdown kill switch; reset it from the UI after reviewing the account"}
    target, _, _ = paper.target_book(now)

    async def go() -> dict:
        book = LiveBook(exchange)
        try:
            equity = await book.ex.equity()
            peak = max(state.get("peak_equity") or equity, equity)
            halt = equity < peak * (1 - book.limits.kill_drawdown)
            result = await book.rebalance({} if halt else target, neutral.ENSEMBLE["band"], dry_run)
            result.update({"peak_equity": peak, "halted": halt})
            return result
        finally:
            await book.aclose()

    result = asyncio.run(go())
    row = {
        "day": today,
        "at": now.isoformat(timespec="seconds"),
        "equity": result["equity"],
        "orders": len(result["orders"]),
        "filled": sum(f["status"] == "filled" for f in result["fills"]),
        "errors": sum(f["status"] == "error" for f in result["fills"]),
        "halted": result["halted"],
        "dry_run": dry_run,
    }
    if not dry_run:
        state["peak_equity"] = result["peak_equity"]
        state["halted"] = result["halted"]
        state["history"].append(row)
        state["last_orders"] = result["fills"]
        save_ledger(state)
    return {**row, "planned": result["orders"]}


def loop(at_minute: int = 15, retry_minutes: int = 15) -> None:
    while True:
        now = datetime.now(UTC)
        due = datetime(now.year, now.month, now.day, 0, at_minute, tzinfo=UTC)
        if now >= due:
            try:
                log.warning("quant LIVE rebalance: %s", {k: v for k, v in step(now).items() if k != "planned"})
                due += timedelta(days=1)
            except Exception:
                log.exception("quant LIVE rebalance failed, retrying in %d minutes", retry_minutes)
                due = datetime.now(UTC) + timedelta(minutes=retry_minutes)
        time.sleep(max(30.0, (due - datetime.now(UTC)).total_seconds()))
