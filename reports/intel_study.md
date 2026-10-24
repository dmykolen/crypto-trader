# Intel signals — out-of-sample study

Generated 2026-10-24T13:02:49+00:00 by `trader intel study`. Universe: 26 perps, 1,024,385 symbol-hours.
Train (sign selection) 2022-01-01 → 2024-07-01, test (scored once) 2024-07-01 → 2026-10-01. Costs 5 bps per unit turnover.

## Verdicts

| feature | mode | verdict | rank corr with past 24 h return | what |
|---|---|---|---|---|
| `news_mentions_24h` | cs | **weak** | +0.01 | distinct headlines naming the perp, trailing 24 h |
| `news_burst_z` | cs | **weak** | +0.00 | this hour's mentions vs the trailing 7-day baseline |
| `news_polarity_24h` | cs | **fails** | +0.00 | mention-weighted lexicon polarity, trailing 24 h |
| `oi_chg_1h` | cs | **untradeable** | +0.12 | open-interest change over 1 h (metrics archive) |
| `oi_chg_24h` | cs | **untradeable** | +0.69 | open-interest change over 24 h |
| `top_position_ratio_z` | cs | **weak** | +0.06 | top-trader long/short position ratio vs its own 30-day history |
| `top_account_ratio_z` | cs | **fails** | -0.24 | top-trader long/short account ratio vs its own 30-day history |
| `global_account_ratio_z` | cs | **fails** | -0.29 | all-account long/short ratio vs its own 30-day history |
| `taker_ratio_24h` | cs | **fails** | +0.08 | log taker buy/sell volume ratio, trailing 24 h mean |
| `oi_chg_24h_ts` | ts | **untradeable** | +0.69 | open-interest change over 24 h, within-symbol timing |
| `top_position_ratio_ts` | ts | **untradeable** | +0.06 | top-trader position ratio z, within-symbol timing |
| `news_mentions_24h_ts` | ts | **fails** | +0.01 | own headline count, within-symbol timing |
| `wiki_z` | ts | **weak** | +0.01 | Wikipedia pageviews vs 28-day baseline (9 large tokens) |
| `gdelt_z` | ts | **no-data** | +0.03 | GDELT article volume vs 28-day baseline (5 large tokens) |
| `fear_greed` | mkt | **untradeable** | +0.07 | alternative.me Fear & Greed index level |
| `fear_greed_chg_7d` | mkt | **weak** | +0.10 | Fear & Greed change over 7 days |
| `mkt_mentions_24h` | mkt | **fails** | -0.04 | all stored headlines, trailing 24 h |
| `mkt_polarity_24h` | mkt | **fails** | +0.01 | market-wide mention-weighted polarity, trailing 24 h |
| `ref_ret_24h` | cs | **untradeable** | +1.00 | REFERENCE (not intel): own past 24 h return |
| `ref_funding` | cs | **untradeable** | +0.06 | REFERENCE (not intel): last funding rate |

Verdict counts (all 20 features incl. 2 price references): fails 7, no-data 1, untradeable 7, weak 5.

- **robust** (Holm-significant on test in the train direction AND the train-chosen rule is net positive on test): none.
- **untradeable** (Holm-significant rank IC on test, but the rule loses after 5 bps costs): `oi_chg_1h`, `oi_chg_24h`, `oi_chg_24h_ts`, `top_position_ratio_ts`, `fear_greed`.
- **weak** (only unadjusted p < 0.05 on test): `news_mentions_24h`, `news_burst_z`, `top_position_ratio_z`, `wiki_z`, `fear_greed_chg_7d`.
- **fails**: `news_polarity_24h`, `top_account_ratio_z`, `global_account_ratio_z`, `taker_ratio_24h`, `news_mentions_24h_ts`, `mkt_mentions_24h`, `mkt_polarity_24h`. **no-data**: `gdelt_z`.
- References: short-term reversal `ref_ret_24h` is **untradeable**, funding `ref_funding` is **untradeable** — the harness does detect known price effects, so the intel results are not a power failure.

## Rank IC by horizon (monthly ICs; test IC signed by the train direction)

