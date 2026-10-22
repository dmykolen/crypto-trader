# Per-token strategy selection — out-of-sample (walk-forward)

Every 7 days the selector picks — among trend / breakout / mean-reversion / ML-forecast strategies × parameters × leverage 2-10x × ATR stop/take-profit — the spec with the best lower confidence bound of daily log-growth over the previous 60 days (flat when no bound is positive); that spec trades the next fold. The folds are replayed as one $1000 account (15m bars, fees, slippage, funding, isolated liquidation), so the equity is entirely out-of-sample.

| symbol | oos_return_pct | max_drawdown_pct | sharpe_daily | best_day_pnl | worst_day_pnl | days_pnl_ge_100 | days | live_choice |
|---|---|---|---|---|---|---|---|---|
| BTCUSDT | 48.3 | -64.68 | 0.88 | 355.4 | -533.34 | 18 | 365 | flat — no spec with a positive edge |
| ETHUSDT | -49.18 | -66.09 | -0.82 | 96.09 | -120.08 | 0 | 365 | flat — no spec with a positive edge |
| SOLUSDT | -56.3 | -66.9 | -0.3 | 193.82 | -213.85 | 6 | 365 | flat — no spec with a positive edge |
| DOGEUSDT | -77.75 | -84.2 | -1.94 | 153.11 | -277.93 | 4 | 365 | flat — no spec with a positive edge |
| XRPUSDT | -93.44 | -94.4 | -2.36 | 122.84 | -393.2 | 2 | 365 | flat — no spec with a positive edge |

## BTCUSDT

Regime now: `{"trend_strength_adx": 10.2, "efficiency_ratio_48": 0.101, "hurst": 0.559, "vol_ratio_short_long": 0.69, "realized_vol_per_bar_pct": 0.139, "rsi_14": 42.8, "ema_gap_48_192_atr": 0.6, "drawdown_from_high_pct": -1.29}`

