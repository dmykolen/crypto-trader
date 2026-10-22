# Event-driven playbooks — out-of-sample report

Generated 2026-10-22T23:38:50+00:00. Every trade below was chosen by a rule that saw only events whose 24h outcome
was known before the notice appeared (walk-forward). Costs: taker fee, slippage, stop slippage, funding, isolated
liquidation with maintenance margin — see `assumptions`.

## Criterion: ≥ $100 within 24h from a $1000 balance, on ≥ 3 tokens

* **Per trade** (each OOS trade on a fresh $1000, closed ≤ 24h after the notice): **148** trades made ≥ $100 on **126** distinct tokens.
* **One account** ($1000 start, 20% of equity per trade, ≤ 5 open, ≤ 30% per announcement): ends at **$3,483.4** (+248.34%, max drawdown -42.29%); **18** trades made ≥ 10% of the balance within 24h on **17** tokens.
* Criterion met (both views, account profitable overall): **True**; still met without the 5 most profitable announcements: **True**

## Headline

* events with a tradable perpetual window: **544**
* out-of-sample trades: **425**, win rate **0.513**, mean / median return on margin **0.0592 / 0.0058**
* liquidations: **0**

```json
{
  "entry_latency_s": 60,
  "taker_fee": 0.0005,
  "slippage_per_side": 0.0015,
  "stop_slippage_per_side": 0.003,
  "maintenance_margin": 0.02,
  "fills": "1m bars; entry at the bar open after the delay; a stop that gaps fills at the open; take-profit never better than its level; stop/liquidation before take-profit inside a bar",
  "funding": "every historical settlement inside the holding window is charged on the position notional (shorts pay negative rates)",
  "selection": "walk-forward, LCB(z=1.0) of log-growth, ≥10 prior events with known 24h outcomes",
  "risk_rule": "stops always fire before liquidation (stop ≤ 80% of the liquidation distance)",
  "sizing": "per-trade view: a fresh $1000 balance as isolated margin; account view: 20% of equity per trade, ≤5 open, ≤30% per announcement (the live trader's rules)"
}
```

## One account, two sizing policies

Overlapping signals share the balance: a signal is skipped while its symbol is open or no margin is free. `all_in` commits
the whole free balance to every trade — shown only to make the point that it is ruinous even with a positive edge.

| policy | final_equity | return_pct | max_drawdown_pct | trades_taken | signals_skipped | win_rate | trading_days | days_ge_10pct | days_le_minus_10pct | best_day_pct | worst_day_pct |
|---|---|---|---|---|---|---|---|---|---|---|---|
| fraction | 3483.4 | 248.34 | -42.29 | 335 | 90 | 0.493 | 244 | 18 | 15 | 25.59 | -21.42 |
| all_in | 17.86 | -98.21 | -99.86 | 240 | 185 | 0.512 | 221 | 70 | 61 | 101.76 | -81.5 |

## By half-year (is the edge steady?)

| period | oos_trades | win_rate | mean_ret_on_margin | account_equity_end | account_period_return_pct |
|---|---|---|---|---|---|
| 2021-H1 | 2 | 1.0 | 0.5025 | 1151.05 | 15.1 |
| 2021-H2 | 3 | 0.667 | -0.0266 | 1097.1 | -4.69 |
| 2022-H1 | 7 | 0.286 | -0.0823 | 966.0 | -11.95 |
| 2022-H2 | 1 | 0.0 | -0.3956 | 889.57 | -7.91 |
| 2023-H1 | 8 | 0.625 | -0.0312 | 861.41 | -3.17 |
| 2023-H2 | 7 | 0.857 | 0.1721 | 1085.87 | 26.06 |
| 2024-H1 | 13 | 0.154 | -0.063 | 959.42 | -11.65 |
| 2024-H2 | 36 | 0.556 | 0.0575 | 1439.71 | 50.06 |
| 2025-H1 | 62 | 0.419 | 0.0361 | 1498.96 | 4.12 |
| 2025-H2 | 86 | 0.57 | 0.0527 | 1673.66 | 11.65 |
| 2026-H1 | 133 | 0.571 | 0.1229 | 5152.47 | 207.86 |
| 2026-H2 | 67 | 0.418 | -0.0016 | 3483.38 | -32.39 |

## Concentration (the account without its best announcements / trades / half-year)

| variant | oos_trades | mean_ret_on_margin | tokens_ge_100_on_fresh_1000 | account_return_pct | account_max_dd_pct | account_tokens_ge_10pct_in_24h |
|---|---|---|---|---|---|---|
| all OOS trades | 425 | 0.0592 | 126 | 248.34 | -42.29 | 17 |
| without the best 1 announcement(s) | 416 | 0.0498 | 124 | 198.99 | -42.29 | 17 |
| without the best 2 announcement(s) | 408 | 0.0414 | 121 | 154.13 | -46.11 | 16 |
| without the best 5 announcement(s) | 394 | 0.0221 | 110 | 29.87 | -49.65 | 13 |
| without the best 10 announcement(s) | 373 | 0.0062 | 98 | -13.11 | -53.5 | 11 |
| without the best 10 trades | 415 | 0.035 | 118 | 42.97 | -54.79 | 12 |
| without the best half-year (2026-H1) | 292 | 0.0302 | 89 | 13.15 | -49.19 | 9 |

## Mean return on margin, announcements resampled as clusters (bootstrap, 90% interval)

Trades triggered by one notice move together, so the notice — not the trade — is the independent unit.

| group | announcements | trades | mean | 90% interval | P(mean ≤ 0) |
|---|---|---|---|---|---|
| all | 276 | 425 | 0.0592 | 0.0227 … 0.0962 | 0.0034 |
| binance_monitoring_tag | 20 | 84 | 0.1466 | 0.0241 … 0.2527 | 0.0274 |
| binance_perp_delisting | 19 | 31 | 0.0254 | -0.0769 … 0.1109 | 0.3282 |
| binance_spot_delisting | 22 | 60 | 0.1207 | 0.0021 … 0.2523 | 0.047 |
| binance_spot_listing | 22 | 24 | 0.0214 | -0.0642 … 0.1187 | 0.3324 |
| upbit_delisting | 14 | 14 | -0.0453 | -0.1004 … 0.0096 | 0.9152 |
| upbit_krw_listing | 109 | 113 | -0.024 | -0.048 … 0.0 | 0.9498 |
| upbit_listing | 38 | 67 | 0.071 | 0.0037 … 0.1453 | 0.037 |
| upbit_warning | 32 | 32 | 0.0906 | -0.0306 … 0.2157 | 0.1148 |

## Robustness (same walk-forward and account, harsher assumptions)

| variant | oos_trades | win_rate | mean_ret_on_margin | tokens_ge_100_on_fresh_1000 | account_return_pct | account_max_dd_pct | account_tokens_ge_10pct_in_24h |
|---|---|---|---|---|---|---|---|
| baseline | 425 | 0.513 | 0.0592 | 126 | 248.34 | -42.29 | 17 |
| entry latency 3 min | 440 | 0.495 | 0.0269 | 114 | 56.61 | -38.67 | 12 |
| entry latency 5 min | 399 | 0.479 | 0.0175 | 109 | 10.4 | -53.55 | 6 |
| 2x slippage | 357 | 0.51 | 0.0527 | 116 | 164.69 | -39.83 | 13 |
| 3x slippage | 319 | 0.514 | 0.038 | 104 | 62.39 | -45.28 | 12 |
| looser selection z=0.5 | 459 | 0.501 | 0.0586 | 137 | 225.99 | -45.03 | 22 |
| stricter selection z=2 | 270 | 0.563 | 0.0531 | 94 | 227.16 | -25.89 | 9 |

## Per event type (out-of-sample, each trade on a fresh $1000)

| type | events | oos_trades | win_rate | mean_ret_on_margin | total_pnl_on_1000_each | trades_ge_100_usd_in_24h | liquidations |
|---|---|---|---|---|---|---|---|
| binance_monitoring_tag | 94 | 84 | 0.56 | 0.1466 | 12312.22 | 44 | 0 |
| binance_perp_delisting | 44 | 31 | 0.581 | 0.0254 | 787.72 | 13 | 0 |
| binance_spot_delisting | 72 | 60 | 0.567 | 0.1207 | 7242.29 | 28 | 0 |
| binance_spot_listing | 34 | 24 | 0.375 | 0.0214 | 513.29 | 7 | 0 |
| upbit_delisting | 27 | 14 | 0.143 | -0.0453 | -634.29 | 1 | 0 |
| upbit_krw_listing | 154 | 113 | 0.416 | -0.024 | -2706.85 | 10 | 0 |
| upbit_listing | 77 | 67 | 0.672 | 0.071 | 4755.55 | 34 | 0 |
| upbit_warning | 42 | 32 | 0.5 | 0.0906 | 2898.54 | 11 | 0 |

## Live playbooks (fitted on all history with the same rule)

| type | playbook | events | mean R | win rate | worst R |
|---|---|---|---|---|---|
| binance_monitoring_tag | SHORT 5x, enter +0m, hold ≤1380m, SL 5% | 94 | 0.1831 | 0.585 | -0.286 |
| binance_perp_delisting | SHORT 2x, enter +5m, hold ≤240m, SL 20% | 44 | 0.0835 | 0.5 | -0.4094 |
| binance_spot_delisting | SHORT 5x, enter +30m, hold ≤480m, SL 10%, TP 20%, trail 10% | 72 | 0.2715 | 0.597 | -0.5218 |
| binance_spot_listing | LONG 1x, enter +5m, hold ≤480m, SL 10% | 34 | 0.0701 | 0.441 | -0.104 |
| upbit_delisting | skip — no positive edge | 27 | None | None | None |
| upbit_krw_listing | skip — no positive edge | 154 | None | None | None |
| upbit_listing | SHORT 2x, enter +60m, hold ≤480m, SL 35%, TP 10% | 77 | 0.0491 | 0.675 | -0.1409 |
| upbit_warning | SHORT 5x, enter +0m, hold ≤1380m, SL 5%, TP 20%, trail 10% | 42 | 0.1703 | 0.548 | -0.2767 |

## Event study (average path after the first possible fill, mean / median)

| type | n | jump before fill | 1h | 4h | 8h | 23h |
|---|---|---|---|---|---|---|
| binance_monitoring_tag | 94 | -4.55% / -4.12% | -1.74% / -1.14% | -3.26% / -2.32% | -3.48% / -3.87% | -4.88% / -4.78% |
| binance_perp_delisting | 44 | +2.44% / -1.39% | -2.72% / -0.43% | +2.72% / -1.37% | -5.02% / -2.45% | -3.74% / -2.26% |
| binance_spot_delisting | 72 | -9.08% / -10.70% | -0.79% / -1.09% | -5.26% / -6.21% | -7.09% / -7.37% | -4.29% / -8.73% |
| binance_spot_listing | 34 | +18.27% / +8.33% | +3.30% / +0.45% | +3.46% / -0.08% | +4.44% / -2.49% | +0.51% / -1.11% |
| upbit_delisting | 27 | -4.88% / -3.48% | -0.45% / +0.00% | +0.17% / +0.00% | +1.62% / +0.00% | +0.42% / +0.00% |
| upbit_krw_listing | 154 | +23.58% / +14.70% | +0.27% / -0.33% | -0.16% / -1.05% | -0.99% / -3.50% | -3.46% / -6.48% |
| upbit_listing | 77 | +6.63% / +3.69% | +0.02% / -0.59% | -2.00% / -2.62% | -3.85% / -3.76% | -4.32% / -3.73% |
| upbit_warning | 42 | -0.42% / -0.15% | -2.07% / -0.67% | -4.79% / -0.71% | -2.30% / -0.40% | -5.85% / -1.70% |

## Account trades that made ≥ 10% of the balance within 24h (≥ $100 per $1000)

| entry (UTC) | exit (UTC) | symbol | event | balance at entry | margin | PnL | return on margin |
|---|---|---|---|---|---|---|---|
| 2021-04-14T07:02:00+00:00 | 2021-04-14T14:13:00+00:00 | GRTUSDT | upbit_listing | 1000.0 | 200.0 | +101.12 | +0.506 |
| 2024-11-13T06:46:00+00:00 | 2024-11-13T14:46:00+00:00 | AGLDUSDT | upbit_listing | 1189.76 | 237.95 | +167.60 | +0.704 |
| 2025-04-03T07:02:00+00:00 | 2025-04-04T06:02:00+00:00 | BSWUSDT | binance_monitoring_tag | 1638.07 | 327.61 | +333.37 | +1.018 |
| 2025-07-25T02:21:00+00:00 | 2025-07-26T01:21:00+00:00 | HUMAUSDT | upbit_listing | 1387.04 | 277.41 | +214.35 | +0.773 |
| 2025-10-02T12:31:00+00:00 | 2025-10-02T13:38:00+00:00 | ZKCUSDT | upbit_warning | 1171.76 | 234.35 | +231.89 | +0.989 |
| 2025-10-10T06:31:00+00:00 | 2025-10-10T06:47:00+00:00 | INUSDT | upbit_krw_listing | 1530.71 | 306.14 | +181.76 | +0.594 |
| 2025-10-29T03:17:00+00:00 | 2025-10-29T03:34:00+00:00 | FLMUSDT | binance_spot_delisting | 1547.86 | 309.57 | +306.32 | +0.989 |
| 2026-02-12T07:02:00+00:00 | 2026-02-13T06:02:00+00:00 | NOMUSDT | upbit_warning | 1685.26 | 337.05 | +270.10 | +0.801 |
| 2026-03-06T08:31:00+00:00 | 2026-03-07T07:31:00+00:00 | COSUSDT | binance_monitoring_tag | 1603.93 | 320.79 | +200.35 | +0.625 |
| 2026-04-20T05:31:00+00:00 | 2026-04-20T06:31:00+00:00 | PIEVERSEUSDT | upbit_krw_listing | 1843.37 | 368.67 | +188.25 | +0.511 |
| 2026-05-13T08:32:00+00:00 | 2026-05-13T09:48:00+00:00 | ATAUSDT | binance_spot_delisting | 1931.21 | 386.24 | +382.19 | +0.989 |
| 2026-05-22T08:02:00+00:00 | 2026-05-23T07:02:00+00:00 | COOKIEUSDT | binance_monitoring_tag | 2487.86 | 497.57 | +381.16 | +0.766 |
| 2026-06-05T07:32:00+00:00 | 2026-06-05T15:32:00+00:00 | COSUSDT | binance_spot_delisting | 3012.42 | 602.48 | +412.63 | +0.685 |
| 2026-06-15T09:32:00+00:00 | 2026-06-16T08:32:00+00:00 | OPGUSDT | upbit_listing | 3650.55 | 730.11 | +397.27 | +0.544 |
| 2026-06-18T07:31:00+00:00 | 2026-06-18T08:14:00+00:00 | AERGOUSDT | upbit_warning | 4047.82 | 809.56 | +795.26 | +0.982 |
| 2026-06-22T05:01:00+00:00 | 2026-06-23T04:01:00+00:00 | TAIKOUSDT | upbit_warning | 4830.37 | 966.07 | +553.69 | +0.573 |
| 2026-08-11T06:01:00+00:00 | 2026-08-12T01:01:00+00:00 | RVNUSDT | upbit_warning | 3385.73 | 677.15 | +633.53 | +0.936 |
| 2026-09-22T06:02:00+00:00 | 2026-09-23T05:02:00+00:00 | SOPHUSDT | upbit_warning | 3107.18 | 621.44 | +321.54 | +0.517 |

## Every out-of-sample trade (each on a fresh $1000)

