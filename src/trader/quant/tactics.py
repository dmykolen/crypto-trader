from collections.abc import Callable
from dataclasses import dataclass, field
from functools import partial

import numpy as np
import pandas as pd
from numba import njit

from trader.quant import features, mathx, trend
from trader.quant import indicators as ind
from trader.quant.indicators import lag, rmax, rmin
from trader.services import engine

DAY = 86_400_000


@njit(cache=True)
def _hold(event: np.ndarray, bars: int) -> np.ndarray:
    out = np.zeros(len(event), np.int64)
    side, left = 0, 0
    for i in range(len(event)):
        e = event[i]
        if e > 0 or e < 0:
            side, left = (1 if e > 0 else -1), bars
        elif left > 0:
            left -= 1
            side = side if left > 0 else 0
        out[i] = side
    return out


@njit(cache=True)
def _band(x: np.ndarray, lo: float, hi: float, mid: float) -> np.ndarray:
    out = np.zeros(len(x), np.int64)
    side = 0
    for i in range(len(x)):
        v = x[i]
        if v != v:
            side = 0
        elif side == 0:
            side = 1 if v < lo else (-1 if v > hi else 0)
        elif (side > 0 and v >= mid) or (side < 0 and v <= mid):
            side = 0
        out[i] = side
    return out


@dataclass
class Inputs:
    o: np.ndarray
    h: np.ndarray
    low: np.ndarray
    c: np.ndarray
    a: np.ndarray
    funding: np.ndarray
    time: np.ndarray
    f: pd.DataFrame
    edge: np.ndarray

    def col(self, name: str) -> np.ndarray:
        return self.f[name].to_numpy(np.float64) if name in self.f else np.full(len(self.c), np.nan)


def inputs(bars: pd.DataFrame, btc: pd.DataFrame | None = None, edge: np.ndarray | None = None) -> Inputs:
    f = features.frame(bars, btc)
    f["zz_bos"] = f.zz_bos_up - f.zz_bos_down
    f["volume_break"] = f.lvl_break * (f.volume_z24 > 2)
    o, h, low, c = (bars[k].to_numpy(np.float64) for k in ("open", "high", "low", "close"))
    funding = np.nan_to_num(bars["funding"].to_numpy(np.float64)) if "funding" in bars else np.zeros(len(c))
    return Inputs(o, h, low, c, ind.atr(h, low, c, 14), funding, bars.open_time.to_numpy(np.int64), f, np.zeros(len(c)) if edge is None else np.nan_to_num(edge))


def _sign(x: np.ndarray, dead: float = 0.0) -> np.ndarray:
    x = np.nan_to_num(np.asarray(x, np.float64))
    return (x > dead).astype(np.int64) - (x < -dead).astype(np.int64)


def _supertrend(x: Inputs, mult: float) -> np.ndarray:
    return _sign(ind.supertrend(x.h, x.low, x.c, x.a, mult)[0])


def _ichimoku(x: Inputs) -> np.ndarray:
    tk = x.col("ichi_tk")
    return ((x.col("ichi_above_cloud") > 0) & (tk > 0)).astype(np.int64) - ((x.col("ichi_below_cloud") < 0) & (tk < 0)).astype(np.int64)