| fold | spec chosen on the previous window | fold return |
|---|---|---|
| 2025-10-20 → 2025-10-27 | flat (no positive edge in training window) | 0.0% |
| 2025-10-27 → 2025-11-03 | flat (no positive edge in training window) | 0.0% |
| 2025-11-03 → 2025-11-10 | flat (no positive edge in training window) | 0.0% |
| 2025-11-10 → 2025-11-17 | donchian(entry=192, exit_=96) 2x SL 0ATR TP 0ATR | 9.61% |
| 2025-11-17 → 2025-11-24 | donchian(entry=192, exit_=96) 5x SL 0ATR TP 0ATR | 26.41% |
| 2025-11-24 → 2025-12-01 | donchian(entry=192, exit_=96) 5x SL 0ATR TP 8ATR | 12.81% |
| 2025-12-01 → 2025-12-08 | donchian(entry=192, exit_=96) 5x SL 0ATR TP 8ATR | 19.92% |
| 2025-12-08 → 2025-12-15 | donchian(entry=192, exit_=96) 5x SL 0ATR TP 8ATR | 24.77% |
| 2025-12-15 → 2025-12-22 | donchian(entry=192, exit_=96) 5x SL 0ATR TP 8ATR | -36.95% |
| 2025-12-22 → 2025-12-29 | donchian(entry=192, exit_=96) 5x SL 0ATR TP 8ATR | -34.14% |
| 2025-12-29 → 2026-01-05 | flat (no positive edge in training window) | 0.0% |
| 2026-01-05 → 2026-01-12 | flat (no positive edge in training window) | 0.0% |
| 2026-01-12 → 2026-01-19 | flat (no positive edge in training window) | 0.0% |
| 2026-01-19 → 2026-01-26 | flat (no positive edge in training window) | 0.0% |
| 2026-01-26 → 2026-02-02 | flat (no positive edge in training window) | 0.0% |
| 2026-02-02 → 2026-02-09 | mean_reversion(er_max=0.3, window=96, z_in=2.5) 2x SL 2ATR TP 0ATR | -8.08% |
| 2026-02-09 → 2026-02-16 | flat (no positive edge in training window) | 0.0% |
| 2026-02-16 → 2026-02-23 | flat (no positive edge in training window) | 0.0% |
| 2026-02-23 → 2026-03-02 | donchian(entry=192, exit_=96) 5x SL 0ATR TP 8ATR | 20.07% |
| 2026-03-02 → 2026-03-09 | donchian(entry=192, exit_=96) 5x SL 0ATR TP 8ATR | 42.99% |
| 2026-03-09 → 2026-03-16 | donchian(entry=192, exit_=96) 5x SL 0ATR TP 8ATR | 13.66% |
| 2026-03-16 → 2026-03-23 | donchian(entry=192, exit_=96) 5x SL 0ATR TP 8ATR | 28.75% |
| 2026-03-23 → 2026-03-30 | donchian(entry=192, exit_=96) 5x SL 0ATR TP 8ATR | -21.11% |
| 2026-03-30 → 2026-04-06 | donchian(entry=192, exit_=96) 5x SL 0ATR TP 8ATR | -28.43% |
| 2026-04-06 → 2026-04-13 | donchian(entry=192, exit_=96) 5x SL 0ATR TP 4ATR | 13.94% |
| 2026-04-13 → 2026-04-20 | donchian(entry=192, exit_=96) 5x SL 0ATR TP 4ATR | 19.11% |
| 2026-04-20 → 2026-04-27 | donchian(entry=192, exit_=96) 5x SL 0ATR TP 4ATR | -11.88% |
| 2026-04-27 → 2026-05-04 | flat (no positive edge in training window) | 0.0% |
| 2026-05-04 → 2026-05-11 | flat (no positive edge in training window) | 0.0% |
| 2026-05-11 → 2026-05-18 | flat (no positive edge in training window) | 0.0% |
| 2026-05-18 → 2026-05-25 | flat (no positive edge in training window) | 0.0% |
| 2026-05-25 → 2026-06-01 | flat (no positive edge in training window) | 0.0% |
| 2026-06-01 → 2026-06-08 | flat (no positive edge in training window) | 0.0% |
| 2026-06-08 → 2026-06-15 | flat (no positive edge in training window) | 0.0% |
| 2026-06-15 → 2026-06-22 | flat (no positive edge in training window) | 0.0% |
| 2026-06-22 → 2026-06-29 | flat (no positive edge in training window) | 0.0% |
| 2026-06-29 → 2026-07-06 | donchian(entry=192, exit_=96) 2x SL 2ATR TP 0ATR | -3.2% |
| 2026-07-06 → 2026-07-13 | flat (no positive edge in training window) | 0.0% |
| 2026-07-13 → 2026-07-20 | flat (no positive edge in training window) | 0.0% |
| 2026-07-20 → 2026-07-27 | flat (no positive edge in training window) | 0.0% |
| 2026-07-27 → 2026-08-03 | flat (no positive edge in training window) | 0.0% |
| 2026-08-03 → 2026-08-10 | mean_reversion(er_max=0.3, window=48, z_in=2.5) 2x SL 0ATR TP 8ATR | 0.02% |
| 2026-08-10 → 2026-08-17 | mean_reversion(er_max=0.3, window=48, z_in=2.5) 2x SL 0ATR TP 8ATR | 1.14% |
| 2026-08-17 → 2026-08-24 | flat (no positive edge in training window) | 0.0% |
| 2026-08-24 → 2026-08-31 | flat (no positive edge in training window) | 0.0% |
| 2026-08-31 → 2026-09-07 | flat (no positive edge in training window) | 0.0% |
| 2026-09-07 → 2026-09-14 | flat (no positive edge in training window) | 0.0% |
| 2026-09-14 → 2026-09-21 | flat (no positive edge in training window) | 0.0% |
| 2026-09-21 → 2026-09-28 | flat (no positive edge in training window) | 0.0% |
| 2026-09-28 → 2026-10-05 | flat (no positive edge in training window) | 0.0% |
| 2026-10-05 → 2026-10-12 | flat (no positive edge in training window) | 0.0% |
| 2026-10-12 → 2026-10-19 | flat (no positive edge in training window) | 0.0% |
| 2026-10-19 → 2026-10-19 | flat (no positive edge in training window) | 0.0% |

## ETHUSDT

Regime now: `{"trend_strength_adx": 13.9, "efficiency_ratio_48": 0.065, "hurst": 0.533, "vol_ratio_short_long": 0.65, "realized_vol_per_bar_pct": 0.221, "rsi_14": 52.7, "ema_gap_48_192_atr": -0.45, "drawdown_from_high_pct": -1.5}`