| announced (UTC) | type | symbol | playbook | entry → exit | R | PnL on $1000 |
|---|---|---|---|---|---|---|
| 2021-04-14T07:00:01+00:00 | upbit_listing | GRTUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 10%, TP 10% | 2021-04-14T07:02:00+00:00 → 2021-04-14T14:13:00+00:00 | +0.506 | +505.60 |
| 2021-04-14T07:00:01+00:00 | upbit_listing | SNXUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 10%, TP 10% | 2021-04-14T07:02:00+00:00 → 2021-04-14T14:15:00+00:00 | +0.499 | +499.32 |
| 2021-12-22T04:00:01+00:00 | upbit_listing | GTCUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 10%, TP 10% | 2021-12-22T04:02:00+00:00 → 2021-12-22T04:52:00+00:00 | -0.522 | -521.76 |
| 2021-12-22T04:00:01+00:00 | upbit_listing | OCEANUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 10%, TP 10% | 2021-12-22T04:02:00+00:00 → 2021-12-23T03:02:00+00:00 | +0.285 | +285.13 |
| 2021-12-29T04:50:01+00:00 | upbit_listing | LPTUSDT | SHORT 5x, enter +60m, hold ≤480m, SL 10%, TP 10% | 2021-12-29T05:52:00+00:00 → 2021-12-29T13:52:00+00:00 | +0.157 | +156.70 |
| 2022-02-08T04:00:23+00:00 | upbit_krw_listing | AVAXUSDT | SHORT 5x, enter +30m, hold ≤60m, SL 10%, TP 10% | 2022-02-08T04:32:00+00:00 → 2022-02-08T05:32:00+00:00 | -0.031 | -31.22 |
| 2022-03-17T02:00:01+00:00 | upbit_krw_listing | CELOUSDT | SHORT 5x, enter +30m, hold ≤60m, SL 10%, TP 10% | 2022-03-17T02:32:00+00:00 → 2022-03-17T03:32:00+00:00 | -0.090 | -89.81 |
| 2022-04-21T01:25:01+00:00 | upbit_listing | API3USDT | SHORT 3x, enter +0m, hold ≤1380m, SL 20%, TP 10% | 2022-04-21T01:27:00+00:00 → 2022-04-21T08:08:00+00:00 | +0.293 | +293.38 |
| 2022-05-03T01:30:01+00:00 | upbit_listing | ARPAUSDT | SHORT 5x, enter +60m, hold ≤480m, SL 10% | 2022-05-03T02:32:00+00:00 → 2022-05-03T07:06:00+00:00 | -0.522 | -521.76 |
| 2022-05-03T01:30:01+00:00 | upbit_listing | ENSUSDT | SHORT 5x, enter +60m, hold ≤480m, SL 10% | 2022-05-03T02:32:00+00:00 → 2022-05-03T10:32:00+00:00 | +0.035 | +35.05 |
| 2022-05-04T01:00:01+00:00 | upbit_krw_listing | GMTUSDT | SHORT 5x, enter +30m, hold ≤60m, SL 10%, TP 10% | 2022-05-04T01:32:00+00:00 → 2022-05-04T02:32:00+00:00 | -0.023 | -22.88 |
| 2022-05-17T01:32:28+00:00 | upbit_listing | APEUSDT | SHORT 3x, enter +0m, hold ≤1380m, SL 20%, TP 10% | 2022-05-17T01:34:00+00:00 → 2022-05-18T00:34:00+00:00 | -0.239 | -239.12 |
| 2022-07-14T01:25:01+00:00 | upbit_listing | RAYUSDT | SHORT 3x, enter +0m, hold ≤1380m, SL 20%, TP 10% | 2022-07-14T01:27:00+00:00 → 2022-07-15T00:27:00+00:00 | -0.396 | -395.62 |
| 2023-01-18T01:00:16+00:00 | upbit_krw_listing | 1000SHIBUSDT | SHORT 5x, enter +30m, hold ≤60m, SL 10%, TP 10% | 2023-01-18T01:32:00+00:00 → 2023-01-18T02:32:00+00:00 | -0.280 | -280.37 |
| 2023-01-18T01:00:16+00:00 | upbit_krw_listing | GALUSDT | SHORT 5x, enter +30m, hold ≤60m, SL 10%, TP 10% | 2023-01-18T01:32:00+00:00 → 2023-01-18T02:32:00+00:00 | -0.226 | -225.60 |
| 2023-03-07T00:30:08+00:00 | upbit_krw_listing | MASKUSDT | LONG 2x, enter +0m, hold ≤240m, SL 5%, TP 20%, trail 10% | 2023-03-07T00:32:00+00:00 → 2023-03-07T04:32:00+00:00 | +0.037 | +37.27 |
| 2023-03-21T00:51:45+00:00 | upbit_listing | MAGICUSDT | SHORT 3x, enter +30m, hold ≤480m, SL 20% | 2023-03-21T01:23:00+00:00 → 2023-03-21T09:23:00+00:00 | +0.141 | +140.65 |
| 2023-03-30T01:00:00+00:00 | upbit_krw_listing | ARBUSDT | LONG 2x, enter +0m, hold ≤240m, SL 5%, TP 20%, trail 10% | 2023-03-30T01:01:00+00:00 → 2023-03-30T05:01:00+00:00 | +0.063 | +62.70 |
| 2023-04-27T01:00:17+00:00 | upbit_krw_listing | EGLDUSDT | LONG 3x, enter +0m, hold ≤240m, SL 5%, TP 20%, trail 10% | 2023-04-27T01:02:00+00:00 → 2023-04-27T05:02:00+00:00 | +0.013 | +12.59 |
| 2023-06-01T04:30:02+00:00 | upbit_krw_listing | GRTUSDT | LONG 3x, enter +0m, hold ≤240m, SL 5%, TP 20%, trail 10% | 2023-06-01T04:32:00+00:00 → 2023-06-01T04:37:00+00:00 | -0.161 | -161.47 |
| 2023-06-27T05:00:00+00:00 | upbit_krw_listing | BLURUSDT | LONG 2x, enter +0m, hold ≤240m, SL 5%, TP 20%, trail 10% | 2023-06-27T05:01:00+00:00 → 2023-06-27T09:01:00+00:00 | +0.165 | +164.73 |
| 2023-07-11T00:00:02+00:00 | upbit_listing | MINAUSDT | SHORT 3x, enter +30m, hold ≤480m, SL 20% | 2023-07-11T00:32:00+00:00 → 2023-07-11T08:32:00+00:00 | +0.002 | +2.49 |
| 2023-07-28T02:30:00+00:00 | upbit_krw_listing | IMXUSDT | LONG 3x, enter +0m, hold ≤240m, SL 5%, TP 20%, trail 10% | 2023-07-28T02:31:00+00:00 → 2023-07-28T06:31:00+00:00 | +0.041 | +40.77 |
| 2023-08-10T00:10:00+00:00 | upbit_listing | STGUSDT | SHORT 3x, enter +60m, hold ≤480m, SL 20% | 2023-08-10T01:11:00+00:00 → 2023-08-10T09:11:00+00:00 | +0.200 | +200.04 |
| 2023-08-22T00:20:02+00:00 | upbit_listing | CYBERUSDT | SHORT 3x, enter +60m, hold ≤480m, SL 20% | 2023-08-22T01:22:00+00:00 → 2023-08-22T09:22:00+00:00 | +0.320 | +319.90 |
| 2023-10-24T04:25:01+00:00 | upbit_krw_listing | MINAUSDT | LONG 3x, enter +0m, hold ≤240m, SL 5%, TP 20%, trail 10% | 2023-10-24T04:27:00+00:00 → 2023-10-24T04:31:00+00:00 | -0.161 | -161.47 |
| 2023-11-30T05:00:00+00:00 | upbit_listing | IDUSDT | SHORT 3x, enter +60m, hold ≤480m, SL 20% | 2023-11-30T06:01:00+00:00 → 2023-11-30T14:01:00+00:00 | +0.409 | +409.12 |
| 2023-12-18T07:30:00+00:00 | upbit_krw_listing | ASTRUSDT | LONG 2x, enter +0m, hold ≤240m, SL 5%, TP 20%, trail 10% | 2023-12-18T07:31:00+00:00 → 2023-12-18T07:32:00+00:00 | +0.394 | +394.20 |
| 2024-02-07T04:13:10+00:00 | upbit_krw_listing | IDUSDT | LONG 3x, enter +0m, hold ≤240m, SL 5%, TP 20%, trail 10% | 2024-02-07T04:15:00+00:00 → 2024-02-07T04:17:00+00:00 | -0.161 | -161.47 |
| 2024-02-27T02:45:08+00:00 | upbit_krw_listing | ALTUSDT | LONG 2x, enter +0m, hold ≤240m, SL 10%, TP 20% | 2024-02-27T02:47:00+00:00 → 2024-02-27T06:47:00+00:00 | -0.003 | -2.77 |
| 2024-02-27T02:45:08+00:00 | upbit_krw_listing | PYTHUSDT | LONG 2x, enter +0m, hold ≤240m, SL 10%, TP 20% | 2024-02-27T02:47:00+00:00 → 2024-02-27T06:47:00+00:00 | +0.166 | +165.57 |
| 2024-04-23T05:32:10+00:00 | upbit_krw_listing | BIGTIMEUSDT | LONG 2x, enter +0m, hold ≤240m, SL 10%, TP 20% | 2024-04-23T05:34:00+00:00 → 2024-04-23T08:37:00+00:00 | -0.203 | -203.47 |
| 2024-05-03T05:36:10+00:00 | upbit_krw_listing | ZETAUSDT | LONG 2x, enter +0m, hold ≤240m, SL 10%, TP 20% | 2024-05-03T05:38:00+00:00 → 2024-05-03T09:31:00+00:00 | -0.191 | -191.40 |
| 2024-05-03T05:36:10+00:00 | upbit_krw_listing | OMNIUSDT | LONG 2x, enter +0m, hold ≤240m, SL 10%, TP 20% | 2024-05-03T05:38:00+00:00 → 2024-05-03T05:39:00+00:00 | -0.207 | -207.30 |
| 2024-05-08T05:00:26+00:00 | binance_perp_delisting | IDEXUSDT | LONG 5x, enter +15m, hold ≤60m, SL 5%, TP 10% | 2024-05-08T05:17:00+00:00 → 2024-05-08T06:17:00+00:00 | +0.081 | +81.31 |
| 2024-05-08T05:00:26+00:00 | binance_perp_delisting | SLPUSDT | LONG 5x, enter +15m, hold ≤60m, SL 5%, TP 10% | 2024-05-08T05:17:00+00:00 → 2024-05-08T06:17:00+00:00 | -0.052 | -52.42 |
| 2024-05-08T05:00:26+00:00 | binance_perp_delisting | GLMRUSDT | LONG 5x, enter +15m, hold ≤60m, SL 5%, TP 10% | 2024-05-08T05:17:00+00:00 → 2024-05-08T06:17:00+00:00 | -0.041 | -41.04 |
| 2024-05-08T05:00:26+00:00 | binance_perp_delisting | MDTUSDT | LONG 5x, enter +15m, hold ≤60m, SL 5%, TP 10% | 2024-05-08T05:17:00+00:00 → 2024-05-08T06:17:00+00:00 | -0.085 | -85.05 |
| 2024-05-08T05:00:26+00:00 | binance_perp_delisting | AUDIOUSDT | LONG 5x, enter +15m, hold ≤60m, SL 5%, TP 10% | 2024-05-08T05:17:00+00:00 → 2024-05-08T06:17:00+00:00 | -0.044 | -44.13 |
| 2024-05-29T09:15:13+00:00 | upbit_krw_listing | AUCTIONUSDT | LONG 1x, enter +0m, hold ≤240m, SL 5%, TP 20%, trail 10% | 2024-05-29T09:17:00+00:00 → 2024-05-29T10:04:00+00:00 | -0.023 | -23.07 |
| 2024-05-30T07:29:55+00:00 | upbit_krw_listing | STGUSDT | LONG 1x, enter +0m, hold ≤240m, SL 5%, TP 20%, trail 10% | 2024-05-30T07:31:00+00:00 → 2024-05-30T07:33:00+00:00 | -0.054 | -53.82 |
| 2024-07-01T07:00:03+00:00 | binance_monitoring_tag | BALUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 5%, TP 10% | 2024-07-01T07:02:00+00:00 → 2024-07-01T14:02:00+00:00 | +0.488 | +488.40 |
| 2024-07-01T07:00:03+00:00 | binance_monitoring_tag | CVXUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 5%, TP 10% | 2024-07-01T07:02:00+00:00 → 2024-07-02T06:02:00+00:00 | -0.019 | -18.53 |
| 2024-07-01T07:00:03+00:00 | binance_monitoring_tag | SNTUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 5%, TP 10% | 2024-07-01T07:02:00+00:00 → 2024-07-02T06:02:00+00:00 | -0.019 | -18.53 |
| 2024-07-01T07:00:03+00:00 | binance_monitoring_tag | ZENUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 5%, TP 10% | 2024-07-01T07:02:00+00:00 → 2024-07-01T07:23:00+00:00 | +0.488 | +488.50 |
| 2024-07-08T07:01:09+00:00 | binance_spot_delisting | BONDUSDT | SHORT 5x, enter +60m, hold ≤480m, SL 10% | 2024-07-08T08:03:00+00:00 → 2024-07-08T16:03:00+00:00 | +0.437 | +436.60 |
| 2024-08-12T07:00:11+00:00 | binance_spot_delisting | LOOMUSDT | SHORT 5x, enter +60m, hold ≤480m, SL 10% | 2024-08-12T08:02:00+00:00 → 2024-08-12T16:02:00+00:00 | -0.232 | -232.31 |
| 2024-08-12T07:00:11+00:00 | binance_spot_delisting | REEFUSDT | SHORT 5x, enter +60m, hold ≤480m, SL 10% | 2024-08-12T08:02:00+00:00 → 2024-08-12T16:02:00+00:00 | +0.009 | +9.28 |
| 2024-08-20T07:37:46+00:00 | upbit_listing | 1000PEPEUSDT | SHORT 3x, enter +60m, hold ≤480m, SL 20% | 2024-08-20T08:39:00+00:00 → 2024-08-20T16:39:00+00:00 | +0.065 | +65.05 |
| 2024-09-19T06:44:52+00:00 | upbit_listing | MEWUSDT | SHORT 3x, enter +30m, hold ≤480m, SL 20% | 2024-09-19T07:16:00+00:00 → 2024-09-19T15:16:00+00:00 | +0.085 | +85.25 |
| 2024-10-03T07:00:05+00:00 | binance_monitoring_tag | BLZUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 5%, TP 10% | 2024-10-03T07:02:00+00:00 → 2024-10-03T07:25:00+00:00 | -0.271 | -270.88 |
| 2024-10-03T07:00:05+00:00 | binance_monitoring_tag | KEYUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 5%, TP 10% | 2024-10-03T07:02:00+00:00 → 2024-10-03T08:21:00+00:00 | +0.489 | +488.87 |
| 2024-10-03T07:00:05+00:00 | binance_monitoring_tag | PENDLEUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 5%, TP 10% | 2024-10-03T07:02:00+00:00 → 2024-10-04T06:02:00+00:00 | +0.159 | +158.98 |
| 2024-10-03T07:00:05+00:00 | binance_monitoring_tag | SEIUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 5%, TP 10% | 2024-10-03T07:02:00+00:00 → 2024-10-04T06:02:00+00:00 | +0.240 | +240.05 |
| 2024-10-22T05:53:47+00:00 | upbit_listing | 1000BONKUSDT | SHORT 3x, enter +30m, hold ≤480m, SL 20% | 2024-10-22T06:25:00+00:00 → 2024-10-22T14:25:00+00:00 | +0.176 | +176.18 |
| 2024-10-23T07:00:37+00:00 | binance_spot_delisting | UNFIUSDT | SHORT 5x, enter +60m, hold ≤480m, SL 10% | 2024-10-23T08:02:00+00:00 → 2024-10-23T16:02:00+00:00 | +0.139 | +138.94 |
| 2024-11-13T06:15:00+00:00 | upbit_listing | AGLDUSDT | SHORT 3x, enter +30m, hold ≤480m, SL 20% | 2024-11-13T06:46:00+00:00 → 2024-11-13T14:46:00+00:00 | +0.704 | +704.35 |
| 2024-11-13T06:15:00+00:00 | upbit_listing | ARPAUSDT | SHORT 3x, enter +30m, hold ≤480m, SL 20% | 2024-11-13T06:46:00+00:00 → 2024-11-13T14:46:00+00:00 | -0.179 | -178.90 |
| 2024-11-13T06:15:00+00:00 | upbit_listing | ASTRUSDT | SHORT 3x, enter +30m, hold ≤480m, SL 20% | 2024-11-13T06:46:00+00:00 → 2024-11-13T14:46:00+00:00 | -0.113 | -113.15 |
| 2024-11-13T06:15:00+00:00 | upbit_listing | BNTUSDT | SHORT 3x, enter +30m, hold ≤480m, SL 20% | 2024-11-13T06:46:00+00:00 → 2024-11-13T14:46:00+00:00 | -0.185 | -184.55 |
| 2024-11-13T06:15:00+00:00 | upbit_listing | EGLDUSDT | SHORT 3x, enter +30m, hold ≤480m, SL 20% | 2024-11-13T06:46:00+00:00 → 2024-11-13T14:46:00+00:00 | -0.150 | -149.87 |
| 2024-11-13T06:15:00+00:00 | upbit_listing | FILUSDT | SHORT 3x, enter +30m, hold ≤480m, SL 20% | 2024-11-13T06:46:00+00:00 → 2024-11-13T14:46:00+00:00 | -0.213 | -213.13 |
| 2024-11-13T06:15:00+00:00 | upbit_listing | NEARUSDT | SHORT 3x, enter +30m, hold ≤480m, SL 20% | 2024-11-13T06:46:00+00:00 → 2024-11-13T14:46:00+00:00 | -0.220 | -219.76 |
| 2024-11-13T06:15:00+00:00 | upbit_listing | OXTUSDT | SHORT 3x, enter +30m, hold ≤480m, SL 20% | 2024-11-13T06:46:00+00:00 → 2024-11-13T14:46:00+00:00 | -0.215 | -215.45 |
| 2024-11-13T06:15:00+00:00 | upbit_listing | RADUSDT | SHORT 3x, enter +30m, hold ≤480m, SL 20% | 2024-11-13T06:46:00+00:00 → 2024-11-13T14:46:00+00:00 | -0.012 | -11.72 |
| 2024-11-13T06:15:00+00:00 | upbit_listing | XLMUSDT | SHORT 3x, enter +30m, hold ≤480m, SL 20% | 2024-11-13T06:46:00+00:00 → 2024-11-13T14:46:00+00:00 | -0.110 | -109.75 |
| 2024-11-20T02:49:09+00:00 | upbit_listing | JASMYUSDT | SHORT 3x, enter +60m, hold ≤480m, SL 20% | 2024-11-20T03:51:00+00:00 → 2024-11-20T11:51:00+00:00 | +0.108 | +107.58 |
| 2024-11-26T08:30:14+00:00 | binance_spot_delisting | KEYUSDT | SHORT 5x, enter +60m, hold ≤480m, SL 10% | 2024-11-26T09:32:00+00:00 → 2024-11-26T17:32:00+00:00 | -0.120 | -119.95 |
| 2024-11-26T08:30:14+00:00 | binance_spot_delisting | RENUSDT | SHORT 5x, enter +60m, hold ≤480m, SL 10% | 2024-11-26T09:32:00+00:00 → 2024-11-26T09:48:00+00:00 | -0.522 | -521.76 |
| 2024-11-29T04:00:01+00:00 | binance_perp_delisting | XEMUSDT | LONG 5x, enter +5m, hold ≤60m, SL 5% | 2024-11-29T04:07:00+00:00 → 2024-11-29T05:07:00+00:00 | +0.162 | +161.58 |
| 2024-11-29T04:00:01+00:00 | binance_perp_delisting | ORBSUSDT | LONG 5x, enter +5m, hold ≤60m, SL 5% | 2024-11-29T04:07:00+00:00 → 2024-11-29T05:07:00+00:00 | +0.047 | +47.33 |
| 2024-11-29T04:00:01+00:00 | binance_perp_delisting | LOOMUSDT | LONG 5x, enter +5m, hold ≤60m, SL 5% | 2024-11-29T04:07:00+00:00 → 2024-11-29T05:07:00+00:00 | +0.008 | +8.03 |
| 2024-12-05T03:01:45+00:00 | upbit_listing | SWELLUSDT | SHORT 3x, enter +60m, hold ≤480m, SL 20% | 2024-12-05T04:03:00+00:00 → 2024-12-05T12:03:00+00:00 | -0.067 | -67.21 |
| 2024-12-06T03:00:04+00:00 | binance_perp_delisting | MAVIAUSDT | LONG 5x, enter +5m, hold ≤60m, SL 5% | 2024-12-06T03:07:00+00:00 → 2024-12-06T04:07:00+00:00 | +0.095 | +94.85 |
| 2024-12-06T03:00:04+00:00 | binance_perp_delisting | OMGUSDT | LONG 5x, enter +5m, hold ≤60m, SL 5% | 2024-12-06T03:07:00+00:00 → 2024-12-06T04:07:00+00:00 | +0.352 | +352.29 |
| 2024-12-06T03:00:04+00:00 | binance_perp_delisting | BONDUSDT | LONG 5x, enter +5m, hold ≤60m, SL 5% | 2024-12-06T03:07:00+00:00 → 2024-12-06T04:07:00+00:00 | +0.171 | +170.63 |
| 2024-12-18T08:01:12+00:00 | binance_spot_delisting | BLZUSDT | SHORT 3x, enter +15m, hold ≤480m, SL 20%, TP 10% | 2024-12-18T08:18:00+00:00 → 2024-12-18T12:02:00+00:00 | +0.293 | +293.24 |
| 2025-01-02T09:00:19+00:00 | binance_monitoring_tag | STMXUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 5%, TP 10% | 2025-01-02T09:02:00+00:00 → 2025-01-03T08:02:00+00:00 | +0.208 | +208.30 |
| 2025-01-02T09:00:19+00:00 | binance_monitoring_tag | TROYUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 5%, TP 10% | 2025-01-02T09:02:00+00:00 → 2025-01-02T14:11:00+00:00 | +0.489 | +488.74 |
| 2025-01-15T08:00:06+00:00 | binance_perp_delisting | REEFUSDT | LONG 5x, enter +5m, hold ≤60m, SL 5% | 2025-01-15T08:07:00+00:00 → 2025-01-15T09:01:00+00:00 | -0.269 | -269.12 |
| 2025-01-31T08:17:39+00:00 | upbit_krw_listing | VIRTUALUSDT | SHORT 1x, enter +30m, hold ≤60m, SL 20% | 2025-01-31T08:49:00+00:00 → 2025-01-31T09:49:00+00:00 | -0.001 | -0.59 |
| 2025-02-06T04:58:53+00:00 | upbit_listing | JTOUSDT | SHORT 3x, enter +60m, hold ≤480m, SL 20% | 2025-02-06T06:00:00+00:00 → 2025-02-06T14:00:00+00:00 | +0.163 | +162.89 |
| 2025-02-06T04:58:53+00:00 | upbit_listing | SCRUSDT | SHORT 3x, enter +60m, hold ≤480m, SL 20% | 2025-02-06T06:00:00+00:00 → 2025-02-06T14:00:00+00:00 | +0.605 | +605.26 |
| 2025-02-09T07:10:31+00:00 | binance_spot_listing | 1000CHEEMSUSDT | LONG 3x, enter +5m, hold ≤60m, SL 20%, TP 20% | 2025-02-09T07:17:00+00:00 → 2025-02-09T08:17:00+00:00 | +0.127 | +126.53 |
| 2025-02-13T06:24:06+00:00 | upbit_krw_listing | TRUMPUSDT | SHORT 1x, enter +30m, hold ≤60m, SL 20% | 2025-02-13T06:56:00+00:00 → 2025-02-13T07:56:00+00:00 | +0.027 | +26.75 |
| 2025-02-17T07:00:24+00:00 | binance_spot_delisting | AMBUSDT | SHORT 3x, enter +15m, hold ≤480m, SL 20% | 2025-02-17T07:17:00+00:00 → 2025-02-17T15:17:00+00:00 | +0.399 | +399.43 |
| 2025-02-17T07:00:24+00:00 | binance_spot_delisting | STMXUSDT | SHORT 3x, enter +15m, hold ≤480m, SL 20% | 2025-02-17T07:17:00+00:00 → 2025-02-17T15:17:00+00:00 | -0.352 | -351.74 |
| 2025-02-21T05:00:00+00:00 | upbit_krw_listing | JTOUSDT | SHORT 1x, enter +30m, hold ≤60m, SL 20% | 2025-02-21T05:31:00+00:00 → 2025-02-21T06:31:00+00:00 | +0.053 | +52.51 |
| 2025-02-21T05:10:02+00:00 | upbit_listing | ARKMUSDT | SHORT 3x, enter +0m, hold ≤1380m, SL 20% | 2025-02-21T05:12:00+00:00 → 2025-02-22T04:12:00+00:00 | +0.233 | +233.07 |
| 2025-02-25T08:39:55+00:00 | upbit_krw_listing | COWUSDT | SHORT 1x, enter +30m, hold ≤60m, SL 20% | 2025-02-25T09:11:00+00:00 → 2025-02-25T10:11:00+00:00 | -0.009 | -8.69 |
| 2025-03-05T02:47:19+00:00 | upbit_krw_listing | KAITOUSDT | SHORT 1x, enter +30m, hold ≤60m, SL 20% | 2025-03-05T03:19:00+00:00 → 2025-03-05T04:19:00+00:00 | -0.069 | -69.25 |
| 2025-03-21T04:57:29+00:00 | upbit_krw_listing | ORCAUSDT | SHORT 1x, enter +30m, hold ≤60m, SL 20% | 2025-03-21T05:29:00+00:00 → 2025-03-21T06:29:00+00:00 | -0.044 | -44.18 |
| 2025-03-21T05:50:20+00:00 | binance_spot_delisting | AERGOUSDT | SHORT 2x, enter +0m, hold ≤1380m, SL 35%, TP 20% | 2025-03-21T05:52:00+00:00 → 2025-03-22T04:52:00+00:00 | -0.160 | -160.27 |
| 2025-03-21T05:50:20+00:00 | binance_spot_delisting | COMBOUSDT | SHORT 2x, enter +0m, hold ≤1380m, SL 35%, TP 20% | 2025-03-21T05:52:00+00:00 → 2025-03-21T05:59:00+00:00 | -0.710 | -710.45 |
| 2025-03-21T05:50:20+00:00 | binance_spot_delisting | LINAUSDT | SHORT 2x, enter +0m, hold ≤1380m, SL 35%, TP 20% | 2025-03-21T05:52:00+00:00 → 2025-03-21T18:09:00+00:00 | +0.396 | +395.58 |
| 2025-04-01T07:05:00+00:00 | upbit_krw_listing | COMPUSDT | SHORT 1x, enter +30m, hold ≤60m, SL 20% | 2025-04-01T07:36:00+00:00 → 2025-04-01T08:36:00+00:00 | +0.069 | +68.57 |
| 2025-04-03T07:00:36+00:00 | binance_monitoring_tag | BSWUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 5% | 2025-04-03T07:02:00+00:00 → 2025-04-04T06:02:00+00:00 | +1.018 | +1017.56 |
| 2025-04-03T07:00:36+00:00 | binance_monitoring_tag | FLMUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 5% | 2025-04-03T07:02:00+00:00 → 2025-04-03T07:06:00+00:00 | -0.271 | -270.88 |
| 2025-04-03T07:00:36+00:00 | binance_monitoring_tag | NKNUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 5% | 2025-04-03T07:02:00+00:00 → 2025-04-04T06:02:00+00:00 | +0.817 | +816.99 |
| 2025-04-03T07:00:36+00:00 | binance_monitoring_tag | PERPUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 5% | 2025-04-03T07:02:00+00:00 → 2025-04-04T06:02:00+00:00 | +0.646 | +646.43 |
| 2025-04-03T07:00:36+00:00 | binance_monitoring_tag | VOXELUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 5% | 2025-04-03T07:02:00+00:00 → 2025-04-04T06:02:00+00:00 | +1.544 | +1544.20 |
| 2025-04-03T07:00:36+00:00 | binance_monitoring_tag | JUPUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 5% | 2025-04-03T07:02:00+00:00 → 2025-04-04T06:02:00+00:00 | -0.198 | -198.40 |
| 2025-04-03T07:00:36+00:00 | binance_monitoring_tag | STRKUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 5% | 2025-04-03T07:02:00+00:00 → 2025-04-04T06:02:00+00:00 | -0.032 | -31.61 |
| 2025-04-03T07:00:36+00:00 | binance_monitoring_tag | TONUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 5% | 2025-04-03T07:02:00+00:00 → 2025-04-04T06:02:00+00:00 | +0.307 | +306.83 |
| 2025-04-04T07:04:42+00:00 | upbit_krw_listing | FILUSDT | SHORT 1x, enter +0m, hold ≤1380m, SL 5% | 2025-04-04T07:06:00+00:00 → 2025-04-05T06:06:00+00:00 | +0.058 | +58.10 |
| 2025-04-16T05:39:10+00:00 | upbit_krw_listing | WCTUSDT | SHORT 1x, enter +0m, hold ≤1380m, SL 5% | 2025-04-16T05:41:00+00:00 → 2025-04-16T05:42:00+00:00 | -0.054 | -54.18 |
| 2025-04-16T05:56:44+00:00 | upbit_listing | SHELLUSDT | SHORT 3x, enter +0m, hold ≤1380m, SL 20% | 2025-04-16T05:58:00+00:00 → 2025-04-17T04:58:00+00:00 | +0.119 | +119.08 |
| 2025-04-24T04:00:05+00:00 | binance_spot_delisting | ALPACAUSDT | SHORT 3x, enter +15m, hold ≤480m, SL 20% | 2025-04-24T04:17:00+00:00 → 2025-04-24T04:33:00+00:00 | -0.614 | -614.11 |
| 2025-04-24T06:00:00+00:00 | upbit_warning | SNXUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 10%, TP 20% | 2025-04-24T06:01:00+00:00 → 2025-04-24T20:16:00+00:00 | -0.521 | -520.73 |
| 2025-04-29T06:25:02+00:00 | upbit_krw_listing | SIGNUSDT | SHORT 2x, enter +30m, hold ≤60m, SL 20% | 2025-04-29T06:57:00+00:00 → 2025-04-29T07:57:00+00:00 | -0.108 | -107.92 |
| 2025-05-06T11:25:20+00:00 | binance_spot_listing | KMNOUSDT | LONG 5x, enter +15m, hold ≤60m, SL 10%, TP 10% | 2025-05-06T11:42:00+00:00 → 2025-05-06T12:42:00+00:00 | -0.086 | -85.92 |
| 2025-05-07T08:00:33+00:00 | binance_monitoring_tag | ALPHAUSDT | SHORT 5x, enter +5m, hold ≤480m, SL 5% | 2025-05-07T08:07:00+00:00 → 2025-05-07T08:10:00+00:00 | -0.271 | -270.88 |
| 2025-05-07T08:00:33+00:00 | binance_monitoring_tag | HIFIUSDT | SHORT 5x, enter +5m, hold ≤480m, SL 5% | 2025-05-07T08:07:00+00:00 → 2025-05-07T08:09:00+00:00 | -0.271 | -270.88 |
| 2025-05-07T08:00:33+00:00 | binance_monitoring_tag | LEVERUSDT | SHORT 5x, enter +5m, hold ≤480m, SL 5% | 2025-05-07T08:07:00+00:00 → 2025-05-07T08:19:00+00:00 | -0.271 | -270.88 |
| 2025-05-07T08:00:33+00:00 | binance_monitoring_tag | MOVEUSDT | SHORT 5x, enter +5m, hold ≤480m, SL 5% | 2025-05-07T08:07:00+00:00 → 2025-05-07T08:17:00+00:00 | -0.271 | -270.88 |
| 2025-05-07T08:00:33+00:00 | binance_monitoring_tag | PORTALUSDT | SHORT 5x, enter +5m, hold ≤480m, SL 5% | 2025-05-07T08:07:00+00:00 → 2025-05-07T08:16:00+00:00 | -0.271 | -270.88 |
| 2025-05-07T08:00:33+00:00 | binance_monitoring_tag | REIUSDT | SHORT 5x, enter +5m, hold ≤480m, SL 5% | 2025-05-07T08:07:00+00:00 → 2025-05-07T08:20:00+00:00 | -0.271 | -270.88 |
| 2025-05-08T07:26:15+00:00 | upbit_krw_listing | TIAUSDT | SHORT 1x, enter +30m, hold ≤60m, SL 20% | 2025-05-08T07:58:00+00:00 → 2025-05-08T08:58:00+00:00 | -0.001 | -1.05 |
| 2025-05-08T07:26:15+00:00 | upbit_krw_listing | IOUSDT | SHORT 1x, enter +30m, hold ≤60m, SL 20% | 2025-05-08T07:58:00+00:00 → 2025-05-08T08:58:00+00:00 | -0.048 | -47.52 |
| 2025-05-09T06:00:00+00:00 | upbit_krw_listing | PENGUUSDT | SHORT 1x, enter +30m, hold ≤60m, SL 20% | 2025-05-09T06:31:00+00:00 → 2025-05-09T07:31:00+00:00 | +0.024 | +24.31 |
| 2025-05-19T06:00:00+00:00 | upbit_warning | STMXUSDT | SHORT 5x, enter +0m, hold ≤480m, SL 10%, TP 20% | 2025-05-19T06:01:00+00:00 → 2025-05-19T14:01:00+00:00 | -0.020 | -19.53 |
| 2025-05-19T06:00:01+00:00 | upbit_warning | XEMUSDT | SHORT 5x, enter +0m, hold ≤480m, SL 10%, TP 20% | 2025-05-19T06:02:00+00:00 → 2025-05-19T14:02:00+00:00 | -0.020 | -19.53 |
| 2025-05-21T02:45:29+00:00 | upbit_krw_listing | OMUSDT | SHORT 1x, enter +0m, hold ≤1380m, SL 5% | 2025-05-21T02:47:00+00:00 → 2025-05-22T01:47:00+00:00 | +0.093 | +93.36 |
| 2025-05-23T02:48:50+00:00 | upbit_listing | KERNELUSDT | SHORT 3x, enter +0m, hold ≤1380m, SL 20% | 2025-05-23T02:50:00+00:00 → 2025-05-24T01:50:00+00:00 | +0.376 | +375.58 |
| 2025-05-27T07:44:50+00:00 | upbit_listing | HYPERUSDT | SHORT 3x, enter +0m, hold ≤1380m, SL 20% | 2025-05-27T07:46:00+00:00 → 2025-05-28T06:46:00+00:00 | +0.366 | +366.33 |
| 2025-05-27T07:44:50+00:00 | upbit_listing | REDUSDT | SHORT 3x, enter +0m, hold ≤1380m, SL 20% | 2025-05-27T07:46:00+00:00 → 2025-05-28T06:46:00+00:00 | +0.163 | +162.64 |
| 2025-05-30T03:15:00+00:00 | upbit_krw_listing | LPTUSDT | SHORT 1x, enter +0m, hold ≤1380m, SL 5% | 2025-05-30T03:16:00+00:00 → 2025-05-30T04:07:00+00:00 | -0.061 | -61.23 |
| 2025-06-05T05:00:18+00:00 | binance_monitoring_tag | FISUSDT | SHORT 5x, enter +30m, hold ≤480m, SL 10%, TP 20% | 2025-06-05T05:32:00+00:00 → 2025-06-05T13:32:00+00:00 | +0.121 | +121.27 |
| 2025-06-05T05:00:18+00:00 | binance_monitoring_tag | MDTUSDT | SHORT 5x, enter +30m, hold ≤480m, SL 10%, TP 20% | 2025-06-05T05:32:00+00:00 → 2025-06-05T13:32:00+00:00 | -0.020 | -19.53 |
| 2025-06-05T07:03:21+00:00 | upbit_krw_listing | RVNUSDT | SHORT 1x, enter +0m, hold ≤1380m, SL 5% | 2025-06-05T07:05:00+00:00 → 2025-06-05T07:06:00+00:00 | -0.054 | -54.18 |
| 2025-06-10T04:41:10+00:00 | upbit_listing | EPTUSDT | SHORT 3x, enter +0m, hold ≤1380m, SL 20% | 2025-06-10T04:43:00+00:00 → 2025-06-11T03:43:00+00:00 | +0.071 | +71.16 |
| 2025-06-10T04:41:12+00:00 | upbit_krw_listing | AXLUSDT | SHORT 1x, enter +30m, hold ≤60m, SL 20% | 2025-06-10T05:13:00+00:00 → 2025-06-10T06:13:00+00:00 | -0.076 | -75.95 |
| 2025-06-16T09:04:43+00:00 | upbit_listing | HAEDALUSDT | SHORT 3x, enter +0m, hold ≤1380m, SL 20% | 2025-06-16T09:06:00+00:00 → 2025-06-17T08:06:00+00:00 | +0.307 | +307.33 |
| 2025-06-16T09:04:45+00:00 | upbit_krw_listing | ALTUSDT | LONG 1x, enter +0m, hold ≤240m, SL 20%, TP 20% | 2025-06-16T09:06:00+00:00 → 2025-06-16T12:09:00+00:00 | -0.194 | -193.97 |
| 2025-06-19T00:35:03+00:00 | upbit_krw_listing | RAYUSDT | SHORT 1x, enter +30m, hold ≤60m, SL 20% | 2025-06-19T01:07:00+00:00 → 2025-06-19T02:07:00+00:00 | -0.004 | -4.01 |
| 2025-06-24T07:25:53+00:00 | upbit_krw_listing | NEWTUSDT | SHORT 1x, enter +30m, hold ≤60m, SL 20% | 2025-06-24T07:57:00+00:00 → 2025-06-24T08:57:00+00:00 | -0.002 | -1.60 |
| 2025-06-26T07:00:09+00:00 | binance_spot_delisting | ALPHAUSDT | SHORT 3x, enter +60m, hold ≤480m, SL 10% | 2025-06-26T08:02:00+00:00 → 2025-06-26T09:31:00+00:00 | -0.313 | -313.05 |
| 2025-06-26T07:00:09+00:00 | binance_spot_delisting | BSWUSDT | SHORT 3x, enter +60m, hold ≤480m, SL 10% | 2025-06-26T08:02:00+00:00 → 2025-06-26T09:03:00+00:00 | -0.313 | -313.05 |
| 2025-06-26T07:00:09+00:00 | binance_spot_delisting | LEVERUSDT | SHORT 3x, enter +60m, hold ≤480m, SL 10% | 2025-06-26T08:02:00+00:00 → 2025-06-26T09:46:00+00:00 | -0.313 | -313.05 |
| 2025-07-03T04:47:01+00:00 | upbit_krw_listing | MOODENGUSDT | SHORT 1x, enter +30m, hold ≤60m, SL 20% | 2025-07-03T05:19:00+00:00 → 2025-07-03T06:19:00+00:00 | +0.054 | +53.80 |
| 2025-07-07T03:29:57+00:00 | binance_monitoring_tag | BAKEUSDT | SHORT 5x, enter +30m, hold ≤480m, SL 10%, TP 20% | 2025-07-07T04:01:00+00:00 → 2025-07-07T04:49:00+00:00 | -0.522 | -521.76 |
| 2025-07-07T03:29:57+00:00 | binance_monitoring_tag | IDEXUSDT | SHORT 5x, enter +30m, hold ≤480m, SL 10%, TP 20% | 2025-07-07T04:01:00+00:00 → 2025-07-07T12:01:00+00:00 | -0.020 | -20.03 |
| 2025-07-10T03:30:00+00:00 | upbit_listing | BABYUSDT | SHORT 3x, enter +0m, hold ≤1380m, SL 20% | 2025-07-10T03:31:00+00:00 → 2025-07-11T02:31:00+00:00 | +0.024 | +23.52 |
| 2025-07-10T03:30:01+00:00 | upbit_krw_listing | HYPERUSDT | SHORT 2x, enter +30m, hold ≤60m, SL 20% | 2025-07-10T04:02:00+00:00 → 2025-07-10T05:02:00+00:00 | +0.039 | +39.40 |
| 2025-07-11T04:42:59+00:00 | upbit_krw_listing | ENAUSDT | SHORT 2x, enter +30m, hold ≤60m, SL 20% | 2025-07-11T05:14:00+00:00 → 2025-07-11T06:14:00+00:00 | +0.058 | +58.49 |
| 2025-07-25T02:19:50+00:00 | upbit_krw_listing | SYRUPUSDT | SHORT 2x, enter +30m, hold ≤60m, SL 20% | 2025-07-25T02:51:00+00:00 → 2025-07-25T03:51:00+00:00 | -0.010 | -9.90 |
| 2025-07-25T02:19:51+00:00 | upbit_listing | HUMAUSDT | SHORT 3x, enter +0m, hold ≤1380m, SL 20% | 2025-07-25T02:21:00+00:00 → 2025-07-26T01:21:00+00:00 | +0.773 | +772.70 |
| 2025-07-28T04:24:25+00:00 | upbit_krw_listing | OPUSDT | SHORT 2x, enter +30m, hold ≤60m, SL 20% | 2025-07-28T04:56:00+00:00 → 2025-07-28T05:56:00+00:00 | -0.029 | -28.69 |
| 2025-07-29T08:50:00+00:00 | upbit_krw_listing | OMNIUSDT | SHORT 2x, enter +60m, hold ≤60m, SL 20% | 2025-07-29T09:51:00+00:00 → 2025-07-29T10:51:00+00:00 | +0.188 | +187.57 |
| 2025-08-06T03:21:00+00:00 | upbit_krw_listing | PROVEUSDT | SHORT 3x, enter +60m, hold ≤60m, SL 20% | 2025-08-06T04:22:00+00:00 → 2025-08-06T05:22:00+00:00 | -0.104 | -103.83 |
| 2025-08-06T07:30:06+00:00 | binance_perp_delisting | DEFIUSDT | LONG 5x, enter +5m, hold ≤60m, SL 10% | 2025-08-06T07:37:00+00:00 → 2025-08-06T08:37:00+00:00 | -0.069 | -68.59 |
| 2025-08-08T02:09:39+00:00 | upbit_krw_listing | IPUSDT | SHORT 3x, enter +60m, hold ≤60m, SL 20% | 2025-08-08T03:11:00+00:00 → 2025-08-08T04:11:00+00:00 | +0.013 | +12.61 |
| 2025-08-12T07:30:00+00:00 | upbit_krw_listing | CYBERUSDT | SHORT 3x, enter +60m, hold ≤60m, SL 20% | 2025-08-12T08:31:00+00:00 → 2025-08-12T09:31:00+00:00 | -0.396 | -395.93 |
| 2025-08-19T07:30:00+00:00 | upbit_krw_listing | API3USDT | SHORT 2x, enter +30m, hold ≤60m, SL 20% | 2025-08-19T08:01:00+00:00 → 2025-08-19T09:01:00+00:00 | -0.179 | -178.84 |
| 2025-08-22T00:30:00+00:00 | upbit_krw_listing | AEROUSDT | SHORT 2x, enter +30m, hold ≤60m, SL 20% | 2025-08-22T01:01:00+00:00 → 2025-08-22T02:01:00+00:00 | +0.011 | +10.66 |
| 2025-08-28T05:00:00+00:00 | upbit_krw_listing | TREEUSDT | SHORT 2x, enter +30m, hold ≤60m, SL 20% | 2025-08-28T05:31:00+00:00 → 2025-08-28T06:31:00+00:00 | +0.021 | +21.00 |
| 2025-08-29T11:00:12+00:00 | binance_perp_delisting | LEVERUSDT | LONG 5x, enter +5m, hold ≤60m, SL 10% | 2025-08-29T11:07:00+00:00 → 2025-08-29T11:10:00+00:00 | -0.518 | -518.24 |
| 2025-09-01T01:49:05+00:00 | binance_spot_listing | WLFIUSDT | LONG 5x, enter +15m, hold ≤60m, SL 10%, TP 10% | 2025-09-01T02:06:00+00:00 → 2025-09-01T03:06:00+00:00 | +0.303 | +303.49 |
| 2025-09-01T04:09:10+00:00 | upbit_krw_listing | WLFIUSDT | SHORT 2x, enter +30m, hold ≤60m, SL 20% | 2025-09-01T04:41:00+00:00 → 2025-09-01T05:41:00+00:00 | -0.053 | -52.74 |
| 2025-09-03T02:59:54+00:00 | binance_spot_delisting | BAKEUSDT | LONG 5x, enter +0m, hold ≤60m, SL 5%, TP 20% | 2025-09-03T03:01:00+00:00 → 2025-09-03T03:02:00+00:00 | -0.269 | -269.12 |
| 2025-09-03T02:59:54+00:00 | binance_spot_delisting | HIFIUSDT | LONG 5x, enter +0m, hold ≤60m, SL 5%, TP 20% | 2025-09-03T03:01:00+00:00 → 2025-09-03T03:03:00+00:00 | -0.269 | -269.12 |
| 2025-09-05T07:45:00+00:00 | upbit_krw_listing | REDUSDT | SHORT 1x, enter +30m, hold ≤480m, SL 5%, TP 20% | 2025-09-05T08:16:00+00:00 → 2025-09-05T11:03:00+00:00 | -0.054 | -54.18 |
| 2025-09-09T10:21:09+00:00 | upbit_krw_listing | WLDUSDT | SHORT 2x, enter +30m, hold ≤60m, SL 20% | 2025-09-09T10:53:00+00:00 → 2025-09-09T11:53:00+00:00 | +0.006 | +5.82 |
| 2025-09-10T04:22:36+00:00 | upbit_krw_listing | OPENUSDT | SHORT 2x, enter +30m, hold ≤60m, SL 20% | 2025-09-10T04:54:00+00:00 → 2025-09-10T05:54:00+00:00 | +0.096 | +95.98 |
| 2025-09-10T07:40:05+00:00 | upbit_krw_listing | LINEAUSDT | SHORT 2x, enter +30m, hold ≤60m, SL 20% | 2025-09-10T08:12:00+00:00 → 2025-09-10T09:12:00+00:00 | +0.007 | +7.39 |
| 2025-09-10T10:14:43+00:00 | binance_perp_delisting | BSWUSDT | LONG 3x, enter +0m, hold ≤480m, SL 20%, TP 10% | 2025-09-10T10:16:00+00:00 → 2025-09-10T10:17:00+00:00 | +0.292 | +291.90 |
| 2025-09-11T10:15:27+00:00 | upbit_krw_listing | PUMPUSDT | SHORT 2x, enter +30m, hold ≤60m, SL 20% | 2025-09-11T10:47:00+00:00 → 2025-09-11T11:47:00+00:00 | +0.030 | +30.01 |
| 2025-09-11T11:37:53+00:00 | binance_spot_listing | PUMPUSDT | LONG 5x, enter +15m, hold ≤60m, SL 10%, TP 10% | 2025-09-11T11:54:00+00:00 → 2025-09-11T12:54:00+00:00 | -0.129 | -128.73 |
| 2025-09-15T02:30:00+00:00 | upbit_krw_listing | AVNTUSDT | SHORT 2x, enter +30m, hold ≤60m, SL 20% | 2025-09-15T03:01:00+00:00 → 2025-09-15T04:01:00+00:00 | +0.036 | +36.37 |
| 2025-09-15T03:47:01+00:00 | binance_spot_listing | AVNTUSDT | LONG 3x, enter +5m, hold ≤60m, SL 20%, TP 20% | 2025-09-15T03:54:00+00:00 → 2025-09-15T04:31:00+00:00 | +0.600 | +600.29 |
| 2025-09-17T02:30:23+00:00 | upbit_listing | PLUMEUSDT | SHORT 3x, enter +0m, hold ≤1380m, SL 20% | 2025-09-17T02:32:00+00:00 → 2025-09-18T01:32:00+00:00 | +0.024 | +24.42 |
| 2025-09-17T08:45:27+00:00 | binance_perp_delisting | ALPHAUSDT | LONG 3x, enter +0m, hold ≤480m, SL 20%, TP 10% | 2025-09-17T08:47:00+00:00 → 2025-09-17T08:48:00+00:00 | +0.292 | +291.90 |
| 2025-09-18T10:02:31+00:00 | upbit_krw_listing | LAUSDT | SHORT 2x, enter +30m, hold ≤60m, SL 20% | 2025-09-18T10:34:00+00:00 → 2025-09-18T11:34:00+00:00 | +0.230 | +230.47 |
| 2025-09-19T03:10:00+00:00 | upbit_listing | ETHFIUSDT | SHORT 3x, enter +0m, hold ≤1380m, SL 20% | 2025-09-19T03:11:00+00:00 → 2025-09-20T02:11:00+00:00 | +0.317 | +317.45 |
| 2025-09-19T03:10:00+00:00 | upbit_listing | RESOLVUSDT | SHORT 3x, enter +0m, hold ≤1380m, SL 20% | 2025-09-19T03:11:00+00:00 → 2025-09-20T02:11:00+00:00 | +0.332 | +331.62 |
| 2025-09-19T03:10:00+00:00 | upbit_listing | INITUSDT | SHORT 3x, enter +0m, hold ≤1380m, SL 20% | 2025-09-19T03:11:00+00:00 → 2025-09-20T02:11:00+00:00 | +0.268 | +267.68 |
| 2025-09-19T03:10:00+00:00 | upbit_listing | SPKUSDT | SHORT 3x, enter +0m, hold ≤1380m, SL 20% | 2025-09-19T03:11:00+00:00 → 2025-09-20T02:11:00+00:00 | +0.214 | +213.53 |
| 2025-09-22T02:30:00+00:00 | upbit_krw_listing | SUNUSDT | SHORT 3x, enter +30m, hold ≤60m, SL 20% | 2025-09-22T03:01:00+00:00 → 2025-09-22T04:01:00+00:00 | -0.135 | -135.18 |
| 2025-09-22T04:50:00+00:00 | upbit_krw_listing | 0GUSDT | SHORT 3x, enter +30m, hold ≤60m, SL 20% | 2025-09-22T05:21:00+00:00 → 2025-09-22T06:21:00+00:00 | +0.024 | +23.70 |
| 2025-09-22T07:30:02+00:00 | binance_perp_delisting | NEIROETHUSDT | LONG 3x, enter +0m, hold ≤480m, SL 20%, TP 10% | 2025-09-22T07:32:00+00:00 → 2025-09-22T07:57:00+00:00 | -0.610 | -609.90 |
| 2025-09-23T03:00:00+00:00 | upbit_warning | UXLINKUSDT | SHORT 5x, enter +0m, hold ≤480m, SL 10%, TP 20% | 2025-09-23T03:01:00+00:00 → 2025-09-23T03:09:00+00:00 | -0.522 | -521.76 |
| 2025-09-24T12:00:05+00:00 | binance_perp_delisting | UXLINKUSDT | SHORT 2x, enter +30m, hold ≤240m, SL 20% | 2025-09-24T12:32:00+00:00 → 2025-09-24T16:32:00+00:00 | +0.202 | +202.45 |
| 2025-09-25T01:57:18+00:00 | upbit_krw_listing | XPLUSDT | SHORT 3x, enter +30m, hold ≤60m, SL 20% | 2025-09-25T02:29:00+00:00 → 2025-09-25T03:29:00+00:00 | +0.041 | +40.89 |
| 2025-09-29T08:53:51+00:00 | upbit_krw_listing | SUPERUSDT | SHORT 3x, enter +30m, hold ≤60m, SL 20% | 2025-09-29T09:25:00+00:00 → 2025-09-29T10:25:00+00:00 | -0.083 | -82.61 |
| 2025-09-29T08:54:03+00:00 | upbit_listing | ORDERUSDT | SHORT 3x, enter +0m, hold ≤1380m, SL 20% | 2025-09-29T08:56:00+00:00 → 2025-09-30T06:54:00+00:00 | -0.616 | -615.58 |
| 2025-09-29T11:45:19+00:00 | binance_perp_delisting | HIFIUSDT | SHORT 3x, enter +30m, hold ≤240m, SL 20% | 2025-09-29T12:17:00+00:00 → 2025-09-29T16:17:00+00:00 | +0.101 | +101.37 |
| 2025-09-29T11:45:19+00:00 | binance_perp_delisting | BAKEUSDT | SHORT 3x, enter +30m, hold ≤240m, SL 20% | 2025-09-29T12:17:00+00:00 → 2025-09-29T16:17:00+00:00 | +0.445 | +444.75 |
| 2025-10-01T04:26:21+00:00 | upbit_krw_listing | SOMIUSDT | SHORT 2x, enter +30m, hold ≤60m, SL 20% | 2025-10-01T04:58:00+00:00 → 2025-10-01T05:58:00+00:00 | -0.053 | -53.32 |
| 2025-10-02T12:30:00+00:00 | upbit_warning | ZKCUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 10%, TP 20%, trail 10% | 2025-10-02T12:31:00+00:00 → 2025-10-02T13:38:00+00:00 | +0.989 | +989.50 |
| 2025-10-06T07:48:49+00:00 | binance_spot_listing | ASTERUSDT | LONG 5x, enter +15m, hold ≤60m, SL 10% | 2025-10-06T08:05:00+00:00 → 2025-10-06T09:05:00+00:00 | +0.154 | +153.75 |
| 2025-10-07T04:35:00+00:00 | upbit_krw_listing | DOODUSDT | SHORT 2x, enter +30m, hold ≤60m, SL 20% | 2025-10-07T05:06:00+00:00 → 2025-10-07T06:06:00+00:00 | +0.290 | +289.95 |
| 2025-10-10T06:00:00+00:00 | upbit_krw_listing | INUSDT | SHORT 3x, enter +30m, hold ≤60m, SL 20%, TP 20% | 2025-10-10T06:31:00+00:00 → 2025-10-10T06:47:00+00:00 | +0.594 | +593.70 |
| 2025-10-15T05:00:00+00:00 | upbit_krw_listing | YGGUSDT | SHORT 3x, enter +30m, hold ≤60m, SL 20% | 2025-10-15T05:31:00+00:00 → 2025-10-15T06:31:00+00:00 | -0.042 | -41.50 |
| 2025-10-17T02:30:00+00:00 | upbit_krw_listing | ZORAUSDT | SHORT 3x, enter +30m, hold ≤60m, SL 20% | 2025-10-17T03:01:00+00:00 → 2025-10-17T04:01:00+00:00 | -0.097 | -96.64 |
| 2025-10-18T03:58:50+00:00 | binance_perp_delisting | SLERFUSDT | SHORT 3x, enter +30m, hold ≤240m, SL 20% | 2025-10-18T04:30:00+00:00 → 2025-10-18T04:48:00+00:00 | -0.614 | -614.11 |
| 2025-10-20T06:35:00+00:00 | upbit_krw_listing | BIOUSDT | SHORT 3x, enter +30m, hold ≤60m, SL 20% | 2025-10-20T07:06:00+00:00 → 2025-10-20T08:06:00+00:00 | -0.059 | -58.58 |
| 2025-10-24T06:15:00+00:00 | upbit_krw_listing | ORDERUSDT | SHORT 3x, enter +30m, hold ≤60m, SL 20% | 2025-10-24T06:46:00+00:00 → 2025-10-24T07:46:00+00:00 | -0.226 | -226.36 |
| 2025-10-25T03:02:18+00:00 | binance_spot_listing | GIGGLEUSDT | LONG 5x, enter +15m, hold ≤60m, SL 10% | 2025-10-25T03:19:00+00:00 → 2025-10-25T04:19:00+00:00 | +0.469 | +468.84 |
| 2025-10-28T07:00:00+00:00 | upbit_krw_listing | KERNELUSDT | SHORT 3x, enter +30m, hold ≤60m, SL 20% | 2025-10-28T07:31:00+00:00 → 2025-10-28T08:31:00+00:00 | +0.133 | +133.35 |
| 2025-10-29T03:00:04+00:00 | binance_spot_delisting | FLMUSDT | SHORT 5x, enter +15m, hold ≤480m, SL 5%, TP 20%, trail 10% | 2025-10-29T03:17:00+00:00 → 2025-10-29T03:34:00+00:00 | +0.989 | +989.50 |
| 2025-10-29T03:00:04+00:00 | binance_spot_delisting | KDAUSDT | SHORT 5x, enter +15m, hold ≤480m, SL 5%, TP 20%, trail 10% | 2025-10-29T03:17:00+00:00 → 2025-10-29T05:07:00+00:00 | +0.990 | +989.74 |
| 2025-10-29T03:00:04+00:00 | binance_spot_delisting | PERPUSDT | SHORT 5x, enter +15m, hold ≤480m, SL 5%, TP 20%, trail 10% | 2025-10-29T03:17:00+00:00 → 2025-10-29T04:03:00+00:00 | +0.084 | +83.88 |
| 2025-10-29T06:30:56+00:00 | upbit_krw_listing | ENSOUSDT | SHORT 3x, enter +30m, hold ≤60m, SL 20% | 2025-10-29T07:02:00+00:00 → 2025-10-29T08:02:00+00:00 | -0.158 | -157.96 |
| 2025-11-03T08:11:21+00:00 | upbit_krw_listing | KITEUSDT | SHORT 2x, enter +30m, hold ≤60m, SL 20% | 2025-11-03T08:43:00+00:00 → 2025-11-03T09:43:00+00:00 | +0.109 | +108.71 |
| 2025-11-05T05:47:59+00:00 | upbit_krw_listing | MMTUSDT | SHORT 3x, enter +30m, hold ≤60m, SL 20% | 2025-11-05T06:19:00+00:00 → 2025-11-05T07:01:00+00:00 | -0.614 | -614.11 |
| 2025-11-10T13:45:00+00:00 | binance_perp_delisting | MYROUSDT | SHORT 3x, enter +30m, hold ≤60m, SL 10%, TP 20%, trail 10% | 2025-11-10T14:17:00+00:00 → 2025-11-10T15:17:00+00:00 | +0.329 | +328.66 |
| 2025-11-10T13:45:00+00:00 | binance_perp_delisting | 1000XUSDT | SHORT 3x, enter +30m, hold ≤60m, SL 10%, TP 20%, trail 10% | 2025-11-10T14:17:00+00:00 → 2025-11-10T15:17:00+00:00 | +0.099 | +98.75 |
| 2025-11-13T10:00:26+00:00 | binance_spot_listing | BANKUSDT | LONG 5x, enter +15m, hold ≤60m, SL 10%, TP 20% | 2025-11-13T10:17:00+00:00 → 2025-11-13T10:27:00+00:00 | -0.518 | -518.24 |
| 2025-11-13T10:00:26+00:00 | binance_spot_listing | METUSDT | LONG 5x, enter +15m, hold ≤60m, SL 10%, TP 20% | 2025-11-13T10:17:00+00:00 → 2025-11-13T11:17:00+00:00 | -0.166 | -165.58 |
| 2025-11-23T05:57:34+00:00 | binance_perp_delisting | PORT3USDT | SHORT 3x, enter +30m, hold ≤60m, SL 10%, TP 20%, trail 10% | 2025-11-23T06:29:00+00:00 → 2025-11-23T07:29:00+00:00 | -0.082 | -82.39 |
| 2025-11-24T09:01:33+00:00 | upbit_krw_listing | MONUSDT | SHORT 2x, enter +30m, hold ≤60m, SL 35% | 2025-11-24T09:33:00+00:00 → 2025-11-24T10:33:00+00:00 | +0.040 | +39.88 |
| 2025-11-26T05:30:02+00:00 | upbit_krw_listing | PLUMEUSDT | SHORT 2x, enter +30m, hold ≤60m, SL 35% | 2025-11-26T06:02:00+00:00 → 2025-11-26T07:02:00+00:00 | -0.052 | -51.55 |
| 2025-12-01T04:30:24+00:00 | binance_monitoring_tag | CHESSUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 5% | 2025-12-01T04:32:00+00:00 → 2025-12-01T11:51:00+00:00 | -0.271 | -270.64 |
| 2025-12-01T04:30:24+00:00 | binance_monitoring_tag | DENTUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 5% | 2025-12-01T04:32:00+00:00 → 2025-12-02T03:32:00+00:00 | +0.653 | +652.83 |
| 2025-12-01T04:30:24+00:00 | binance_monitoring_tag | DFUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 5% | 2025-12-01T04:32:00+00:00 → 2025-12-02T03:32:00+00:00 | +0.244 | +243.52 |
| 2025-12-01T04:30:24+00:00 | binance_monitoring_tag | GHSTUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 5% | 2025-12-01T04:32:00+00:00 → 2025-12-01T13:49:00+00:00 | -0.271 | -270.62 |
| 2025-12-01T04:30:24+00:00 | binance_monitoring_tag | SXPUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 5% | 2025-12-01T04:32:00+00:00 → 2025-12-02T03:32:00+00:00 | +0.956 | +955.85 |
| 2025-12-03T06:29:56+00:00 | binance_spot_delisting | FISUSDT | SHORT 5x, enter +15m, hold ≤480m, SL 5%, TP 20%, trail 10% | 2025-12-03T06:46:00+00:00 → 2025-12-03T11:29:00+00:00 | +0.332 | +332.17 |
| 2025-12-03T06:29:56+00:00 | binance_spot_delisting | REIUSDT | SHORT 5x, enter +15m, hold ≤480m, SL 5%, TP 20%, trail 10% | 2025-12-03T06:46:00+00:00 → 2025-12-03T12:44:00+00:00 | -0.047 | -46.97 |
| 2025-12-03T06:29:56+00:00 | binance_spot_delisting | VOXELUSDT | SHORT 5x, enter +15m, hold ≤480m, SL 5%, TP 20%, trail 10% | 2025-12-03T06:46:00+00:00 → 2025-12-03T09:52:00+00:00 | +0.057 | +56.84 |
| 2025-12-11T11:43:46+00:00 | binance_perp_delisting | AIAUSDT | SHORT 3x, enter +30m, hold ≤60m, SL 10%, TP 20%, trail 10% | 2025-12-11T12:15:00+00:00 → 2025-12-11T12:16:00+00:00 | -0.313 | -313.05 |
| 2025-12-15T07:00:00+00:00 | upbit_krw_listing | WETUSDT | SHORT 2x, enter +30m, hold ≤60m, SL 35% | 2025-12-15T07:31:00+00:00 → 2025-12-15T08:31:00+00:00 | -0.194 | -193.59 |
| 2025-12-26T04:15:00+00:00 | upbit_listing | YBUSDT | SHORT 3x, enter +0m, hold ≤1380m, SL 20% | 2025-12-26T04:16:00+00:00 → 2025-12-27T03:16:00+00:00 | +0.176 | +175.55 |
| 2025-12-26T06:19:43+00:00 | upbit_krw_listing | ZKPUSDT | SHORT 2x, enter +30m, hold ≤60m, SL 35% | 2025-12-26T06:51:00+00:00 → 2025-12-26T07:51:00+00:00 | -0.101 | -101.04 |
| 2025-12-29T05:00:00+00:00 | upbit_warning | FLOWUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 10%, TP 20%, trail 10% | 2025-12-29T05:01:00+00:00 → 2025-12-30T04:01:00+00:00 | +0.269 | +268.80 |
| 2026-01-02T10:59:57+00:00 | binance_monitoring_tag | FLOWUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 5% | 2026-01-02T11:01:00+00:00 → 2026-01-02T19:48:00+00:00 | -0.286 | -286.01 |
| 2026-01-06T07:30:15+00:00 | upbit_krw_listing | ZKUSDT | SHORT 2x, enter +30m, hold ≤60m, SL 35% | 2026-01-06T08:02:00+00:00 → 2026-01-06T09:02:00+00:00 | -0.092 | -92.41 |
| 2026-01-07T02:20:01+00:00 | upbit_krw_listing | BREVUSDT | SHORT 2x, enter +30m, hold ≤60m, SL 35% | 2026-01-07T02:52:00+00:00 → 2026-01-07T03:52:00+00:00 | -0.103 | -103.26 |
| 2026-01-07T10:39:06+00:00 | binance_spot_listing | ZKPUSDT | LONG 3x, enter +15m, hold ≤60m, SL 10%, TP 20% | 2026-01-07T10:56:00+00:00 → 2026-01-07T11:56:00+00:00 | +0.054 | +53.77 |
| 2026-01-12T12:50:53+00:00 | binance_spot_listing | FOGOUSDT | LONG 2x, enter +0m, hold ≤480m, SL 5% | 2026-01-12T12:52:00+00:00 → 2026-01-12T12:57:00+00:00 | -0.108 | -107.65 |
| 2026-01-22T05:25:54+00:00 | binance_spot_listing | SENTUSDT | LONG 2x, enter +0m, hold ≤480m, SL 5% | 2026-01-22T05:27:00+00:00 → 2026-01-22T05:30:00+00:00 | -0.108 | -107.65 |
| 2026-01-26T11:00:00+00:00 | upbit_warning | SXPUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 10%, TP 20%, trail 10% | 2026-01-26T11:01:00+00:00 → 2026-01-27T10:01:00+00:00 | -0.020 | -20.03 |
| 2026-01-29T06:15:07+00:00 | upbit_krw_listing | SENTUSDT | SHORT 1x, enter +30m, hold ≤60m, SL 35% | 2026-01-29T06:47:00+00:00 → 2026-01-29T07:47:00+00:00 | +0.009 | +9.44 |
| 2026-01-30T05:00:00+00:00 | upbit_warning | LRCUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 10%, TP 20%, trail 10% | 2026-01-30T05:01:00+00:00 → 2026-01-31T04:01:00+00:00 | +0.007 | +7.13 |
| 2026-02-02T04:28:43+00:00 | binance_spot_listing | ZAMAUSDT | LONG 2x, enter +5m, hold ≤480m, SL 10% | 2026-02-02T04:35:00+00:00 → 2026-02-02T11:42:00+00:00 | -0.207 | -207.39 |
| 2026-02-02T08:59:52+00:00 | binance_spot_delisting | CHESSUSDT | SHORT 5x, enter +15m, hold ≤240m, SL 5%, TP 20%, trail 10% | 2026-02-02T09:16:00+00:00 → 2026-02-02T10:25:00+00:00 | +0.497 | +496.53 |
| 2026-02-02T08:59:52+00:00 | binance_spot_delisting | DFUSDT | SHORT 5x, enter +15m, hold ≤240m, SL 5%, TP 20%, trail 10% | 2026-02-02T09:16:00+00:00 → 2026-02-02T09:23:00+00:00 | -0.271 | -270.88 |
| 2026-02-02T08:59:52+00:00 | binance_spot_delisting | GHSTUSDT | SHORT 5x, enter +15m, hold ≤240m, SL 5%, TP 20%, trail 10% | 2026-02-02T09:16:00+00:00 → 2026-02-02T10:33:00+00:00 | -0.043 | -42.60 |
| 2026-02-02T08:59:52+00:00 | binance_spot_delisting | NKNUSDT | SHORT 5x, enter +15m, hold ≤240m, SL 5%, TP 20%, trail 10% | 2026-02-02T09:16:00+00:00 → 2026-02-02T12:01:00+00:00 | +0.250 | +250.32 |
| 2026-02-03T07:00:00+00:00 | upbit_krw_listing | BIRBUSDT | SHORT 1x, enter +30m, hold ≤60m, SL 35% | 2026-02-03T07:31:00+00:00 → 2026-02-03T08:31:00+00:00 | +0.062 | +62.49 |
| 2026-02-05T07:14:19+00:00 | binance_perp_delisting | RVVUSDT | SHORT 2x, enter +5m, hold ≤240m, SL 20% | 2026-02-05T07:21:00+00:00 → 2026-02-05T11:21:00+00:00 | +0.198 | +198.25 |
| 2026-02-05T07:14:19+00:00 | binance_perp_delisting | YALAUSDT | SHORT 2x, enter +5m, hold ≤240m, SL 20% | 2026-02-05T07:21:00+00:00 → 2026-02-05T11:21:00+00:00 | +0.428 | +428.43 |
| 2026-02-10T04:30:00+00:00 | upbit_warning | DENTUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 10%, TP 20%, trail 10% | 2026-02-10T04:31:00+00:00 → 2026-02-11T03:31:00+00:00 | +0.085 | +85.26 |
| 2026-02-12T07:00:31+00:00 | upbit_warning | NOMUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 10%, TP 20%, trail 10% | 2026-02-12T07:02:00+00:00 → 2026-02-13T06:02:00+00:00 | +0.801 | +801.37 |
| 2026-02-12T07:28:23+00:00 | binance_spot_listing | ESPUSDT | LONG 1x, enter +5m, hold ≤480m, SL 10% | 2026-02-12T07:35:00+00:00 → 2026-02-12T11:37:00+00:00 | -0.104 | -103.70 |
| 2026-02-12T09:00:04+00:00 | upbit_delisting | FLOWUSDT | SHORT 5x, enter +15m, hold ≤240m, SL 5% | 2026-02-12T09:17:00+00:00 → 2026-02-12T09:18:00+00:00 | -0.271 | -270.88 |
| 2026-02-13T05:00:00+00:00 | upbit_delisting | LRCUSDT | SHORT 5x, enter +15m, hold ≤240m, SL 5% | 2026-02-13T05:16:00+00:00 → 2026-02-13T09:16:00+00:00 | +0.271 | +270.63 |
| 2026-02-16T05:00:00+00:00 | upbit_krw_listing | TAOUSDT | SHORT 2x, enter +30m, hold ≤60m, SL 35% | 2026-02-16T05:31:00+00:00 → 2026-02-16T06:31:00+00:00 | +0.034 | +33.52 |
| 2026-02-20T05:00:00+00:00 | upbit_krw_listing | AZTECUSDT | SHORT 2x, enter +30m, hold ≤60m, SL 35% | 2026-02-20T05:31:00+00:00 → 2026-02-20T06:31:00+00:00 | +0.036 | +36.28 |
| 2026-02-23T06:30:00+00:00 | upbit_warning | IOTXUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 10%, TP 20%, trail 10% | 2026-02-23T06:31:00+00:00 → 2026-02-23T10:02:00+00:00 | -0.419 | -418.55 |
| 2026-02-24T05:00:00+00:00 | upbit_krw_listing | SKRUSDT | SHORT 2x, enter +30m, hold ≤60m, SL 35% | 2026-02-24T05:31:00+00:00 → 2026-02-24T06:31:00+00:00 | +0.074 | +73.82 |
| 2026-02-24T06:04:04+00:00 | upbit_krw_listing | ESPUSDT | SHORT 2x, enter +30m, hold ≤60m, SL 35% | 2026-02-24T06:36:00+00:00 → 2026-02-24T07:36:00+00:00 | -0.170 | -170.00 |
| 2026-02-26T06:00:00+00:00 | upbit_delisting | DENTUSDT | SHORT 5x, enter +5m, hold ≤240m, SL 5%, TP 10% | 2026-02-26T06:06:00+00:00 → 2026-02-26T06:25:00+00:00 | -0.271 | -270.88 |
| 2026-02-27T06:00:00+00:00 | upbit_delisting | NOMUSDT | LONG 2x, enter +60m, hold ≤480m, SL 5% | 2026-02-27T07:01:00+00:00 → 2026-02-27T15:01:00+00:00 | -0.036 | -35.66 |
| 2026-03-04T13:13:14+00:00 | binance_spot_listing | ROBOUSDT | LONG 1x, enter +5m, hold ≤480m, SL 10% | 2026-03-04T13:20:00+00:00 → 2026-03-04T16:48:00+00:00 | -0.100 | -99.83 |
| 2026-03-06T08:29:56+00:00 | binance_monitoring_tag | COSUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 5% | 2026-03-06T08:31:00+00:00 → 2026-03-07T07:31:00+00:00 | +0.625 | +624.56 |
| 2026-03-06T08:29:56+00:00 | binance_monitoring_tag | DEGOUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 5% | 2026-03-06T08:31:00+00:00 → 2026-03-07T07:31:00+00:00 | +0.401 | +401.47 |
| 2026-03-06T08:29:56+00:00 | binance_monitoring_tag | FORTHUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 5% | 2026-03-06T08:31:00+00:00 → 2026-03-07T07:31:00+00:00 | +0.538 | +538.00 |
| 2026-03-06T08:29:56+00:00 | binance_monitoring_tag | FUNUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 5% | 2026-03-06T08:31:00+00:00 → 2026-03-07T07:31:00+00:00 | +0.676 | +676.30 |
| 2026-03-06T08:29:56+00:00 | binance_monitoring_tag | HOOKUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 5% | 2026-03-06T08:31:00+00:00 → 2026-03-07T07:31:00+00:00 | +0.719 | +718.89 |
| 2026-03-06T08:29:56+00:00 | binance_monitoring_tag | LRCUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 5% | 2026-03-06T08:31:00+00:00 → 2026-03-07T03:18:00+00:00 | -0.270 | -270.01 |
| 2026-03-06T08:29:56+00:00 | binance_monitoring_tag | MBOXUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 5% | 2026-03-06T08:31:00+00:00 → 2026-03-07T07:31:00+00:00 | +0.715 | +714.94 |
| 2026-03-06T08:29:56+00:00 | binance_monitoring_tag | OXTUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 5% | 2026-03-06T08:31:00+00:00 → 2026-03-07T07:31:00+00:00 | +0.426 | +426.47 |
| 2026-03-06T08:29:56+00:00 | binance_monitoring_tag | WIFUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 5% | 2026-03-06T08:31:00+00:00 → 2026-03-07T07:31:00+00:00 | +0.603 | +602.77 |
| 2026-03-11T06:00:00+00:00 | upbit_krw_listing | ICPUSDT | SHORT 2x, enter +30m, hold ≤60m, SL 35% | 2026-03-11T06:31:00+00:00 → 2026-03-11T07:31:00+00:00 | -0.016 | -15.74 |
| 2026-03-13T01:45:36+00:00 | binance_spot_listing | KATUSDT | LONG 1x, enter +0m, hold ≤480m, SL 5% | 2026-03-13T01:47:00+00:00 → 2026-03-13T09:47:00+00:00 | +0.041 | +40.75 |
| 2026-03-13T09:00:23+00:00 | binance_monitoring_tag | ATAUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 5% | 2026-03-13T09:02:00+00:00 → 2026-03-13T12:16:00+00:00 | -0.271 | -270.88 |
| 2026-03-13T09:00:23+00:00 | binance_monitoring_tag | A2ZUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 5% | 2026-03-13T09:02:00+00:00 → 2026-03-14T08:02:00+00:00 | +0.305 | +304.85 |
| 2026-03-13T09:00:23+00:00 | binance_monitoring_tag | FIOUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 5% | 2026-03-13T09:02:00+00:00 → 2026-03-14T08:02:00+00:00 | +0.544 | +543.92 |
| 2026-03-13T09:00:23+00:00 | binance_monitoring_tag | GTCUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 5% | 2026-03-13T09:02:00+00:00 → 2026-03-13T12:14:00+00:00 | -0.271 | -270.88 |
| 2026-03-13T09:00:23+00:00 | binance_monitoring_tag | NTRNUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 5% | 2026-03-13T09:02:00+00:00 → 2026-03-14T08:02:00+00:00 | +0.575 | +574.52 |
| 2026-03-13T09:00:23+00:00 | binance_monitoring_tag | PHBUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 5% | 2026-03-13T09:02:00+00:00 → 2026-03-14T08:02:00+00:00 | +0.304 | +304.09 |
| 2026-03-13T09:00:23+00:00 | binance_monitoring_tag | RDNTUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 5% | 2026-03-13T09:02:00+00:00 → 2026-03-14T08:02:00+00:00 | +0.053 | +52.61 |
| 2026-03-18T09:00:08+00:00 | binance_spot_delisting | A2ZUSDT | SHORT 5x, enter +15m, hold ≤240m, SL 5%, TP 20% | 2026-03-18T09:17:00+00:00 → 2026-03-18T09:20:00+00:00 | -0.271 | -270.88 |
| 2026-03-18T09:00:08+00:00 | binance_spot_delisting | FORTHUSDT | SHORT 5x, enter +15m, hold ≤240m, SL 5%, TP 20% | 2026-03-18T09:17:00+00:00 → 2026-03-18T09:27:00+00:00 | -0.271 | -270.88 |
| 2026-03-18T09:00:08+00:00 | binance_spot_delisting | HOOKUSDT | SHORT 5x, enter +15m, hold ≤240m, SL 5%, TP 20% | 2026-03-18T09:17:00+00:00 → 2026-03-18T13:17:00+00:00 | +0.481 | +481.45 |
| 2026-03-18T09:00:08+00:00 | binance_spot_delisting | IDEXUSDT | SHORT 5x, enter +15m, hold ≤240m, SL 5%, TP 20% | 2026-03-18T09:17:00+00:00 → 2026-03-18T13:17:00+00:00 | -0.020 | -20.03 |
| 2026-03-18T09:00:08+00:00 | binance_spot_delisting | LRCUSDT | SHORT 5x, enter +15m, hold ≤240m, SL 5%, TP 20% | 2026-03-18T09:17:00+00:00 → 2026-03-18T09:31:00+00:00 | -0.271 | -270.88 |
| 2026-03-18T09:00:08+00:00 | binance_spot_delisting | NTRNUSDT | SHORT 5x, enter +15m, hold ≤240m, SL 5%, TP 20% | 2026-03-18T09:17:00+00:00 → 2026-03-18T13:17:00+00:00 | +0.342 | +341.61 |
| 2026-03-18T09:00:08+00:00 | binance_spot_delisting | RDNTUSDT | SHORT 5x, enter +15m, hold ≤240m, SL 5%, TP 20% | 2026-03-18T09:17:00+00:00 → 2026-03-18T09:43:00+00:00 | -0.271 | -270.88 |
| 2026-03-18T09:00:08+00:00 | binance_spot_delisting | SXPUSDT | SHORT 5x, enter +15m, hold ≤240m, SL 5%, TP 20% | 2026-03-18T09:17:00+00:00 → 2026-03-18T13:17:00+00:00 | -0.020 | -20.03 |
| 2026-03-19T02:50:00+00:00 | upbit_krw_listing | ETHFIUSDT | SHORT 1x, enter +30m, hold ≤60m, SL 35% | 2026-03-19T03:21:00+00:00 → 2026-03-19T04:21:00+00:00 | +0.030 | +29.71 |
| 2026-03-23T06:00:00+00:00 | upbit_warning | RESOLVUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 10%, TP 20%, trail 10% | 2026-03-23T06:01:00+00:00 → 2026-03-24T05:01:00+00:00 | +0.451 | +451.03 |
| 2026-03-26T08:07:50+00:00 | upbit_krw_listing | KATUSDT | SHORT 2x, enter +30m, hold ≤60m, SL 35% | 2026-03-26T08:39:00+00:00 → 2026-03-26T09:39:00+00:00 | +0.020 | +19.72 |
| 2026-03-31T02:30:01+00:00 | upbit_krw_listing | SKYUSDT | SHORT 2x, enter +30m, hold ≤60m, SL 35% | 2026-03-31T03:02:00+00:00 → 2026-03-31T04:02:00+00:00 | +0.018 | +18.19 |
| 2026-04-02T05:00:00+00:00 | upbit_warning | DRIFTUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 10%, TP 20%, trail 10% | 2026-04-02T05:01:00+00:00 → 2026-04-02T06:06:00+00:00 | -0.508 | -507.81 |
| 2026-04-09T06:00:05+00:00 | binance_spot_delisting | FIOUSDT | SHORT 3x, enter +15m, hold ≤480m, SL 20%, TP 10% | 2026-04-09T06:17:00+00:00 → 2026-04-09T14:17:00+00:00 | +0.072 | +72.48 |
| 2026-04-09T06:00:05+00:00 | binance_spot_delisting | FUNUSDT | SHORT 3x, enter +15m, hold ≤480m, SL 20%, TP 10% | 2026-04-09T06:17:00+00:00 → 2026-04-09T07:55:00+00:00 | +0.293 | +293.10 |
| 2026-04-09T06:00:05+00:00 | binance_spot_delisting | MDTUSDT | SHORT 3x, enter +15m, hold ≤480m, SL 20%, TP 10% | 2026-04-09T06:17:00+00:00 → 2026-04-09T14:17:00+00:00 | -0.012 | -12.02 |
| 2026-04-09T06:00:05+00:00 | binance_spot_delisting | OXTUSDT | SHORT 3x, enter +15m, hold ≤480m, SL 20%, TP 10% | 2026-04-09T06:17:00+00:00 → 2026-04-09T09:19:00+00:00 | +0.287 | +287.24 |
| 2026-04-13T09:00:01+00:00 | upbit_warning | DOTUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 5%, TP 20%, trail 10% | 2026-04-13T09:02:00+00:00 → 2026-04-14T08:02:00+00:00 | -0.051 | -51.05 |
| 2026-04-14T02:30:06+00:00 | binance_monitoring_tag | HIGHUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 5% | 2026-04-14T02:32:00+00:00 → 2026-04-15T01:32:00+00:00 | +0.106 | +106.25 |
| 2026-04-14T02:30:06+00:00 | binance_monitoring_tag | MLNUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 5% | 2026-04-14T02:32:00+00:00 → 2026-04-14T02:33:00+00:00 | -0.271 | -270.88 |
| 2026-04-14T02:30:06+00:00 | binance_monitoring_tag | RESOLVUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 5% | 2026-04-14T02:32:00+00:00 → 2026-04-14T02:41:00+00:00 | -0.271 | -270.88 |
| 2026-04-14T02:30:06+00:00 | binance_monitoring_tag | SYSUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 5% | 2026-04-14T02:32:00+00:00 → 2026-04-14T02:39:00+00:00 | -0.271 | -270.88 |
| 2026-04-14T02:30:06+00:00 | binance_monitoring_tag | TRUUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 5% | 2026-04-14T02:32:00+00:00 → 2026-04-14T03:34:00+00:00 | -0.271 | -270.88 |
| 2026-04-14T02:30:06+00:00 | binance_monitoring_tag | VELODROMEUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 5% | 2026-04-14T02:32:00+00:00 → 2026-04-14T02:41:00+00:00 | -0.271 | -270.88 |
| 2026-04-14T05:00:00+00:00 | upbit_krw_listing | CCUSDT | SHORT 2x, enter +30m, hold ≤60m, SL 35% | 2026-04-14T05:31:00+00:00 → 2026-04-14T06:31:00+00:00 | -0.022 | -21.66 |
| 2026-04-14T07:48:40+00:00 | upbit_krw_listing | ZAMAUSDT | SHORT 2x, enter +30m, hold ≤60m, SL 35% | 2026-04-14T08:20:00+00:00 → 2026-04-14T09:20:00+00:00 | -0.058 | -57.74 |
| 2026-04-17T05:00:02+00:00 | upbit_krw_listing | SOONUSDT | SHORT 1x, enter +30m, hold ≤60m, SL 35% | 2026-04-17T05:32:00+00:00 → 2026-04-17T06:32:00+00:00 | +0.009 | +9.30 |
| 2026-04-17T09:00:06+00:00 | binance_spot_delisting | DEGOUSDT | SHORT 3x, enter +15m, hold ≤480m, SL 20%, TP 10% | 2026-04-17T09:17:00+00:00 → 2026-04-17T10:27:00+00:00 | +0.293 | +293.10 |
| 2026-04-17T09:00:06+00:00 | binance_spot_delisting | DENTUSDT | SHORT 3x, enter +15m, hold ≤480m, SL 20%, TP 10% | 2026-04-17T09:17:00+00:00 → 2026-04-17T10:04:00+00:00 | +0.293 | +293.10 |
| 2026-04-17T09:00:06+00:00 | binance_spot_delisting | TRUUSDT | SHORT 3x, enter +15m, hold ≤480m, SL 20%, TP 10% | 2026-04-17T09:17:00+00:00 → 2026-04-17T15:36:00+00:00 | +0.293 | +293.10 |
| 2026-04-20T05:00:00+00:00 | upbit_krw_listing | PIEVERSEUSDT | SHORT 2x, enter +30m, hold ≤60m, SL 35% | 2026-04-20T05:31:00+00:00 → 2026-04-20T06:31:00+00:00 | +0.511 | +510.61 |
| 2026-04-20T08:00:00+00:00 | upbit_warning | KERNELUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 5%, TP 20%, trail 10% | 2026-04-20T08:01:00+00:00 → 2026-04-20T20:10:00+00:00 | +0.183 | +182.79 |
| 2026-04-21T06:16:24+00:00 | upbit_krw_listing | CHIPUSDT | SHORT 2x, enter +30m, hold ≤60m, SL 35% | 2026-04-21T06:48:00+00:00 → 2026-04-21T07:48:00+00:00 | -0.348 | -347.70 |
| 2026-04-21T12:00:32+00:00 | binance_spot_listing | CHIPUSDT | LONG 1x, enter +0m, hold ≤480m, SL 5% | 2026-04-21T12:02:00+00:00 → 2026-04-21T20:02:00+00:00 | +0.400 | +400.24 |
| 2026-04-23T02:20:00+00:00 | upbit_krw_listing | SPKUSDT | SHORT 1x, enter +30m, hold ≤60m, SL 35% | 2026-04-23T02:51:00+00:00 → 2026-04-23T03:51:00+00:00 | -0.226 | -226.45 |
| 2026-04-24T08:00:00+00:00 | upbit_delisting | RESOLVUSDT | LONG 1x, enter +60m, hold ≤480m, SL 5% | 2026-04-24T09:01:00+00:00 → 2026-04-24T13:50:00+00:00 | -0.054 | -53.87 |
| 2026-04-27T05:00:00+00:00 | upbit_krw_listing | XCNUSDT | LONG 1x, enter +5m, hold ≤240m, SL 20%, TP 10% | 2026-04-27T05:06:00+00:00 → 2026-04-27T09:06:00+00:00 | -0.004 | -3.99 |
| 2026-04-27T06:30:00+00:00 | upbit_krw_listing | PRLUSDT | LONG 1x, enter +5m, hold ≤240m, SL 20%, TP 10% | 2026-04-27T06:36:00+00:00 → 2026-04-27T08:26:00+00:00 | -0.186 | -186.40 |
| 2026-04-30T02:30:06+00:00 | upbit_krw_listing | MEGAUSDT | SHORT 1x, enter +30m, hold ≤60m, SL 35% | 2026-04-30T03:02:00+00:00 → 2026-04-30T04:02:00+00:00 | -0.039 | -38.56 |
| 2026-04-30T07:00:05+00:00 | binance_monitoring_tag | NFPUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 5% | 2026-04-30T07:02:00+00:00 → 2026-05-01T06:02:00+00:00 | +0.111 | +111.47 |
| 2026-04-30T07:00:05+00:00 | binance_monitoring_tag | NOMUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 5% | 2026-04-30T07:02:00+00:00 → 2026-05-01T06:02:00+00:00 | +0.154 | +153.66 |
| 2026-04-30T07:00:05+00:00 | binance_monitoring_tag | QUICKUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 5% | 2026-04-30T07:02:00+00:00 → 2026-05-01T06:02:00+00:00 | -0.020 | -20.03 |
| 2026-04-30T07:00:05+00:00 | binance_monitoring_tag | VICUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 5% | 2026-04-30T07:02:00+00:00 → 2026-05-01T06:02:00+00:00 | +0.254 | +254.32 |
| 2026-04-30T07:50:00+00:00 | upbit_warning | NKNUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 5%, TP 20%, trail 10% | 2026-04-30T07:51:00+00:00 → 2026-05-01T06:51:00+00:00 | -0.020 | -20.03 |
| 2026-04-30T09:07:29+00:00 | binance_spot_listing | MEGAUSDT | LONG 2x, enter +0m, hold ≤480m, SL 5% | 2026-04-30T09:09:00+00:00 → 2026-04-30T09:35:00+00:00 | -0.108 | -107.65 |
| 2026-05-06T05:00:00+00:00 | upbit_krw_listing | WIFUSDT | SHORT 1x, enter +30m, hold ≤60m, SL 35% | 2026-05-06T05:31:00+00:00 → 2026-05-06T06:31:00+00:00 | +0.001 | +1.47 |
| 2026-05-07T03:50:00+00:00 | upbit_krw_listing | B3USDT | SHORT 1x, enter +30m, hold ≤60m, SL 35% | 2026-05-07T04:21:00+00:00 → 2026-05-07T05:21:00+00:00 | -0.004 | -4.01 |
| 2026-05-12T05:00:00+00:00 | upbit_krw_listing | VVVUSDT | SHORT 1x, enter +30m, hold ≤60m, SL 35% | 2026-05-12T05:31:00+00:00 → 2026-05-12T06:31:00+00:00 | +0.023 | +23.42 |
| 2026-05-12T06:00:00+00:00 | upbit_warning | OXTUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 5%, TP 20%, trail 10% | 2026-05-12T06:01:00+00:00 → 2026-05-13T05:01:00+00:00 | -0.020 | -20.03 |
| 2026-05-13T08:00:04+00:00 | binance_spot_delisting | ATAUSDT | SHORT 5x, enter +30m, hold ≤480m, SL 10%, TP 20%, trail 10% | 2026-05-13T08:32:00+00:00 → 2026-05-13T09:48:00+00:00 | +0.989 | +989.50 |
| 2026-05-13T08:00:04+00:00 | binance_spot_delisting | MLNUSDT | SHORT 5x, enter +30m, hold ≤480m, SL 10%, TP 20%, trail 10% | 2026-05-13T08:32:00+00:00 → 2026-05-13T11:32:00+00:00 | +0.326 | +326.24 |
| 2026-05-13T08:00:04+00:00 | binance_spot_delisting | PHBUSDT | SHORT 5x, enter +30m, hold ≤480m, SL 10%, TP 20%, trail 10% | 2026-05-13T08:32:00+00:00 → 2026-05-13T15:06:00+00:00 | +0.989 | +989.50 |
| 2026-05-13T08:00:04+00:00 | binance_spot_delisting | SYSUSDT | SHORT 5x, enter +30m, hold ≤480m, SL 10%, TP 20%, trail 10% | 2026-05-13T08:32:00+00:00 → 2026-05-13T14:46:00+00:00 | +0.990 | +989.71 |
| 2026-05-14T06:00:00+00:00 | upbit_delisting | NKNUSDT | LONG 2x, enter +60m, hold ≤480m, SL 5% | 2026-05-14T07:01:00+00:00 → 2026-05-14T15:01:00+00:00 | -0.008 | -7.99 |
| 2026-05-14T10:00:03+00:00 | binance_spot_listing | AIGENSYNUSDT | LONG 2x, enter +0m, hold ≤480m, SL 5% | 2026-05-14T10:02:00+00:00 → 2026-05-14T18:02:00+00:00 | +0.394 | +393.71 |
| 2026-05-15T08:41:07+00:00 | upbit_krw_listing | IRYSUSDT | SHORT 1x, enter +30m, hold ≤60m, SL 35% | 2026-05-15T09:13:00+00:00 → 2026-05-15T10:13:00+00:00 | -0.033 | -33.43 |
| 2026-05-22T07:18:35+00:00 | binance_spot_listing | GENIUSUSDT | LONG 2x, enter +0m, hold ≤480m, SL 5% | 2026-05-22T07:20:00+00:00 → 2026-05-22T07:21:00+00:00 | -0.108 | -107.65 |
| 2026-05-22T07:18:35+00:00 | binance_spot_listing | OPGUSDT | LONG 2x, enter +0m, hold ≤480m, SL 5% | 2026-05-22T07:20:00+00:00 → 2026-05-22T08:46:00+00:00 | -0.108 | -107.75 |
| 2026-05-22T08:00:04+00:00 | binance_monitoring_tag | COOKIEUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 5% | 2026-05-22T08:02:00+00:00 → 2026-05-23T07:02:00+00:00 | +0.766 | +766.04 |
| 2026-05-22T08:00:04+00:00 | binance_monitoring_tag | EPICUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 5% | 2026-05-22T08:02:00+00:00 → 2026-05-23T07:02:00+00:00 | +0.706 | +705.85 |
| 2026-05-22T08:00:04+00:00 | binance_monitoring_tag | HEIUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 5% | 2026-05-22T08:02:00+00:00 → 2026-05-23T07:02:00+00:00 | +0.209 | +209.18 |
| 2026-05-22T08:00:04+00:00 | binance_monitoring_tag | HFTUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 5% | 2026-05-22T08:02:00+00:00 → 2026-05-23T07:02:00+00:00 | +0.343 | +342.51 |
| 2026-05-22T08:00:04+00:00 | binance_monitoring_tag | STORJUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 5% | 2026-05-22T08:02:00+00:00 → 2026-05-23T07:02:00+00:00 | +0.190 | +190.24 |
| 2026-05-22T08:00:04+00:00 | binance_monitoring_tag | SYNUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 5% | 2026-05-22T08:02:00+00:00 → 2026-05-23T07:02:00+00:00 | +0.170 | +170.39 |
| 2026-05-22T08:00:04+00:00 | binance_monitoring_tag | TLMUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 5% | 2026-05-22T08:02:00+00:00 → 2026-05-23T07:02:00+00:00 | +0.464 | +463.99 |
| 2026-05-29T07:30:00+00:00 | upbit_delisting | OXTUSDT | LONG 2x, enter +60m, hold ≤480m, SL 5% | 2026-05-29T08:31:00+00:00 → 2026-05-29T16:31:00+00:00 | -0.008 | -7.99 |
| 2026-06-05T07:00:07+00:00 | binance_spot_delisting | COSUSDT | SHORT 5x, enter +30m, hold ≤480m, SL 10%, TP 20%, trail 10% | 2026-06-05T07:32:00+00:00 → 2026-06-05T15:32:00+00:00 | +0.685 | +684.89 |
| 2026-06-05T07:00:07+00:00 | binance_spot_delisting | HIGHUSDT | SHORT 5x, enter +30m, hold ≤480m, SL 10%, TP 20%, trail 10% | 2026-06-05T07:32:00+00:00 → 2026-06-05T15:32:00+00:00 | +0.547 | +547.02 |
| 2026-06-05T07:00:07+00:00 | binance_spot_delisting | MBOXUSDT | SHORT 5x, enter +30m, hold ≤480m, SL 10%, TP 20%, trail 10% | 2026-06-05T07:32:00+00:00 → 2026-06-05T15:32:00+00:00 | +0.457 | +456.79 |
| 2026-06-05T09:30:00+00:00 | upbit_krw_listing | BABYUSDT | SHORT 1x, enter +30m, hold ≤60m, SL 35% | 2026-06-05T10:01:00+00:00 → 2026-06-05T11:01:00+00:00 | -0.188 | -187.58 |
| 2026-06-09T02:30:02+00:00 | upbit_listing | CTRUSDT | SHORT 3x, enter +0m, hold ≤1380m, SL 20% | 2026-06-09T02:32:00+00:00 → 2026-06-10T01:32:00+00:00 | +0.250 | +249.85 |
| 2026-06-15T09:30:02+00:00 | upbit_listing | OPGUSDT | SHORT 3x, enter +0m, hold ≤1380m, SL 20% | 2026-06-15T09:32:00+00:00 → 2026-06-16T08:32:00+00:00 | +0.544 | +544.12 |
| 2026-06-18T07:00:18+00:00 | binance_monitoring_tag | ACTUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 5% | 2026-06-18T07:02:00+00:00 → 2026-06-18T07:59:00+00:00 | -0.271 | -270.88 |
| 2026-06-18T07:00:18+00:00 | binance_monitoring_tag | BLURUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 5% | 2026-06-18T07:02:00+00:00 → 2026-06-19T06:02:00+00:00 | +0.098 | +98.43 |
| 2026-06-18T07:30:00+00:00 | upbit_warning | AERGOUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 5%, TP 20%, trail 10% | 2026-06-18T07:31:00+00:00 → 2026-06-18T08:14:00+00:00 | +0.982 | +982.33 |
| 2026-06-19T02:08:56+00:00 | upbit_listing | LITUSDT | SHORT 3x, enter +0m, hold ≤1380m, SL 20% | 2026-06-19T02:10:00+00:00 → 2026-06-20T01:10:00+00:00 | +0.181 | +180.55 |
| 2026-06-19T02:08:56+00:00 | upbit_listing | KMNOUSDT | SHORT 3x, enter +0m, hold ≤1380m, SL 20% | 2026-06-19T02:10:00+00:00 → 2026-06-20T01:10:00+00:00 | -0.197 | -196.72 |
| 2026-06-19T02:08:56+00:00 | upbit_listing | MORPHOUSDT | SHORT 3x, enter +0m, hold ≤1380m, SL 20% | 2026-06-19T02:10:00+00:00 → 2026-06-20T01:10:00+00:00 | +0.076 | +75.67 |
| 2026-06-19T02:08:56+00:00 | upbit_listing | LDOUSDT | SHORT 3x, enter +0m, hold ≤1380m, SL 20% | 2026-06-19T02:10:00+00:00 → 2026-06-20T01:10:00+00:00 | +0.077 | +77.34 |
| 2026-06-19T02:08:56+00:00 | upbit_listing | PAXGUSDT | SHORT 3x, enter +0m, hold ≤1380m, SL 20% | 2026-06-19T02:10:00+00:00 → 2026-06-20T01:10:00+00:00 | +0.005 | +4.80 |
| 2026-06-19T09:00:02+00:00 | upbit_krw_listing | REUSDT | LONG 1x, enter +5m, hold ≤240m, SL 20%, TP 10% | 2026-06-19T09:07:00+00:00 → 2026-06-19T09:38:00+00:00 | +0.097 | +97.30 |
| 2026-06-22T05:00:00+00:00 | upbit_warning | TAIKOUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 5%, TP 20%, trail 10% | 2026-06-22T05:01:00+00:00 → 2026-06-23T04:01:00+00:00 | +0.573 | +573.14 |
| 2026-06-25T17:00:06+00:00 | binance_perp_delisting | IPUSDT | SHORT 2x, enter +5m, hold ≤240m, SL 20% | 2026-06-25T17:07:00+00:00 → 2026-06-25T21:07:00+00:00 | -0.212 | -212.42 |
| 2026-06-26T09:00:15+00:00 | binance_spot_delisting | NFPUSDT | SHORT 5x, enter +30m, hold ≤480m, SL 10%, TP 20%, trail 10% | 2026-06-26T09:32:00+00:00 → 2026-06-26T10:24:00+00:00 | +0.001 | +1.22 |
| 2026-06-30T03:00:55+00:00 | upbit_krw_listing | AIUSDT | LONG 1x, enter +5m, hold ≤240m, SL 20%, TP 10% | 2026-06-30T03:07:00+00:00 → 2026-06-30T07:07:00+00:00 | -0.004 | -3.99 |
| 2026-07-03T06:00:11+00:00 | binance_monitoring_tag | SCRTUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 5% | 2026-07-03T06:02:00+00:00 → 2026-07-03T07:09:00+00:00 | -0.271 | -270.88 |
| 2026-07-03T06:00:11+00:00 | binance_monitoring_tag | VANRYUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 5% | 2026-07-03T06:02:00+00:00 → 2026-07-03T06:27:00+00:00 | -0.271 | -270.88 |
| 2026-07-03T08:00:00+00:00 | upbit_delisting | AERGOUSDT | LONG 2x, enter +60m, hold ≤480m, SL 5% | 2026-07-03T09:01:00+00:00 → 2026-07-03T11:40:00+00:00 | -0.108 | -107.65 |
| 2026-07-07T04:39:48+00:00 | upbit_krw_listing | OPGUSDT | LONG 1x, enter +5m, hold ≤240m, SL 20%, TP 10% | 2026-07-07T04:46:00+00:00 → 2026-07-07T08:46:00+00:00 | -0.177 | -176.71 |
| 2026-07-07T07:30:00+00:00 | upbit_warning | 1000BONKUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 5%, TP 20%, trail 10% | 2026-07-07T07:31:00+00:00 → 2026-07-08T06:31:00+00:00 | +0.282 | +282.26 |
| 2026-07-17T07:30:01+00:00 | binance_spot_listing | AEROUSDT | LONG 2x, enter +0m, hold ≤480m, SL 5% | 2026-07-17T07:32:00+00:00 → 2026-07-17T13:36:00+00:00 | -0.107 | -106.94 |
| 2026-07-21T14:15:14+00:00 | binance_perp_delisting | AERGOUSDT | SHORT 2x, enter +5m, hold ≤240m, SL 20% | 2026-07-21T14:22:00+00:00 → 2026-07-21T18:22:00+00:00 | -0.124 | -124.25 |
| 2026-07-22T10:00:00+00:00 | upbit_warning | ZILUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 5%, TP 20%, trail 10% | 2026-07-22T10:01:00+00:00 → 2026-07-22T11:26:00+00:00 | -0.271 | -270.88 |
| 2026-07-24T03:00:06+00:00 | binance_monitoring_tag | ACXUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 5% | 2026-07-24T03:02:00+00:00 → 2026-07-24T03:10:00+00:00 | -0.271 | -270.88 |
| 2026-07-24T03:00:06+00:00 | binance_monitoring_tag | LSKUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 5% | 2026-07-24T03:02:00+00:00 → 2026-07-24T03:21:00+00:00 | -0.271 | -270.88 |
| 2026-07-24T03:00:06+00:00 | binance_monitoring_tag | STXUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 5% | 2026-07-24T03:02:00+00:00 → 2026-07-25T02:02:00+00:00 | +0.255 | +254.68 |
| 2026-07-28T09:00:00+00:00 | upbit_warning | STORJUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 5%, TP 20%, trail 10% | 2026-07-28T09:01:00+00:00 → 2026-07-28T09:03:00+00:00 | -0.271 | -270.88 |
| 2026-07-31T07:30:02+00:00 | upbit_warning | JASMYUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 10%, TP 20%, trail 10% | 2026-07-31T07:32:00+00:00 → 2026-08-01T06:32:00+00:00 | -0.059 | -58.81 |
| 2026-08-03T03:30:10+00:00 | binance_spot_delisting | ACXUSDT | SHORT 5x, enter +30m, hold ≤480m, SL 10%, TP 20%, trail 10% | 2026-08-03T04:02:00+00:00 → 2026-08-03T04:52:00+00:00 | +0.419 | +419.09 |
| 2026-08-03T03:30:10+00:00 | binance_spot_delisting | HFTUSDT | SHORT 5x, enter +30m, hold ≤480m, SL 10%, TP 20%, trail 10% | 2026-08-03T04:02:00+00:00 → 2026-08-03T04:03:00+00:00 | -0.522 | -521.76 |
| 2026-08-03T03:30:10+00:00 | binance_spot_delisting | VANRYUSDT | SHORT 5x, enter +30m, hold ≤480m, SL 10%, TP 20%, trail 10% | 2026-08-03T04:02:00+00:00 → 2026-08-03T12:02:00+00:00 | +0.881 | +880.79 |
| 2026-08-03T03:30:10+00:00 | binance_spot_delisting | VICUSDT | SHORT 5x, enter +30m, hold ≤480m, SL 10%, TP 20%, trail 10% | 2026-08-03T04:02:00+00:00 → 2026-08-03T04:44:00+00:00 | +0.188 | +188.42 |
| 2026-08-07T07:00:00+00:00 | upbit_delisting | 1000BONKUSDT | LONG 1x, enter +60m, hold ≤480m, SL 5% | 2026-08-07T08:01:00+00:00 → 2026-08-07T16:01:00+00:00 | -0.043 | -42.76 |
| 2026-08-07T07:30:00+00:00 | upbit_warning | SNXUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 10%, TP 20%, trail 10% | 2026-08-07T07:31:00+00:00 → 2026-08-08T06:31:00+00:00 | +0.063 | +63.06 |
| 2026-08-10T02:05:54+00:00 | upbit_listing | CYSUSDT | SHORT 3x, enter +0m, hold ≤1380m, SL 20% | 2026-08-10T02:07:00+00:00 → 2026-08-10T11:39:00+00:00 | -0.614 | -613.82 |
| 2026-08-10T02:05:54+00:00 | upbit_listing | ICNTUSDT | SHORT 3x, enter +0m, hold ≤1380m, SL 20% | 2026-08-10T02:07:00+00:00 → 2026-08-11T01:07:00+00:00 | +0.144 | +143.93 |
| 2026-08-10T02:05:54+00:00 | upbit_listing | XANUSDT | SHORT 3x, enter +0m, hold ≤1380m, SL 20% | 2026-08-10T02:07:00+00:00 → 2026-08-11T01:07:00+00:00 | +1.160 | +1159.51 |
| 2026-08-10T02:05:54+00:00 | upbit_listing | EDENUSDT | SHORT 3x, enter +0m, hold ≤1380m, SL 20% | 2026-08-10T02:07:00+00:00 → 2026-08-11T01:07:00+00:00 | +0.001 | +1.24 |
| 2026-08-10T02:05:54+00:00 | upbit_listing | ALLOUSDT | SHORT 3x, enter +0m, hold ≤1380m, SL 20% | 2026-08-10T02:07:00+00:00 → 2026-08-11T01:07:00+00:00 | -0.004 | -3.89 |
| 2026-08-11T06:00:00+00:00 | upbit_warning | RVNUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 10%, TP 20%, trail 10% | 2026-08-11T06:01:00+00:00 → 2026-08-12T01:01:00+00:00 | +0.936 | +935.58 |
| 2026-08-11T09:00:12+00:00 | binance_monitoring_tag | GLMRUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 5% | 2026-08-11T09:02:00+00:00 → 2026-08-12T08:02:00+00:00 | -0.020 | -20.03 |
| 2026-08-11T09:00:12+00:00 | binance_monitoring_tag | ICXUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 5% | 2026-08-11T09:02:00+00:00 → 2026-08-12T08:02:00+00:00 | -0.190 | -190.26 |
| 2026-08-11T09:00:12+00:00 | binance_monitoring_tag | MOVRUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 5% | 2026-08-11T09:02:00+00:00 → 2026-08-12T08:02:00+00:00 | +0.714 | +713.70 |
| 2026-08-11T09:00:12+00:00 | binance_monitoring_tag | RAREUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 5% | 2026-08-11T09:02:00+00:00 → 2026-08-12T08:02:00+00:00 | +0.073 | +73.09 |
| 2026-08-11T09:00:12+00:00 | binance_monitoring_tag | SOPHUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 5% | 2026-08-11T09:02:00+00:00 → 2026-08-12T02:55:00+00:00 | -0.270 | -269.87 |
| 2026-08-14T07:00:05+00:00 | upbit_delisting | JASMYUSDT | SHORT 2x, enter +15m, hold ≤240m, SL 10%, trail 10% | 2026-08-14T07:17:00+00:00 → 2026-08-14T11:17:00+00:00 | -0.066 | -65.57 |
| 2026-08-14T07:00:06+00:00 | upbit_delisting | STORJUSDT | SHORT 2x, enter +15m, hold ≤240m, SL 10%, trail 10% | 2026-08-14T07:17:00+00:00 → 2026-08-14T11:17:00+00:00 | +0.037 | +37.22 |
| 2026-08-20T06:00:06+00:00 | binance_spot_delisting | ICXUSDT | SHORT 5x, enter +30m, hold ≤480m, SL 10%, TP 20%, trail 10% | 2026-08-20T06:32:00+00:00 → 2026-08-20T14:32:00+00:00 | -0.146 | -146.47 |
| 2026-08-20T06:00:06+00:00 | binance_spot_delisting | SCRTUSDT | SHORT 5x, enter +30m, hold ≤480m, SL 10%, TP 20%, trail 10% | 2026-08-20T06:32:00+00:00 → 2026-08-20T07:22:00+00:00 | -0.228 | -228.18 |
| 2026-08-20T06:00:06+00:00 | binance_spot_delisting | STORJUSDT | SHORT 5x, enter +30m, hold ≤480m, SL 10%, TP 20%, trail 10% | 2026-08-20T06:32:00+00:00 → 2026-08-20T14:32:00+00:00 | +0.006 | +5.96 |
| 2026-08-21T00:48:00+00:00 | upbit_listing | BICOUSDT | SHORT 3x, enter +0m, hold ≤480m, SL 20% | 2026-08-21T00:49:00+00:00 → 2026-08-21T08:49:00+00:00 | +0.106 | +106.02 |
| 2026-08-21T00:48:00+00:00 | upbit_listing | BMTUSDT | SHORT 3x, enter +0m, hold ≤480m, SL 20% | 2026-08-21T00:49:00+00:00 → 2026-08-21T08:49:00+00:00 | +0.115 | +115.14 |
| 2026-08-21T00:48:00+00:00 | upbit_listing | NILUSDT | SHORT 3x, enter +0m, hold ≤480m, SL 20% | 2026-08-21T00:49:00+00:00 → 2026-08-21T08:49:00+00:00 | -0.231 | -230.55 |
| 2026-08-21T00:48:00+00:00 | upbit_listing | GWEIUSDT | SHORT 3x, enter +0m, hold ≤480m, SL 20% | 2026-08-21T00:49:00+00:00 → 2026-08-21T02:22:00+00:00 | -0.614 | -614.11 |
| 2026-08-21T08:00:01+00:00 | upbit_warning | MANTRAUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 10%, TP 20%, trail 10% | 2026-08-21T08:02:00+00:00 → 2026-08-21T14:00:00+00:00 | -0.499 | -499.16 |
| 2026-08-24T06:00:02+00:00 | upbit_warning | SANDUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 5%, TP 20%, trail 10% | 2026-08-24T06:02:00+00:00 → 2026-08-25T05:02:00+00:00 | +0.115 | +115.30 |
| 2026-08-28T07:00:00+00:00 | upbit_delisting | SNXUSDT | SHORT 1x, enter +15m, hold ≤240m, SL 10%, trail 10% | 2026-08-28T07:16:00+00:00 → 2026-08-28T11:16:00+00:00 | -0.020 | -19.57 |
| 2026-08-28T07:30:00+00:00 | upbit_warning | ICXUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 5%, TP 20%, trail 10% | 2026-08-28T07:31:00+00:00 → 2026-08-29T06:31:00+00:00 | -0.020 | -20.03 |
| 2026-09-01T08:02:57+00:00 | upbit_warning | INJUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 5%, TP 20%, trail 10% | 2026-09-01T08:04:00+00:00 → 2026-09-02T07:04:00+00:00 | +0.056 | +56.36 |
| 2026-09-04T08:00:06+00:00 | binance_monitoring_tag | AVAUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 5% | 2026-09-04T08:02:00+00:00 → 2026-09-05T07:02:00+00:00 | +0.304 | +304.30 |
| 2026-09-04T08:00:06+00:00 | binance_monitoring_tag | SCRUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 5% | 2026-09-04T08:02:00+00:00 → 2026-09-05T07:02:00+00:00 | +0.216 | +215.55 |
| 2026-09-04T08:00:06+00:00 | binance_monitoring_tag | TOWNSUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 5% | 2026-09-04T08:02:00+00:00 → 2026-09-05T07:02:00+00:00 | +0.213 | +213.09 |
| 2026-09-04T10:15:01+00:00 | binance_spot_listing | MARSCOINUSDT | LONG 1x, enter +0m, hold ≤480m, SL 5% | 2026-09-04T10:17:00+00:00 → 2026-09-04T10:18:00+00:00 | -0.054 | -53.82 |
| 2026-09-08T10:25:32+00:00 | upbit_listing | HEMIUSDT | SHORT 3x, enter +60m, hold ≤480m, SL 20%, TP 10% | 2026-09-08T11:27:00+00:00 → 2026-09-08T19:27:00+00:00 | +0.226 | +226.25 |
| 2026-09-08T10:25:32+00:00 | upbit_listing | USELESSUSDT | SHORT 3x, enter +60m, hold ≤480m, SL 20%, TP 10% | 2026-09-08T11:27:00+00:00 → 2026-09-08T15:02:00+00:00 | -0.614 | -613.95 |
| 2026-09-10T04:30:01+00:00 | upbit_listing | REZUSDT | SHORT 3x, enter +0m, hold ≤480m, SL 20% | 2026-09-10T04:32:00+00:00 → 2026-09-10T05:21:00+00:00 | -0.614 | -614.11 |
| 2026-09-18T07:30:00+00:00 | upbit_delisting | ICXUSDT | SHORT 1x, enter +15m, hold ≤480m, SL 10%, trail 10% | 2026-09-18T07:46:00+00:00 → 2026-09-18T15:46:00+00:00 | -0.004 | -4.01 |
| 2026-09-21T07:00:00+00:00 | upbit_warning | EGLDUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 5%, TP 20%, trail 10% | 2026-09-21T07:01:00+00:00 → 2026-09-21T10:49:00+00:00 | -0.273 | -273.47 |
| 2026-09-22T06:00:08+00:00 | upbit_warning | SOPHUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 5%, TP 20%, trail 10% | 2026-09-22T06:02:00+00:00 → 2026-09-23T05:02:00+00:00 | +0.517 | +517.41 |
| 2026-09-24T07:30:38+00:00 | binance_spot_listing | HYPEUSDT | LONG 1x, enter +5m, hold ≤480m, SL 10% | 2026-09-24T07:37:00+00:00 → 2026-09-24T15:37:00+00:00 | -0.020 | -19.60 |
| 2026-10-09T07:00:14+00:00 | binance_monitoring_tag | BICOUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 5% | 2026-10-09T07:02:00+00:00 → 2026-10-09T07:22:00+00:00 | -0.271 | -270.88 |
| 2026-10-09T07:00:14+00:00 | binance_monitoring_tag | CVCUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 5% | 2026-10-09T07:02:00+00:00 → 2026-10-09T11:52:00+00:00 | -0.271 | -270.83 |
| 2026-10-12T04:54:09+00:00 | upbit_krw_listing | RSRUSDT | LONG 1x, enter +5m, hold ≤240m, SL 20%, TP 10% | 2026-10-12T05:01:00+00:00 → 2026-10-12T09:01:00+00:00 | -0.002 | -1.85 |
| 2026-10-12T10:00:00+00:00 | upbit_krw_listing | GTCUSDT | LONG 1x, enter +5m, hold ≤240m, SL 20%, TP 10% | 2026-10-12T10:06:00+00:00 → 2026-10-12T10:36:00+00:00 | +0.097 | +97.30 |
| 2026-10-13T06:00:03+00:00 | upbit_warning | BLURUSDT | SHORT 5x, enter +0m, hold ≤1380m, SL 5%, TP 20%, trail 10% | 2026-10-13T06:02:00+00:00 → 2026-10-13T22:06:00+00:00 | +0.099 | +99.50 |
| 2026-10-14T06:00:08+00:00 | binance_spot_delisting | EPICUSDT | SHORT 5x, enter +30m, hold ≤480m, SL 10%, TP 20%, trail 10% | 2026-10-14T06:32:00+00:00 → 2026-10-14T09:15:00+00:00 | +0.136 | +136.45 |
| 2026-10-14T06:00:08+00:00 | binance_spot_delisting | QUICKUSDT | SHORT 5x, enter +30m, hold ≤480m, SL 10%, TP 20%, trail 10% | 2026-10-14T06:32:00+00:00 → 2026-10-14T14:32:00+00:00 | -0.020 | -20.03 |
| 2026-10-15T04:40:00+00:00 | upbit_krw_listing | PUFFERUSDT | LONG 1x, enter +5m, hold ≤240m, SL 20%, TP 10% | 2026-10-15T04:46:00+00:00 → 2026-10-15T08:46:00+00:00 | -0.004 | -3.99 |
| 2026-10-15T07:00:00+00:00 | upbit_delisting | SOPHUSDT | SHORT 1x, enter +15m, hold ≤480m, SL 10%, trail 10% | 2026-10-15T07:16:00+00:00 → 2026-10-15T10:34:00+00:00 | -0.055 | -55.31 |
| 2026-10-19T07:40:00+00:00 | upbit_krw_listing | CTUSDT | LONG 1x, enter +5m, hold ≤240m, SL 20%, TP 10% | 2026-10-19T07:46:00+00:00 → 2026-10-19T11:46:00+00:00 | -0.098 | -98.09 |
| 2026-10-21T09:30:01+00:00 | binance_perp_delisting | PTBUSDT | SHORT 2x, enter +5m, hold ≤240m, SL 20% | 2026-10-21T09:37:00+00:00 → 2026-10-21T13:37:00+00:00 | +0.234 | +233.76 |
| 2026-10-21T09:30:01+00:00 | binance_perp_delisting | MITOUSDT | SHORT 2x, enter +5m, hold ≤240m, SL 20% | 2026-10-21T09:37:00+00:00 → 2026-10-21T13:37:00+00:00 | +0.286 | +286.18 |