| feature | h | cov train | cov test | IC train | t train | IC test (signed) | t test | p test | p Holm |
|---|---|---|---|---|---|---|---|---|---|
| `news_mentions_24h` | 1 | 1.8% | 1.5% | +0.0069 | 2.65 | +0.0086 | 2.92 | 0.0018 | 0.0704 |
| `news_mentions_24h` | 4 | 1.8% | 1.5% | +0.0092 | 1.76 | +0.0086 | 1.68 | 0.0465 | 1.0 |
| `news_mentions_24h` | 24 | 1.8% | 1.5% | +0.0232 | 2.29 | +0.0106 | 1.03 | 0.1514 | 1.0 |
| `news_burst_z` | 1 | 0.1% | 0.1% | -0.0034 | -0.21 | -0.0214 | -1.86 | 0.9688 | 1.0 |
| `news_burst_z` | 4 | 0.1% | 0.1% | +0.0215 | 1.76 | +0.0299 | 2.31 | 0.0106 | 0.3698 |
| `news_burst_z` | 24 | 0.1% | 0.1% | +0.0144 | 1.01 | +0.0141 | 1.08 | 0.1395 | 1.0 |
| `news_polarity_24h` | 1 | 0.4% | 0.2% | +0.0055 | 1.51 | +0.0111 | 1.13 | 0.1295 | 1.0 |
| `news_polarity_24h` | 4 | 0.4% | 0.2% | +0.0037 | 0.42 | +0.0007 | 0.03 | 0.487 | 1.0 |
| `news_polarity_24h` | 24 | 0.4% | 0.2% | +0.0110 | 0.43 | +0.0091 | 0.27 | 0.3919 | 1.0 |
| `oi_chg_1h` | 1 | 99.9% | 96.7% | -0.0248 | -10.93 | +0.0191 | 8.09 | 0.0 | 0.0 |
| `oi_chg_1h` | 4 | 99.9% | 96.7% | -0.0201 | -7.88 | +0.0127 | 6.2 | 0.0 | 0.0 |
| `oi_chg_1h` | 24 | 99.9% | 96.7% | -0.0095 | -4.58 | +0.0063 | 2.62 | 0.0045 | 0.1605 |
| `oi_chg_24h` | 1 | 99.8% | 96.7% | -0.0206 | -12.38 | +0.0139 | 6.52 | 0.0 | 0.0 |
| `oi_chg_24h` | 4 | 99.8% | 96.7% | -0.0249 | -10.39 | +0.0178 | 4.31 | 0.0 | 0.0004 |
| `oi_chg_24h` | 24 | 99.8% | 96.7% | -0.0246 | -4.94 | +0.0168 | 2.28 | 0.0112 | 0.3802 |
| `top_position_ratio_z` | 1 | 63.1% | 96.8% | -0.0035 | -2.87 | +0.0060 | 2.91 | 0.0018 | 0.0704 |
| `top_position_ratio_z` | 4 | 63.1% | 96.8% | -0.0087 | -3.28 | +0.0091 | 2.25 | 0.0122 | 0.4027 |
| `top_position_ratio_z` | 24 | 63.1% | 96.8% | -0.0174 | -2.89 | +0.0095 | 1.03 | 0.1512 | 1.0 |
| `top_account_ratio_z` | 1 | 63.1% | 96.8% | +0.0178 | 4.81 | +0.0018 | 0.99 | 0.1605 | 1.0 |
| `top_account_ratio_z` | 4 | 63.1% | 96.8% | +0.0166 | 2.74 | -0.0014 | -0.39 | 0.6524 | 1.0 |
| `top_account_ratio_z` | 24 | 63.1% | 96.8% | +0.0060 | 0.51 | -0.0061 | -0.88 | 0.8114 | 1.0 |
| `global_account_ratio_z` | 1 | 97.0% | 96.8% | +0.0154 | 5.41 | +0.0023 | 1.21 | 0.1134 | 1.0 |
| `global_account_ratio_z` | 4 | 97.0% | 96.8% | +0.0151 | 3.03 | +0.0021 | 0.62 | 0.2692 | 1.0 |
| `global_account_ratio_z` | 24 | 97.0% | 96.8% | +0.0044 | 0.48 | +0.0014 | 0.21 | 0.4163 | 1.0 |
| `taker_ratio_24h` | 1 | 85.7% | 96.8% | -0.0044 | -3.21 | +0.0018 | 1.42 | 0.0785 | 1.0 |
| `taker_ratio_24h` | 4 | 85.7% | 96.8% | -0.0023 | -1.01 | +0.0023 | 0.73 | 0.2316 | 1.0 |
| `taker_ratio_24h` | 24 | 85.7% | 96.8% | -0.0028 | -0.42 | +0.0001 | 0.02 | 0.4911 | 1.0 |
| `oi_chg_24h_ts` | 1 | 99.8% | 96.7% | -0.0353 | -11.85 | +0.0283 | 8.29 | 0.0 | 0.0 |
| `oi_chg_24h_ts` | 4 | 99.8% | 96.7% | -0.0511 | -9.8 | +0.0375 | 5.43 | 0.0 | 0.0 |
| `oi_chg_24h_ts` | 24 | 99.8% | 96.7% | -0.0691 | -5.59 | +0.0339 | 2.65 | 0.004 | 0.1493 |
| `top_position_ratio_ts` | 1 | 63.1% | 96.8% | -0.0070 | -1.87 | +0.0127 | 3.62 | 0.0001 | 0.0064 |
| `top_position_ratio_ts` | 4 | 63.1% | 96.8% | -0.0187 | -2.6 | +0.0340 | 5.24 | 0.0 | 0.0 |
| `top_position_ratio_ts` | 24 | 63.1% | 96.8% | -0.0404 | -2.49 | +0.0867 | 5.95 | 0.0 | 0.0 |
| `news_mentions_24h_ts` | 1 | 1.8% | 1.5% | +0.0033 | 1.2 | +0.0004 | 0.11 | 0.4577 | 1.0 |
| `news_mentions_24h_ts` | 4 | 1.8% | 1.5% | +0.0046 | 0.8 | -0.0050 | -0.71 | 0.7606 | 1.0 |
| `news_mentions_24h_ts` | 24 | 1.8% | 1.5% | +0.0066 | 0.39 | -0.0257 | -2.34 | 0.9904 | 1.0 |
| `wiki_z` | 1 | 35.8% | 37.4% | -0.0001 | -0.04 | -0.0002 | -0.05 | 0.5186 | 1.0 |
| `wiki_z` | 4 | 35.8% | 37.4% | -0.0022 | -0.44 | +0.0029 | 0.39 | 0.3466 | 1.0 |
| `wiki_z` | 24 | 35.8% | 37.4% | -0.0030 | -0.22 | +0.0366 | 2.17 | 0.0149 | 0.4762 |
| `gdelt_z` | 1 | 4.0% | 4.2% | -0.0005 | -0.07 | – | – | – | – |
| `gdelt_z` | 4 | 4.0% | 4.2% | -0.0100 | -0.64 | – | – | – | – |
| `gdelt_z` | 24 | 4.0% | 4.2% | -0.0137 | -0.33 | – | – | – | – |
| `fear_greed` | 1 | 100.0% | 100.0% | -0.0075 | -1.3 | +0.0180 | 2.69 | 0.0035 | 0.1345 |
| `fear_greed` | 4 | 100.0% | 100.0% | -0.0408 | -3.62 | +0.0484 | 3.54 | 0.0002 | 0.0084 |
| `fear_greed` | 24 | 100.0% | 100.0% | -0.0909 | -2.92 | +0.1588 | 6.25 | 0.0 | 0.0 |
| `fear_greed_chg_7d` | 1 | 91.3% | 94.3% | +0.0002 | 0.03 | +0.0024 | 0.38 | 0.3524 | 1.0 |
| `fear_greed_chg_7d` | 4 | 91.3% | 94.3% | -0.0125 | -1.17 | +0.0084 | 0.68 | 0.2476 | 1.0 |
| `fear_greed_chg_7d` | 24 | 91.3% | 94.3% | -0.0539 | -1.93 | +0.0432 | 1.89 | 0.0295 | 0.9132 |
| `mkt_mentions_24h` | 1 | 74.7% | 79.4% | +0.0056 | 1.01 | -0.0053 | -0.71 | 0.7625 | 1.0 |
| `mkt_mentions_24h` | 4 | 74.7% | 79.4% | +0.0025 | 0.24 | -0.0167 | -1.11 | 0.8666 | 1.0 |
| `mkt_mentions_24h` | 24 | 74.7% | 79.4% | +0.0069 | 0.25 | -0.0259 | -0.75 | 0.7731 | 1.0 |
| `mkt_polarity_24h` | 1 | 45.1% | 54.3% | -0.0020 | -0.39 | +0.0055 | 0.96 | 0.1689 | 1.0 |
| `mkt_polarity_24h` | 4 | 45.1% | 54.3% | -0.0042 | -0.41 | +0.0113 | 0.94 | 0.1729 | 1.0 |
| `mkt_polarity_24h` | 24 | 45.1% | 54.3% | -0.0098 | -0.46 | +0.0357 | 1.19 | 0.1165 | 1.0 |
| `ref_ret_24h` | 1 | 99.7% | 96.6% | -0.0354 | -13.57 | +0.0259 | 9.49 | 0.0 | 0.0 |
| `ref_ret_24h` | 4 | 99.7% | 96.6% | -0.0359 | -9.41 | +0.0335 | 5.89 | 0.0 | 0.0 |
| `ref_ret_24h` | 24 | 99.7% | 96.6% | -0.0234 | -3.51 | +0.0337 | 4.07 | 0.0 | 0.0011 |
| `ref_funding` | 1 | 12.3% | 11.9% | -0.0078 | -1.77 | +0.0164 | 3.45 | 0.0003 | 0.0113 |
| `ref_funding` | 4 | 12.3% | 11.9% | -0.0136 | -3.23 | +0.0233 | 3.82 | 0.0001 | 0.003 |
| `ref_funding` | 24 | 12.3% | 11.9% | -0.0189 | -2.67 | +0.0281 | 3.68 | 0.0001 | 0.0051 |