| fold | spec chosen on the previous window | fold return |
|---|---|---|
| 2025-10-20 → 2025-10-27 | donchian(entry=192, exit_=96) 2x SL 4ATR TP 4ATR | -12.89% |
| 2025-10-27 → 2025-11-03 | flat (no positive edge in training window) | 0.0% |
| 2025-11-03 → 2025-11-10 | flat (no positive edge in training window) | 0.0% |
| 2025-11-10 → 2025-11-17 | flat (no positive edge in training window) | 0.0% |
| 2025-11-17 → 2025-11-24 | flat (no positive edge in training window) | 0.0% |
| 2025-11-24 → 2025-12-01 | flat (no positive edge in training window) | 0.0% |
| 2025-12-01 → 2025-12-08 | flat (no positive edge in training window) | 0.0% |
| 2025-12-08 → 2025-12-15 | flat (no positive edge in training window) | 0.0% |
| 2025-12-15 → 2025-12-22 | donchian(entry=192, exit_=96) 2x SL 0ATR TP 4ATR | -18.69% |
| 2025-12-22 → 2025-12-29 | flat (no positive edge in training window) | 0.0% |
| 2025-12-29 → 2026-01-05 | flat (no positive edge in training window) | 0.0% |
| 2026-01-05 → 2026-01-12 | mean_reversion(er_max=0.3, window=96, z_in=2.5) 2x SL 0ATR TP 0ATR | 3.97% |
| 2026-01-12 → 2026-01-19 | mean_reversion(er_max=0.3, window=96, z_in=2.5) 2x SL 0ATR TP 0ATR | -1.38% |
| 2026-01-19 → 2026-01-26 | flat (no positive edge in training window) | 0.0% |
| 2026-01-26 → 2026-02-02 | flat (no positive edge in training window) | 0.0% |
| 2026-02-02 → 2026-02-09 | flat (no positive edge in training window) | 0.0% |
| 2026-02-09 → 2026-02-16 | trend_ema(adx_min=15, fast=48, slow=192) 2x SL 0ATR TP 8ATR | -12.93% |
| 2026-02-16 → 2026-02-23 | donchian(entry=192, exit_=96) 2x SL 2ATR TP 0ATR | -10.76% |
| 2026-02-23 → 2026-03-02 | mean_reversion(er_max=0.3, window=96, z_in=2) 2x SL 4ATR TP 4ATR | -11.4% |
| 2026-03-02 → 2026-03-09 | trend_ema(adx_min=15, fast=48, slow=192) 2x SL 4ATR TP 8ATR | -16.96% |
| 2026-03-09 → 2026-03-16 | donchian(entry=192, exit_=96) 2x SL 2ATR TP 0ATR | -4.82% |
| 2026-03-16 → 2026-03-23 | donchian(entry=192, exit_=96) 5x SL 0ATR TP 4ATR | 10.37% |
| 2026-03-23 → 2026-03-30 | donchian(entry=192, exit_=96) 5x SL 0ATR TP 4ATR | 3.35% |
| 2026-03-30 → 2026-04-06 | donchian(entry=192, exit_=96) 2x SL 4ATR TP 0ATR | -3.82% |
| 2026-04-06 → 2026-04-13 | flat (no positive edge in training window) | 0.0% |
| 2026-04-13 → 2026-04-20 | donchian(entry=192, exit_=96) 5x SL 2ATR TP 4ATR | 18.8% |
| 2026-04-20 → 2026-04-27 | donchian(entry=192, exit_=96) 10x SL 2ATR TP 4ATR | 11.87% |
| 2026-04-27 → 2026-05-04 | donchian(entry=192, exit_=96) 5x SL 0ATR TP 4ATR | 1.8% |
| 2026-05-04 → 2026-05-11 | trend_ema(adx_min=25, fast=48, slow=192) 5x SL 4ATR TP 8ATR | 0.18% |
| 2026-05-11 → 2026-05-18 | donchian(entry=192, exit_=96) 5x SL 2ATR TP 4ATR | -3.28% |
| 2026-05-18 → 2026-05-25 | flat (no positive edge in training window) | 0.0% |
| 2026-05-25 → 2026-06-01 | flat (no positive edge in training window) | 0.0% |
| 2026-06-01 → 2026-06-08 | trend_ema(adx_min=25, fast=24, slow=96) 2x SL 4ATR TP 8ATR | 25.58% |
| 2026-06-08 → 2026-06-15 | trend_ema(adx_min=25, fast=24, slow=96) 5x SL 4ATR TP 8ATR | -28.78% |
| 2026-06-15 → 2026-06-22 | flat (no positive edge in training window) | 0.0% |
| 2026-06-22 → 2026-06-29 | flat (no positive edge in training window) | 0.0% |
| 2026-06-29 → 2026-07-06 | flat (no positive edge in training window) | 0.0% |
| 2026-07-06 → 2026-07-13 | flat (no positive edge in training window) | 0.0% |
| 2026-07-13 → 2026-07-20 | flat (no positive edge in training window) | 0.0% |
| 2026-07-20 → 2026-07-27 | flat (no positive edge in training window) | 0.0% |
| 2026-07-27 → 2026-08-03 | flat (no positive edge in training window) | 0.0% |
| 2026-08-03 → 2026-08-10 | flat (no positive edge in training window) | 0.0% |
| 2026-08-10 → 2026-08-17 | flat (no positive edge in training window) | 0.0% |
| 2026-08-17 → 2026-08-24 | flat (no positive edge in training window) | 0.0% |
| 2026-08-24 → 2026-08-31 | flat (no positive edge in training window) | 0.0% |
| 2026-08-31 → 2026-09-07 | flat (no positive edge in training window) | 0.0% |
| 2026-09-07 → 2026-09-14 | flat (no positive edge in training window) | 0.0% |
| 2026-09-14 → 2026-09-21 | flat (no positive edge in training window) | 0.0% |
| 2026-09-21 → 2026-09-28 | flat (no positive edge in training window) | 0.0% |
| 2026-09-28 → 2026-10-05 | flat (no positive edge in training window) | 0.0% |
| 2026-10-05 → 2026-10-12 | flat (no positive edge in training window) | 0.0% |
| 2026-10-12 → 2026-10-19 | flat (no positive edge in training window) | 0.0% |
| 2026-10-19 → 2026-10-19 | flat (no positive edge in training window) | 0.0% |

