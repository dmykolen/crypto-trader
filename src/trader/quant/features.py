import numpy as np
import pandas as pd

from trader.quant import indicators as ind
from trader.quant import mathx, patterns
from trader.quant.indicators import div, lag

HORIZONS = (1, 3, 6, 12, 24, 48, 96, 168)


def _col(bars: pd.DataFrame, name: str, default: float | np.ndarray) -> np.ndarray:
    if name in bars and bars[name].notna().any():
        return bars[name].to_numpy(np.float64)
    return np.broadcast_to(np.asarray(default, dtype=np.float64), len(bars)).copy()


def btc_context(btc: pd.DataFrame) -> pd.DataFrame:
    h, low, c = (btc[k].to_numpy(np.float64) for k in ("high", "low", "close"))
    r = mathx.log_returns(c)
    a = ind.atr(h, low, c)
    return pd.DataFrame(
        {
            "btc_r": r,
            "btc_ret_6": np.log(div(c, lag(c, 6))),
            "btc_ret_24": np.log(div(c, lag(c, 24))),
            "btc_ret_168": np.log(div(c, lag(c, 168))),
            "btc_vol_24": ind.rstd(r, 24),
            "btc_vol_ratio": div(ind.rstd(r, 24), ind.rstd(r, 168)),
            "btc_trend": div(c - ind.ema(c, 200), a),
            "btc_rsi": ind.rsi(c, 14),
        },
        index=btc.open_time.to_numpy(np.int64),
    )