## Trading rule (horizon + sign picked on train by net return; cs = rank-weighted long/short, ts/mkt = clipped z timing)

| feature | h | train net bps/day | train Sharpe | test gross bps/day | test net bps/day | test Sharpe | test turnover/day |
|---|---|---|---|---|---|---|---|
| `news_mentions_24h` | 24 | -23.99 | -0.56 | 0.02 | -2.15 | -0.58 | 0.435 |
| `news_burst_z` | 24 | 0.09 | 0.19 | -1.09 | -1.15 | -1.28 | 0.012 |
| `news_polarity_24h` | 1 | 20.6 | 1.06 | 0.13 | -0.3 | -0.29 | 0.086 |
| `oi_chg_1h` | 24 | 5.43 | 0.71 | 5.83 | -0.69 | -0.16 | 1.304 |
| `oi_chg_24h` | 24 | -1.88 | -0.23 | -2.5 | -9.2 | -2.2 | 1.339 |
| `top_position_ratio_z` | 24 | -1.6 | -0.45 | -1.01 | -3.85 | -1.02 | 0.568 |
| `top_account_ratio_z` | 24 | -4.97 | -1.16 | -2.13 | -5.38 | -1.3 | 0.651 |
| `global_account_ratio_z` | 24 | -12.96 | -1.7 | -1.18 | -4.35 | -1.06 | 0.633 |
| `taker_ratio_24h` | 24 | -0.3 | -0.04 | -1.59 | -8.09 | -2.26 | 1.299 |
| `oi_chg_24h_ts` | 24 | 15.94 | 1.15 | -22.4 | -29.2 | -2.05 | 1.36 |
| `top_position_ratio_ts` | 4 | -16.0 | -1.32 | 3.9 | -1.43 | -0.1 | 1.067 |
| `news_mentions_24h_ts` | 24 | -2.09 | -0.08 | 4.56 | 3.29 | 0.2 | 0.253 |
| `wiki_z` | 1 | -4.94 | -0.35 | -8.58 | -12.52 | -0.92 | 0.787 |
| `gdelt_z` | 1 | -1.81 | -0.19 | -0.46 | -0.46 | -0.27 | 0.0 |
| `fear_greed` | 24 | -13.32 | -0.74 | -5.59 | -6.29 | -0.41 | 0.14 |
| `fear_greed_chg_7d` | 1 | 3.79 | 0.26 | 5.83 | 3.72 | 0.26 | 0.422 |
| `mkt_mentions_24h` | 24 | -7.65 | -0.46 | -1.75 | -5.39 | -0.38 | 0.728 |
| `mkt_polarity_24h` | 1 | 3.27 | 0.26 | 6.43 | 0.95 | 0.08 | 1.097 |
| `ref_ret_24h` | 24 | -8.56 | -0.96 | -1.06 | -7.64 | -1.42 | 1.317 |
| `ref_funding` | 24 | -8.89 | -1.05 | 4.27 | -0.82 | -0.2 | 1.017 |