## SOLUSDT

Regime now: `{"trend_strength_adx": 20.8, "efficiency_ratio_48": 0.043, "hurst": 0.507, "vol_ratio_short_long": 0.83, "realized_vol_per_bar_pct": 0.267, "rsi_14": 56.7, "ema_gap_48_192_atr": 1.01, "drawdown_from_high_pct": -0.8}`

| fold | spec chosen on the previous window | fold return |
|---|---|---|
| 2025-10-20 → 2025-10-27 | donchian(entry=192, exit_=96) 2x SL 0ATR TP 0ATR | -17.57% |
| 2025-10-27 → 2025-11-03 | flat (no positive edge in training window) | 0.0% |
| 2025-11-03 → 2025-11-10 | flat (no positive edge in training window) | 0.0% |
| 2025-11-10 → 2025-11-17 | flat (no positive edge in training window) | 0.0% |
| 2025-11-17 → 2025-11-24 | donchian(entry=48, exit_=24) 2x SL 2ATR TP 4ATR | 1.18% |
| 2025-11-24 → 2025-12-01 | flat (no positive edge in training window) | 0.0% |
| 2025-12-01 → 2025-12-08 | flat (no positive edge in training window) | 0.0% |
| 2025-12-08 → 2025-12-15 | flat (no positive edge in training window) | 0.0% |
| 2025-12-15 → 2025-12-22 | flat (no positive edge in training window) | 0.0% |
| 2025-12-22 → 2025-12-29 | mean_reversion(er_max=0.3, window=96, z_in=2) 2x SL 0ATR TP 8ATR | 26.31% |
| 2025-12-29 → 2026-01-05 | mean_reversion(er_max=0.3, window=96, z_in=2.5) 5x SL 4ATR TP 0ATR | -2.26% |
| 2026-01-05 → 2026-01-12 | mean_reversion(er_max=0.3, window=96, z_in=2.5) 5x SL 4ATR TP 0ATR | -12.21% |
| 2026-01-12 → 2026-01-19 | mean_reversion(er_max=0.3, window=96, z_in=2) 2x SL 0ATR TP 8ATR | 8.76% |
| 2026-01-19 → 2026-01-26 | mean_reversion(er_max=0.3, window=96, z_in=2) 2x SL 0ATR TP 8ATR | -7.08% |
| 2026-01-26 → 2026-02-02 | mean_reversion(er_max=0.3, window=96, z_in=2.5) 5x SL 4ATR TP 0ATR | -12.74% |
| 2026-02-02 → 2026-02-09 | mean_reversion(er_max=0.3, window=96, z_in=2) 5x SL 4ATR TP 8ATR | -25.27% |
| 2026-02-09 → 2026-02-16 | mean_reversion(er_max=0.3, window=96, z_in=2) 2x SL 4ATR TP 8ATR | -0.89% |
| 2026-02-16 → 2026-02-23 | donchian(entry=192, exit_=96) 2x SL 4ATR TP 8ATR | -8.19% |
| 2026-02-23 → 2026-03-02 | donchian(entry=192, exit_=96) 5x SL 0ATR TP 8ATR | 89.74% |
| 2026-03-02 → 2026-03-09 | donchian(entry=192, exit_=96) 5x SL 0ATR TP 8ATR | -33.45% |
| 2026-03-09 → 2026-03-16 | donchian(entry=192, exit_=96) 5x SL 0ATR TP 8ATR | 0.75% |
| 2026-03-16 → 2026-03-23 | donchian(entry=192, exit_=96) 5x SL 0ATR TP 8ATR | 23.47% |
| 2026-03-23 → 2026-03-30 | donchian(entry=192, exit_=96) 5x SL 0ATR TP 8ATR | -0.9% |
| 2026-03-30 → 2026-04-06 | donchian(entry=192, exit_=96) 5x SL 0ATR TP 8ATR | -47.64% |
| 2026-04-06 → 2026-04-13 | donchian(entry=192, exit_=96) 2x SL 2ATR TP 8ATR | -7.99% |
| 2026-04-13 → 2026-04-20 | flat (no positive edge in training window) | 0.0% |
| 2026-04-20 → 2026-04-27 | flat (no positive edge in training window) | 0.0% |
| 2026-04-27 → 2026-05-04 | flat (no positive edge in training window) | 0.0% |
| 2026-05-04 → 2026-05-11 | donchian(entry=192, exit_=96) 5x SL 2ATR TP 4ATR | -5.52% |
| 2026-05-11 → 2026-05-18 | flat (no positive edge in training window) | 0.0% |
| 2026-05-18 → 2026-05-25 | flat (no positive edge in training window) | 0.0% |
| 2026-05-25 → 2026-06-01 | flat (no positive edge in training window) | 0.0% |
| 2026-06-01 → 2026-06-08 | flat (no positive edge in training window) | 0.0% |
| 2026-06-08 → 2026-06-15 | flat (no positive edge in training window) | 0.0% |
| 2026-06-15 → 2026-06-22 | donchian(entry=192, exit_=96) 2x SL 4ATR TP 4ATR | 1.71% |
| 2026-06-22 → 2026-06-29 | donchian(entry=192, exit_=96) 5x SL 0ATR TP 4ATR | 25.16% |
| 2026-06-29 → 2026-07-06 | donchian(entry=192, exit_=96) 5x SL 0ATR TP 4ATR | 16.07% |
| 2026-07-06 → 2026-07-13 | donchian(entry=192, exit_=96) 5x SL 0ATR TP 4ATR | -22.46% |
| 2026-07-13 → 2026-07-20 | flat (no positive edge in training window) | 0.0% |
| 2026-07-20 → 2026-07-27 | flat (no positive edge in training window) | 0.0% |
| 2026-07-27 → 2026-08-03 | donchian(entry=96, exit_=48) 5x SL 4ATR TP 4ATR | 2.33% |
| 2026-08-03 → 2026-08-10 | donchian(entry=96, exit_=48) 5x SL 4ATR TP 4ATR | -5.7% |
| 2026-08-10 → 2026-08-17 | donchian(entry=192, exit_=96) 2x SL 0ATR TP 4ATR | -5.44% |
| 2026-08-17 → 2026-08-24 | flat (no positive edge in training window) | 0.0% |
| 2026-08-24 → 2026-08-31 | flat (no positive edge in training window) | 0.0% |
| 2026-08-31 → 2026-09-07 | donchian(entry=96, exit_=48) 2x SL 0ATR TP 4ATR | 1.15% |
| 2026-09-07 → 2026-09-14 | donchian(entry=96, exit_=48) 2x SL 0ATR TP 4ATR | 6.66% |
| 2026-09-14 → 2026-09-21 | donchian(entry=96, exit_=48) 5x SL 0ATR TP 4ATR | 19.22% |
| 2026-09-21 → 2026-09-28 | donchian(entry=96, exit_=48) 5x SL 0ATR TP 4ATR | -9.78% |
| 2026-09-28 → 2026-10-05 | donchian(entry=96, exit_=48) 2x SL 0ATR TP 4ATR | -6.21% |
| 2026-10-05 → 2026-10-12 | flat (no positive edge in training window) | 0.0% |
| 2026-10-12 → 2026-10-19 | flat (no positive edge in training window) | 0.0% |
| 2026-10-19 → 2026-10-19 | flat (no positive edge in training window) | 0.0% |