def _donchian(x: Inputs, n: int) -> np.ndarray:
    levels = (x.c, lag(rmax(x.h, n)), lag(rmin(x.low, n)), lag(rmax(x.h, n // 2)), lag(rmin(x.low, n // 2)))
    return trend._donchian(*(v[:, None] for v in levels))[:, 0].astype(np.int64)


def _votes(x: Inputs) -> np.ndarray:
    return (
        _sign(ind.ema(x.c, 24) - ind.ema(x.c, 96))
        + _supertrend(x, 3.0)
        + _sign(ind.psar(x.h, x.low, 0.02, 0.2)[0])
        + _sign(ind.macd(x.c)[2])
        + _sign(mathx.kalman_trend(np.log(x.c), 96)[1])
        + _ichimoku(x)
    )


def _hurst_switch(x: Inputs) -> np.ndarray:
    hurst = np.nan_to_num(x.col("hurst"), nan=0.5)
    return np.where(hurst > 0.55, _supertrend(x, 3.0), np.where(hurst < 0.45, _band(mathx.zscore(x.c, 96), -2.0, 2.0, 0.0), 0))


def _event(x: Inputs, column: str, hold: int) -> np.ndarray:
    return _hold(np.nan_to_num(x.col(column)), hold)


EVENTS = {
    "squeeze_break": "lvl_break_squeeze",
    "level_break": "lvl_break",
    "volume_break": "volume_break",
    "double_top_bottom": "zz_double_break",
    "head_shoulders": "zz_hs_break",
    "triangle": "zz_triangle_break",
    "structure_break": "zz_bos",
    "divergence": "zz_divergence",
    "flag": "lvl_flag",
    "engulfing": "cdl_engulf",
    "star": "cdl_star",
    "three_soldiers": "cdl_three",
    "hammer": "cdl_hammer",
}

RULES: dict[str, tuple[Callable[..., np.ndarray], tuple[dict, ...]]] = {
    "ema_cross": (lambda x, fast, slow: _sign(ind.ema(x.c, fast) - ind.ema(x.c, slow)), ({"fast": 12, "slow": 26}, {"fast": 24, "slow": 96}, {"fast": 50, "slow": 200})),
    "supertrend": (_supertrend, ({"mult": 2.0}, {"mult": 3.0}, {"mult": 4.0})),
    "psar": (lambda x, step, top: _sign(ind.psar(x.h, x.low, step, top)[0]), ({"step": 0.02, "top": 0.2}, {"step": 0.01, "top": 0.1})),
    "macd": (lambda x, fast, slow, signal: _sign(ind.macd(x.c, fast, slow, signal)[2]), ({"fast": 12, "slow": 26, "signal": 9}, {"fast": 48, "slow": 104, "signal": 36})),
    "donchian": (_donchian, ({"n": 24}, {"n": 72}, {"n": 168})),
    "kalman": (lambda x, span: _sign(mathx.kalman_trend(np.log(x.c), span)[1]), ({"span": 48}, {"span": 192})),
    "ichimoku": (_ichimoku, ({},)),
    "adx_trend": (lambda x, level: np.where(np.nan_to_num(x.col("adx")) > level, _supertrend(x, 3.0), 0), ({"level": 20}, {"level": 30})),
    "trend_vote": (lambda x, k: np.where(np.abs(v := _votes(x)) >= k, np.sign(v), 0), ({"k": 4}, {"k": 6})),
    "rsi_revert": (lambda x, n, lo, hi: _band(ind.rsi(x.c, n), lo, hi, 50.0), ({"n": 14, "lo": 25, "hi": 75}, {"n": 6, "lo": 15, "hi": 85})),
    "bollinger_revert": (lambda x, n, k: _band(ind.bollinger(x.c, n, k)[0], 0.0, 1.0, 0.5), ({"n": 20, "k": 2.0}, {"n": 48, "k": 2.5})),
    "zscore_revert": (lambda x, n, z: _band(mathx.zscore(x.c, n), -z, z, 0.0), ({"n": 96, "z": 2.0}, {"n": 24, "z": 2.5})),
    "heikin_ashi": (lambda x, k: np.where(np.abs(s := np.nan_to_num(x.col("heikin_streak"))) >= k, np.sign(s), 0), ({"k": 3}, {"k": 5})),
    "funding_fade": (lambda x, z: _band(x.col("funding_z"), -z, z, 0.0), ({"z": 2.0},)),
    "residual_revert": (lambda x, z: _band(x.col("resid_24"), -z, z, 0.0), ({"z": 2.0}, {"z": 3.0})),
    "btc_follow": (lambda x, corr: _sign(x.col("btc_ret_24")) * (np.nan_to_num(x.col("btc_corr")) > corr), ({"corr": 0.6},)),
    "ml_edge": (lambda x, theta: _sign(x.edge, theta), ({"theta": 0.05}, {"theta": 0.15})),
    "hurst_switch": (_hurst_switch, ({},)),
} | {name: (partial(_event, column=column), ({"hold": 12}, {"hold": 48})) for name, column in EVENTS.items()}

LABELS = {
    "ema_cross": "Перетин середніх {fast}/{slow} год",
    "supertrend": "SuperTrend {mult} ATR",
    "psar": "Parabolic SAR {step}/{top}",
    "macd": "Гістограма MACD {fast}/{slow}/{signal}",
    "donchian": "Пробій каналу Дончіана {n} год",
    "kalman": "Тренд фільтра Калмана {span} год",
    "ichimoku": "Хмара Ішимоку",
    "adx_trend": "SuperTrend при ADX понад {level}",
    "trend_vote": "{k} з 6 трендових індикаторів",
    "rsi_revert": "Відкат від крайнього RSI {n} год",
    "bollinger_revert": "Відкат від смуг Боллінджера {n} год",
    "zscore_revert": "Повернення до середньої {n} год",
    "heikin_ashi": "{k} свічки Хейкен-Аші поспіль",
    "funding_fade": "Проти перекосу фандінгу",
    "residual_revert": "Відставання від BTC, поріг {z}",
    "btc_follow": "Слідом за BTC",
    "ml_edge": "Прогноз моделі LightGBM, поріг {theta}",
    "hurst_switch": "Тренд або відкат за Херстом",
    "squeeze_break": "Пробій після стиснення, {hold} год",
    "level_break": "Пробій рівня 48 год, {hold} год",
    "volume_break": "Пробій рівня з обсягом, {hold} год",
    "double_top_bottom": "Подвійна вершина / дно, {hold} год",
    "head_shoulders": "Голова й плечі, {hold} год",
    "triangle": "Трикутник, {hold} год",
    "structure_break": "Злам структури, {hold} год",
    "divergence": "Дивергенція RSI, {hold} год",
    "flag": "Прапор, {hold} год",
    "engulfing": "Поглинання, {hold} год",
    "star": "Ранкова / вечірня зірка, {hold} год",
    "three_soldiers": "Три солдати / ворони, {hold} год",
    "hammer": "Молот / падаюча зірка, {hold} год",
}

HOW = {
    "ema_cross": "Лонг, поки середня ціна за {fast} год вища за середню за {slow} год; шорт, поки нижча.",
    "supertrend": "Лонг, поки ціна вища за лінію SuperTrend (вона йде на {mult} ATR нижче ціни), шорт, поки нижча.",
    "psar": "Лонг, поки ціна вища за точки Parabolic SAR, шорт, поки нижча; точки підтягуються за ціною з кроком {step}.",
    "macd": "Лонг, поки гістограма MACD ({fast}/{slow}/{signal} год) вища за нуль, тобто рух угору прискорюється; шорт, поки нижча.",
    "donchian": "Лонг після пробою найвищої ціни за {n} год, шорт після пробою найнижчої; розворот на пробої протилежної межі.",
    "kalman": "Лонг, поки ціна, згладжена фільтром Калмана за {span} год, росте; шорт, поки падає.",
    "ichimoku": "Лонг, коли ціна над хмарою Ішимоку і швидка лінія вища за повільну; шорт навпаки; інакше поза ринком.",
    "adx_trend": "Як SuperTrend 3 ATR, але лише коли тренд сильний (ADX понад {level}); інакше поза ринком.",
    "trend_vote": "Шість трендових індикаторів голосують: лонг, коли щонайменше {k} кажуть «вгору», шорт, коли {k} кажуть «вниз».",
    "rsi_revert": "Лонг, коли RSI за {n} год падає нижче {lo} (ціну перепродали), шорт, коли вище {hi}; вихід, коли RSI повертається до 50.",
    "bollinger_revert": "Лонг, коли ціна падає під нижню смугу Боллінджера ({n} год), шорт, коли виходить над верхню; вихід на середній лінії.",
    "zscore_revert": "Лонг, коли ціна на {z} стандартні відхилення нижча за середню за {n} год, шорт, коли настільки ж вища; вихід на середній.",
    "heikin_ashi": "Лонг після {k} зелених свічок Хейкен-Аші поспіль, шорт після {k} червоних.",
    "funding_fade": "Проти натовпу: шорт, коли лонги платять незвично великий фандінг ({z} стандартні відхилення), лонг, коли платять шорти; вихід, коли фандінг у нормі.",
    "residual_revert": "Лонг, коли монета за 24 год відстала від BTC більше, ніж зазвичай ({z} стандартні відхилення), шорт, коли випередила; вихід, коли розрив закрився.",
    "btc_follow": "Лонг, коли BTC за 24 год виріс, шорт, коли впав; лише поки монета зазвичай ходить разом із BTC (кореляція понад {corr}).",
    "ml_edge": "Лонг, коли модель LightGBM Кванта чекає ріст із перевагою понад {theta}, шорт, коли падіння.",
    "hurst_switch": "Показник Херста визначає ринок: коли ціна йде трендом, торгує як SuperTrend, коли ходить у діапазоні, грає на відкат від крайніх цін.",
    "squeeze_break": "Діапазон останніх 48 год вужчий, ніж зазвичай, і ціна його пробиває: вгору лонг, вниз шорт.",
    "level_break": "Ціна закривається вище максимуму останніх 48 год (лонг) або нижче мінімуму (шорт).",
    "volume_break": "Пробій максимуму чи мінімуму 48 год на обсязі, більшому за звичайний: вгору лонг, вниз шорт.",
    "double_top_bottom": "Подвійне дно з пробоєм угору: лонг; подвійна вершина з пробоєм униз: шорт.",
    "head_shoulders": "Перевернута «голова й плечі» з пробоєм лінії шиї: лонг; звичайна: шорт.",
    "triangle": "Ціна звужується трикутником і виходить з нього: вгору лонг, вниз шорт.",
    "structure_break": "Після серії нижчих максимумів ціна пробиває останній максимум: лонг; дзеркально: шорт.",
    "divergence": "Ціна робить новий мінімум, а RSI ні: лонг; новий максимум без нового максимуму RSI: шорт.",
    "flag": "Після різкого руху (понад 4 ATR за 12 год) ціна 6 год стоїть у вузькому діапазоні: вхід у бік руху.",
    "engulfing": "Свічка повністю перекриває попередню протилежну: зелена (бичаче поглинання) лонг, червона шорт.",
    "star": "Ранкова зірка (падіння, маленька свічка, ріст): лонг; вечірня зірка (ріст, маленька, падіння): шорт.",
    "three_soldiers": "Три зелені свічки поспіль, кожна закривається вище: лонг; три червоні («три ворони»): шорт.",
    "hammer": "Молот (довга нижня тінь після падіння): лонг; падаюча зірка (довга верхня тінь після росту): шорт.",
}

HOLD = " Позицію тримає {hold} год, якщо раніше не прийде протилежний сигнал."


def _num(v: float) -> str:
    return f"{v:g}".replace(".", ",")


def _atr(k: float, atr: float) -> str:
    return f"{_num(k)} ATR (≈ {_num(round(100 * k * atr, 1))} % ціни)" if atr > 0 else f"{_num(k)} ATR"


@dataclass(frozen=True)
class Overlay:
    name: str
    sl: float = 0.0
    tp: float = 0.0
    trail: float = 0.0
    cooldown: int = 0

    def describe(self) -> str:
        parts = [f"стоп {_num(self.sl)} ATR" if self.sl else "", f"тейк {_num(self.tp)} ATR" if self.tp else "", f"трейлінг {_num(self.trail)} ATR" if self.trail else ""]
        parts.append(f"повторний вхід через {self.cooldown} год" if self.cooldown else "")
        return ", ".join(p for p in parts if p) or "вихід лише за сигналом"

    def explain(self, atr: float) -> str:
        parts = [f"стоп-лосс при збитку {_atr(self.sl, atr)}" if self.sl else "", f"тейк-профіт при прибутку {_atr(self.tp, atr)}" if self.tp else ""]
        parts.append(f"трейлінг-стоп на відстані {_atr(self.trail, atr)} від найкращої ціни" if self.trail else "")
        exits = ", ".join(p for p in parts if p)
        after = " чи ".join(n for n, on in (("стопу", self.sl), ("тейку", self.tp), ("трейлінг-стопу", self.trail)) if on)
        again = f" Після {after} входить знову через {self.cooldown} год, якщо сигнал не змінився." if self.cooldown else ""
        return f"Додатково: {exits}.{again}" if exits else "Стопів і тейків немає: виходить лише за сигналом."


OVERLAYS = (
    Overlay("signal"),
    Overlay("sl2", 2.0),
    Overlay("sl2_trail3", 2.0, 0.0, 3.0),
    Overlay("sl2_trail3_reopen", 2.0, 0.0, 3.0, 6),
    Overlay("sl1.5_tp3_reopen", 1.5, 3.0, 0.0, 6),
)


@dataclass(frozen=True)
class Tactic:
    rule: str
    params: tuple[tuple[str, float], ...] = field(default=())
    overlay: Overlay = OVERLAYS[0]

    @property
    def signal(self) -> str:
        return f"{self.rule}({','.join(f'{k}={v:g}' for k, v in self.params)})"

    @property
    def key(self) -> str:
        return f"{self.signal}|{self.overlay.name}"

    @property
    def title(self) -> str:
        return LABELS[self.rule].format(**{k: _num(v) for k, v in self.params})

    def describe(self) -> str:
        return f"{self.title}; {self.overlay.describe()}"

    def explain(self, atr: float = 0.0) -> str:
        p = {k: _num(v) for k, v in self.params}
        return f"{HOW[self.rule].format(**p)}{HOLD.format(**p) if self.rule in EVENTS else ''} {self.overlay.explain(atr)}"


def catalog() -> list[Tactic]:
    return [Tactic(rule, tuple(p.items()), ov) for rule, (_, grid) in RULES.items() for p in grid for ov in OVERLAYS]


def by_key(key: str) -> Tactic:
    return next(t for t in catalog() if t.key == key)


def signals(x: Inputs, tactics: list[Tactic]) -> dict[str, np.ndarray]:
    return {t.signal: np.asarray(RULES[t.rule][0](x, **dict(t.params)), np.int64) for t in {Tactic(t.rule, t.params) for t in tactics}}


def targets(side: np.ndarray, start: int = 0) -> np.ndarray:
    out = np.concatenate(([0], side[:-1])).astype(np.int64)
    out[:start] = 0
    return out


def _risk(x: Inputs, t: Tactic) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    atr_pct = np.nan_to_num(lag(x.a / x.c))
    return t.overlay.sl * atr_pct, t.overlay.tp * atr_pct, t.overlay.trail * atr_pct


def curve(x: Inputs, t: Tactic, side: np.ndarray, leverage: float = 1.0, start: int = 0, costs: engine.Costs | None = None) -> np.ndarray:
    costs = costs or engine.Costs()
    sl, tp, trail = _risk(x, t)
    hold = np.full(len(x.c), 10**9, np.int64)
    equity, _ = engine._simulate(
        x.o, x.h, x.low, x.c, x.funding, targets(side, start), sl, tp, trail, hold, leverage, 1.0, costs.fee, costs.slip, costs.stop_slip, costs.mmr, t.overlay.cooldown
    )
    return equity


def backtest(x: Inputs, t: Tactic, side: np.ndarray, leverage: float = 1.0, start: int = 0, capital: float = 1000.0) -> engine.BacktestResult:
    bars = pd.DataFrame({"open_time": x.time, "open": x.o, "high": x.h, "low": x.low, "close": x.c})
    sl, tp, trail = _risk(x, t)
    return engine.backtest(bars, x.funding, targets(side, start), leverage=leverage, sl=sl, tp=tp, trail=trail, cooldown=t.overlay.cooldown, capital=capital)


def daily(x: Inputs, tactics: list[Tactic], leverage: float = 1.0) -> pd.DataFrame:
    sig = signals(x, tactics)
    day = x.time // DAY * DAY
    last = np.flatnonzero(np.r_[day[1:] != day[:-1], True])
    eq = np.column_stack([curve(x, t, sig[t.signal], leverage)[last] for t in tactics])
    ret = np.vstack([np.full(len(tactics), np.nan), eq[1:] / np.where(eq[:-1] > 0, eq[:-1], np.nan) - 1])
    return pd.DataFrame(ret, index=day[last], columns=[t.key for t in tactics])