## Event study (market-relative forward return, one event per symbol per 24 h)

| event | period | n | 1h bps | t | 4h bps | t | 24h bps | t | polarity-signed 24h bps | t |
|---|---|---|---|---|---|---|---|---|---|---|
| cat_listing | train | 86 | -0.3 | -0.04 | 21.6 | 1.49 | 2.6 | 0.1 | -22.6 | -0.59 |
| cat_listing | test | 137 | -0.2 | -0.07 | 0.2 | 0.03 | 2.0 | 0.09 | -23.8 | -0.26 |
| cat_delisting | train | 11 | -234.9 | -1.02 | -1852.6 | -1.02 | -3528.4 | -1.0 | 13.0 | 0.4 |
| cat_delisting | test | 4 | -48.2 | – | -30.4 | – | -112.9 | – | – | – |
| cat_hack_exploit | train | 0 | – | – | – | – | – | – | – | – |
| cat_hack_exploit | test | 1 | 0.9 | – | -7.5 | – | 225.5 | – | – | – |
| cat_regulation | train | 0 | – | – | – | – | – | – | – | – |
| cat_regulation | test | 6 | -22.0 | -0.74 | -50.8 | -1.81 | -83.9 | -2.65 | 14.9 | – |
| cat_lawsuit | train | 0 | – | – | – | – | – | – | – | – |
| cat_lawsuit | test | 5 | 13.7 | – | 31.7 | – | 61.9 | – | -61.9 | – |
| cat_etf | train | 0 | – | – | – | – | – | – | – | – |
| cat_etf | test | 6 | 5.2 | 0.34 | 37.4 | 0.8 | 112.0 | 1.56 | 13.7 | – |
| cat_unlock_supply | train | 0 | – | – | – | – | – | – | – | – |
| cat_unlock_supply | test | 1 | 3.9 | – | 3.4 | – | -98.5 | – | 98.5 | – |
| cat_partnership_adoption | train | 32 | 6.0 | 0.42 | 20.4 | 0.94 | 1.8 | 0.04 | -74.5 | – |
| cat_partnership_adoption | test | 2 | -0.9 | – | -8.1 | – | -158.1 | – | 6.5 | – |
| cat_macro | train | 0 | – | – | – | – | – | – | – | – |
| cat_macro | test | 6 | 12.8 | 1.73 | 6.5 | 0.28 | -88.4 | -2.0 | 65.7 | – |
| cat_outage | train | 3 | 70.4 | – | 106.1 | – | -552.9 | – | 385.7 | – |
| cat_outage | test | 0 | – | – | – | – | – | – | – | – |
| burst_z>=3 & mentions>=2 | train | 1 | -27.3 | – | -42.3 | – | -109.9 | – | – | – |
| burst_z>=3 & mentions>=2 | test | 7 | -9.3 | -0.77 | 19.3 | 0.39 | 124.7 | 1.39 | 384.3 | – |
| any_mention | train | 388 | -7.2 | -1.01 | -42.9 | -0.82 | -93.5 | -0.93 | 30.7 | 0.87 |
| any_mention | test | 280 | 0.9 | 0.35 | 5.6 | 1.06 | 14.8 | 0.96 | 16.6 | 0.53 |