## DOGEUSDT

Regime now: `{"trend_strength_adx": 13.7, "efficiency_ratio_48": 0.096, "hurst": 0.45, "vol_ratio_short_long": 0.63, "realized_vol_per_bar_pct": 0.241, "rsi_14": 58.0, "ema_gap_48_192_atr": 0.32, "drawdown_from_high_pct": -0.37}`

| fold | spec chosen on the previous window | fold return |
|---|---|---|
| 2025-10-20 → 2025-10-27 | flat (no positive edge in training window) | 0.0% |
| 2025-10-27 → 2025-11-03 | flat (no positive edge in training window) | 0.0% |
| 2025-11-03 → 2025-11-10 | donchian(entry=48, exit_=24) 2x SL 0ATR TP 0ATR | -3.29% |
| 2025-11-10 → 2025-11-17 | donchian(entry=48, exit_=24) 2x SL 0ATR TP 8ATR | -0.86% |
| 2025-11-17 → 2025-11-24 | donchian(entry=48, exit_=24) 2x SL 0ATR TP 8ATR | 33.93% |
| 2025-11-24 → 2025-12-01 | donchian(entry=48, exit_=24) 2x SL 0ATR TP 8ATR | -19.43% |
| 2025-12-01 → 2025-12-08 | donchian(entry=48, exit_=24) 2x SL 0ATR TP 8ATR | 10.99% |
| 2025-12-08 → 2025-12-15 | donchian(entry=48, exit_=24) 2x SL 0ATR TP 8ATR | 0.95% |
| 2025-12-15 → 2025-12-22 | flat (no positive edge in training window) | 0.0% |
| 2025-12-22 → 2025-12-29 | flat (no positive edge in training window) | 0.0% |
| 2025-12-29 → 2026-01-05 | flat (no positive edge in training window) | 0.0% |
| 2026-01-05 → 2026-01-12 | flat (no positive edge in training window) | 0.0% |
| 2026-01-12 → 2026-01-19 | mean_reversion(er_max=0.3, window=96, z_in=2) 2x SL 4ATR TP 4ATR | -2.55% |
| 2026-01-19 → 2026-01-26 | trend_ema(adx_min=15, fast=48, slow=192) 2x SL 0ATR TP 4ATR | 7.0% |
| 2026-01-26 → 2026-02-02 | mean_reversion(er_max=0.3, window=96, z_in=2) 2x SL 2ATR TP 0ATR | 6.15% |
| 2026-02-02 → 2026-02-09 | mean_reversion(er_max=0.3, window=96, z_in=2) 5x SL 2ATR TP 0ATR | -29.84% |
| 2026-02-09 → 2026-02-16 | mean_reversion(er_max=0.3, window=48, z_in=2.5) 5x SL 4ATR TP 0ATR | -55.9% |
| 2026-02-16 → 2026-02-23 | donchian(entry=192, exit_=96) 2x SL 4ATR TP 8ATR | -11.73% |
| 2026-02-23 → 2026-03-02 | trend_ema(adx_min=25, fast=24, slow=96) 2x SL 0ATR TP 0ATR | -4.89% |
| 2026-03-02 → 2026-03-09 | donchian(entry=192, exit_=96) 2x SL 2ATR TP 8ATR | -9.92% |
| 2026-03-09 → 2026-03-16 | mean_reversion(er_max=0.3, window=96, z_in=2) 2x SL 4ATR TP 8ATR | -7.78% |
| 2026-03-16 → 2026-03-23 | flat (no positive edge in training window) | 0.0% |
| 2026-03-23 → 2026-03-30 | flat (no positive edge in training window) | 0.0% |
| 2026-03-30 → 2026-04-06 | flat (no positive edge in training window) | 0.0% |
| 2026-04-06 → 2026-04-13 | flat (no positive edge in training window) | 0.0% |
| 2026-04-13 → 2026-04-20 | flat (no positive edge in training window) | 0.0% |
| 2026-04-20 → 2026-04-27 | flat (no positive edge in training window) | 0.0% |
| 2026-04-27 → 2026-05-04 | donchian(entry=192, exit_=96) 2x SL 2ATR TP 4ATR | 0.93% |
| 2026-05-04 → 2026-05-11 | flat (no positive edge in training window) | 0.0% |
| 2026-05-11 → 2026-05-18 | donchian(entry=192, exit_=96) 5x SL 2ATR TP 4ATR | -15.24% |
| 2026-05-18 → 2026-05-25 | flat (no positive edge in training window) | 0.0% |
| 2026-05-25 → 2026-06-01 | flat (no positive edge in training window) | 0.0% |
| 2026-06-01 → 2026-06-08 | flat (no positive edge in training window) | 0.0% |
| 2026-06-08 → 2026-06-15 | flat (no positive edge in training window) | 0.0% |
| 2026-06-15 → 2026-06-22 | flat (no positive edge in training window) | 0.0% |
| 2026-06-22 → 2026-06-29 | trend_ema(adx_min=15, fast=24, slow=96) 2x SL 0ATR TP 4ATR | -1.41% |
| 2026-06-29 → 2026-07-06 | trend_ema(adx_min=15, fast=24, slow=96) 2x SL 0ATR TP 4ATR | -1.92% |
| 2026-07-06 → 2026-07-13 | flat (no positive edge in training window) | 0.0% |
| 2026-07-13 → 2026-07-20 | flat (no positive edge in training window) | 0.0% |
| 2026-07-20 → 2026-07-27 | flat (no positive edge in training window) | 0.0% |
| 2026-07-27 → 2026-08-03 | trend_ema(adx_min=15, fast=24, slow=96) 2x SL 0ATR TP 4ATR | -2.85% |
| 2026-08-03 → 2026-08-10 | flat (no positive edge in training window) | 0.0% |
| 2026-08-10 → 2026-08-17 | flat (no positive edge in training window) | 0.0% |
| 2026-08-17 → 2026-08-24 | flat (no positive edge in training window) | 0.0% |
| 2026-08-24 → 2026-08-31 | flat (no positive edge in training window) | 0.0% |
| 2026-08-31 → 2026-09-07 | flat (no positive edge in training window) | 0.0% |
| 2026-09-07 → 2026-09-14 | flat (no positive edge in training window) | 0.0% |
| 2026-09-14 → 2026-09-21 | flat (no positive edge in training window) | 0.0% |
| 2026-09-21 → 2026-09-28 | flat (no positive edge in training window) | 0.0% |
| 2026-09-28 → 2026-10-05 | flat (no positive edge in training window) | 0.0% |
| 2026-10-05 → 2026-10-12 | flat (no positive edge in training window) | 0.0% |
| 2026-10-12 → 2026-10-19 | flat (no positive edge in training window) | 0.0% |
| 2026-10-19 → 2026-10-19 | flat (no positive edge in training window) | 0.0% |