def frame(bars: pd.DataFrame, btc: pd.DataFrame | None = None) -> pd.DataFrame:
    o, h, low, c = (bars[k].to_numpy(np.float64) for k in ("open", "high", "low", "close"))
    v = _col(bars, "volume", 0.0)
    qv = _col(bars, "quote_volume", v * c)
    tb = _col(bars, "taker_buy_volume", np.nan)
    funding = np.nan_to_num(_col(bars, "funding", 0.0))
    t = bars.open_time.to_numpy(np.int64)
    a = ind.atr(h, low, c, 14)
    ap = div(a, c)
    r = mathx.log_returns(c)
    vol168 = ind.rstd(r, 168)
    f: dict[str, np.ndarray] = {"atr_pct": ap}
    for n in HORIZONS:
        f[f"mom_{n}"] = div(np.log(div(c, lag(c, n))), vol168 * np.sqrt(n))
    f["ret_24"], f["ret_168"] = np.log(div(c, lag(c, 24))), np.log(div(c, lag(c, 168)))
    for span in (12, 26, 50, 100, 200):
        f[f"ema_dist_{span}"] = div(c - ind.ema(c, span), a)
    e50, e200 = ind.ema(c, 50), ind.ema(c, 200)
    f["ema50_slope"], f["ema200_slope"] = div(e50 - lag(e50, 12), a), div(e200 - lag(e200, 24), a)
    f["ema_cross"] = div(ind.ema(c, 12) - ind.ema(c, 26), a)
    line, _signal, hist = ind.macd(c)
    f["macd"], f["macd_hist"], f["macd_hist_chg"] = div(line, a), div(hist, a), div(hist - lag(hist, 3), a)
    adx, pdi, mdi = ind.adx(h, low, c)
    f["adx"], f["di_spread"] = adx, pdi - mdi
    up, dn = ind.aroon(h, low)
    f["aroon"] = up - dn
    st_dir, st_band = ind.supertrend(h, low, c, a, 3.0)
    f["supertrend"], f["supertrend_dist"] = st_dir, div(c - st_band, a)
    ps_dir, ps = ind.psar(h, low, 0.02, 0.2)
    f["psar"], f["psar_dist"] = ps_dir, div(c - ps, a)
    f.update(ind.ichimoku(h, low, c, a))
    level, slope = mathx.kalman_trend(np.log(c), 96)
    f["kalman_slope"], f["kalman_gap"] = slope, div(np.log(c) - level, ap)
    for n in (24, 96):
        s, r2 = mathx.trend_fit(np.log(c), n)
        f[f"trend_slope_{n}"], f[f"trend_r2_{n}"] = div(s * n, ap), r2
    f["heikin_streak"] = ind.heikin_ashi_streak(o, h, low, c)
    for n in (6, 14, 28):
        f[f"rsi_{n}"] = ind.rsi(c, n)
    k, d = ind.stochastic(h, low, c)
    f["stoch_k"], f["stoch_kd"] = k, k - d
    f["williams"], f["cci"], f["mfi"], f["tsi"] = ind.williams_r(h, low, c), ind.cci(h, low, c), ind.mfi(h, low, c, v), ind.tsi(c)
    pctb, bw = ind.bollinger(c)
    f["bb_pctb"], f["bb_width"] = pctb, bw
    f["bb_squeeze"] = div(bw * c, 3.0 * a)
    f["keltner"] = ind.keltner_position(h, low, c, a)
    f["donchian_20"], f["donchian_55"] = ind.donchian_position(h, low, c, 20), ind.donchian_position(h, low, c, 55)
    rv24 = ind.rstd(r, 24)
    f["rv_24"], f["rv_ratio"] = rv24, div(rv24, vol168)
    f["parkinson"], f["garman_klass"] = div(mathx.parkinson(h, low, 24), rv24), div(mathx.garman_klass(o, h, low, c, 24), rv24)
    f["vol_of_vol"] = div(ind.rstd(rv24, 96), ind.sma(rv24, 96))
    lv = np.log1p(v)
    f["volume_z24"], f["volume_z168"] = mathx.zscore(lv, 24), mathx.zscore(lv, 168)
    qv24 = ind.rsum(qv, 24)
    f["liquidity"] = np.log1p(qv24)
    f["obv_slope"] = div(ind.obv(c, v) - lag(ind.obv(c, v), 24), ind.rsum(v, 24))
    f["cmf"] = ind.cmf(h, low, c, v)
    taker = div(tb, v)
    f["taker_ratio_24"], f["taker_z"] = ind.sma(taker, 24), mathx.zscore(taker, 168)
    f["vwap_24"], f["vwap_168"] = ind.vwap_distance(h, low, c, v, a, 24), ind.vwap_distance(h, low, c, v, a, 168)
    f["amihud"] = np.log1p(1e9 * ind.sma(div(np.abs(r), qv), 24))
    f["funding_24"], f["funding_72"] = ind.rsum(funding, 24), ind.rsum(funding, 72)
    f["funding_z"] = mathx.zscore(ind.rsum(funding, 24), 720)
    f["hurst"] = mathx.hurst(c, 192)
    f["ac1_24"], f["ac1_96"] = mathx.autocorr(r, 24), mathx.autocorr(r, 96)
    f["var_ratio"] = mathx.variance_ratio(r, 96)
    f["skew_96"], f["kurt_96"] = mathx.rolling_skew(r, 96), mathx.rolling_kurt(r, 96)
    f["perm_entropy"] = mathx.permutation_entropy(c, 4, 96)
    f["ffd"] = mathx.zscore(mathx.frac_diff(c, 0.4), 500)
    f["ou_half_life"] = mathx.ou_half_life(c, 168)
    f["z_24"], f["z_96"] = mathx.zscore(c, 24), mathx.zscore(c, 96)
    f["drawdown_168"], f["runup_168"] = div(c - ind.rmax(h, 168), a), div(c - ind.rmin(low, 168), a)
    f.update(patterns.candles(o, h, low, c, a))
    f.update(patterns.chart(h, low, c, a, f["rsi_14"]))
    f.update(patterns.levels(h, low, c, a))
    hour = (t // 3_600_000) % 24
    f["hour_sin"], f["hour_cos"] = np.sin(2 * np.pi * hour / 24), np.cos(2 * np.pi * hour / 24)
    dow = (t // 86_400_000 + 3) % 7
    f["dow_sin"], f["dow_cos"] = np.sin(2 * np.pi * dow / 7), np.cos(2 * np.pi * dow / 7)
    f["to_funding"] = (8 - hour % 8) % 8
    out = pd.DataFrame(f, index=t)
    if btc is not None:
        ctx = btc_context(btc).reindex(t)
        beta, resid = mathx.beta_residual(r, ctx.btc_r.to_numpy(), 168)
        out["btc_beta"], out["resid_24"] = beta, div(ind.rsum(resid, 24), ind.rstd(resid, 168) * np.sqrt(24))
        out["btc_corr"] = pd.Series(r).rolling(168, min_periods=168).corr(pd.Series(ctx.btc_r.to_numpy())).to_numpy()
        out = out.join(ctx.drop(columns=["btc_r"]))
    out = out.replace([np.inf, -np.inf], np.nan)
    return out.astype(np.float32)