## Data coverage and caveats

- Stored text history 2022–2026 is almost entirely Binance + Upbit announcement boards; media RSS, Reddit and the other boards only go back weeks or months, so the news_* features here measure exchange-announcement attention, not media sentiment.
- Polarity is a title lexicon, not a model; Claude assessments (llm_score) exist for too few items to be studied and are excluded.
- Wikipedia pageviews cover 9 tokens, so wiki_z is time-series only (test coverage 37.4% of symbol-hours); GDELT rows cached: 1098.
- GDELT: only 1 token(s), 2021-12-01 → 2022-12-01 cached — the API throttled and then refused this host during the backfill (HTTP 429 / connect timeouts even at one request per minute), so gdelt_z has no test-period data. `trader intel backfill` resumes it.
- Positioning signals partly overlap with short-term price reversal (rank-correlation column; oi_chg_24h most of all); like the reversal reference itself, the Holm-significant ones are real at 1–4 h but too small to pay 5 bps per unit of turnover.
- Positioning (OI, long/short ratios) comes from the data.binance.vision metrics archive, last 5-minute snapshot inside each hour.
- Entity linking uses today's perp list and CoinGecko names; universe symbols all traded through both periods except LUNA (to 2022-05), MATIC (to 2024-09) and FTM (migrated to S), so survivorship effects on linking are limited to them.
- Monthly-IC t-stats treat months as independent; persistent features (Fear & Greed, ratios) have autocorrelated monthly ICs, so their t is optimistic.