## XRPUSDT

Regime now: `{"trend_strength_adx": 7.6, "efficiency_ratio_48": 0.007, "hurst": 0.512, "vol_ratio_short_long": 0.64, "realized_vol_per_bar_pct": 0.222, "rsi_14": 49.1, "ema_gap_48_192_atr": 0.56, "drawdown_from_high_pct": -1.03}`

| fold | spec chosen on the previous window | fold return |
|---|---|---|
| 2025-10-20 → 2025-10-27 | trend_ema(adx_min=15, fast=24, slow=96) 5x SL 0ATR TP 4ATR | -22.42% |
| 2025-10-27 → 2025-11-03 | trend_ema(adx_min=15, fast=24, slow=96) 5x SL 0ATR TP 4ATR | -36.67% |
| 2025-11-03 → 2025-11-10 | donchian(entry=192, exit_=96) 5x SL 0ATR TP 4ATR | -44.56% |
| 2025-11-10 → 2025-11-17 | donchian(entry=96, exit_=48) 5x SL 0ATR TP 4ATR | -12.7% |
| 2025-11-17 → 2025-11-24 | trend_ema(adx_min=15, fast=24, slow=96) 5x SL 4ATR TP 4ATR | -14.57% |
| 2025-11-24 → 2025-12-01 | trend_ema(adx_min=15, fast=24, slow=96) 2x SL 4ATR TP 4ATR | -20.35% |
| 2025-12-01 → 2025-12-08 | flat (no positive edge in training window) | 0.0% |
| 2025-12-08 → 2025-12-15 | flat (no positive edge in training window) | 0.0% |
| 2025-12-15 → 2025-12-22 | flat (no positive edge in training window) | 0.0% |
| 2025-12-22 → 2025-12-29 | flat (no positive edge in training window) | 0.0% |
| 2025-12-29 → 2026-01-05 | flat (no positive edge in training window) | 0.0% |
| 2026-01-05 → 2026-01-12 | flat (no positive edge in training window) | 0.0% |
| 2026-01-12 → 2026-01-19 | flat (no positive edge in training window) | 0.0% |
| 2026-01-19 → 2026-01-26 | flat (no positive edge in training window) | 0.0% |
| 2026-01-26 → 2026-02-02 | flat (no positive edge in training window) | 0.0% |
| 2026-02-02 → 2026-02-09 | trend_ema(adx_min=15, fast=48, slow=192) 2x SL 0ATR TP 8ATR | 6.85% |
| 2026-02-09 → 2026-02-16 | mean_reversion(er_max=0.5, window=96, z_in=2.5) 5x SL 4ATR TP 4ATR | 19.04% |
| 2026-02-16 → 2026-02-23 | mean_reversion(er_max=0.5, window=96, z_in=2.5) 5x SL 4ATR TP 4ATR | -6.87% |
| 2026-02-23 → 2026-03-02 | mean_reversion(er_max=0.5, window=96, z_in=2.5) 5x SL 4ATR TP 4ATR | -15.01% |
| 2026-03-02 → 2026-03-09 | donchian(entry=48, exit_=24) 2x SL 2ATR TP 0ATR | -10.4% |
| 2026-03-09 → 2026-03-16 | mean_reversion(er_max=0.3, window=96, z_in=2.5) 2x SL 4ATR TP 0ATR | -5.0% |
| 2026-03-16 → 2026-03-23 | flat (no positive edge in training window) | 0.0% |
| 2026-03-23 → 2026-03-30 | donchian(entry=48, exit_=24) 2x SL 4ATR TP 0ATR | -8.22% |
| 2026-03-30 → 2026-04-06 | donchian(entry=48, exit_=24) 2x SL 4ATR TP 0ATR | -15.16% |
| 2026-04-06 → 2026-04-13 | flat (no positive edge in training window) | 0.0% |
| 2026-04-13 → 2026-04-20 | flat (no positive edge in training window) | 0.0% |
| 2026-04-20 → 2026-04-27 | flat (no positive edge in training window) | 0.0% |
| 2026-04-27 → 2026-05-04 | flat (no positive edge in training window) | 0.0% |
| 2026-05-04 → 2026-05-11 | flat (no positive edge in training window) | 0.0% |
| 2026-05-11 → 2026-05-18 | flat (no positive edge in training window) | 0.0% |
| 2026-05-18 → 2026-05-25 | flat (no positive edge in training window) | 0.0% |
| 2026-05-25 → 2026-06-01 | flat (no positive edge in training window) | 0.0% |
| 2026-06-01 → 2026-06-08 | flat (no positive edge in training window) | 0.0% |
| 2026-06-08 → 2026-06-15 | flat (no positive edge in training window) | 0.0% |
| 2026-06-15 → 2026-06-22 | flat (no positive edge in training window) | 0.0% |
| 2026-06-22 → 2026-06-29 | flat (no positive edge in training window) | 0.0% |
| 2026-06-29 → 2026-07-06 | flat (no positive edge in training window) | 0.0% |
| 2026-07-06 → 2026-07-13 | flat (no positive edge in training window) | 0.0% |
| 2026-07-13 → 2026-07-20 | flat (no positive edge in training window) | 0.0% |
| 2026-07-20 → 2026-07-27 | flat (no positive edge in training window) | 0.0% |
| 2026-07-27 → 2026-08-03 | flat (no positive edge in training window) | 0.0% |
| 2026-08-03 → 2026-08-10 | flat (no positive edge in training window) | 0.0% |
| 2026-08-10 → 2026-08-17 | flat (no positive edge in training window) | 0.0% |
| 2026-08-17 → 2026-08-24 | flat (no positive edge in training window) | 0.0% |
| 2026-08-24 → 2026-08-31 | donchian(entry=192, exit_=96) 2x SL 2ATR TP 0ATR | -12.59% |
| 2026-08-31 → 2026-09-07 | donchian(entry=192, exit_=96) 2x SL 0ATR TP 0ATR | 4.92% |
| 2026-09-07 → 2026-09-14 | donchian(entry=192, exit_=96) 5x SL 2ATR TP 0ATR | -26.33% |
| 2026-09-14 → 2026-09-21 | donchian(entry=192, exit_=96) 2x SL 2ATR TP 0ATR | -10.14% |
| 2026-09-21 → 2026-09-28 | flat (no positive edge in training window) | 0.0% |
| 2026-09-28 → 2026-10-05 | flat (no positive edge in training window) | 0.0% |
| 2026-10-05 → 2026-10-12 | flat (no positive edge in training window) | 0.0% |
| 2026-10-12 → 2026-10-19 | flat (no positive edge in training window) | 0.0% |
| 2026-10-19 → 2026-10-19 | flat (no positive edge in training window) | 0.0% |
