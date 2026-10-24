# crypto-trader

News-driven, leverage-aware research and trading for **Binance USDⓈ-M perpetuals**, with Claude as analyst.

It watches exchange notice boards (Upbit, Binance) and crypto media, classifies every notice into a tradable
event, and trades the reaction with **playbooks learned walk-forward from every past notice** (≈540 events since
2021, delisted contracts included). A second research track selects per-token strategies (trend / breakout /
mean reversion / LightGBM multi-horizon forecast) walk-forward. Claude triages free-text news, writes desk
briefs grounded in the app's own measurements, and critically reviews every research report.

> ⚠️ Leveraged trading can lose the whole margin. Everything here defaults to **paper trading**. Backtests,
> even honest out-of-sample ones, do not guarantee live results. See [Limits](#limits) before risking money.

## Setup

```bash
uv sync && uv run prek install --prepare-hooks
cp .env.example .env        # set ANTHROPIC_API_KEY; Binance keys only for TRADING_MODE=live
uv run trader backfill      # Upbit + Binance notice history → data/trader.db (~10 min; re-run to resume after rate limits)
```

## Quick start

```bash
uv run trader research events                      # event study + walk-forward playbooks → reports/event_research.{md,json}
uv run trader research review                      # Claude's sceptical review of that report
uv run trader research strategies BTCUSDT SOLUSDT  # per-token strategy selection → reports/strategy_selection.*
uv run trader forecast SOLUSDT --interval 1h       # multi-horizon forecast with its out-of-sample accuracy
uv run trader brief SOLUSDT                        # Claude desk brief (regime, forecast, playbooks, news)
uv run trader analyze-news "Binance Will Delist X"  # rule events + Claude price-impact assessment
uv run trader run                                  # news watcher + paper trader
uv run trader serve                                # HTTP API (RUN_WATCHER=true also runs the trader inside it)
```

## Results (out-of-sample, `reports/event_research.md`)

Every number below comes from trades chosen by a rule that only saw events whose 24h outcome was known before
the notice appeared. Charged: 0.05 % taker fee, 0.15 %/side slippage (0.3 % on stops; a stop that gaps fills at the
open, a take-profit never fills better than its level), every historical funding settlement in the holding window,
and isolated liquidation with a 2 % maintenance margin. Entry is assumed 60 s after the announcement.

| view | result |
|---|---|
| OOS trades (544 events, 2021-04 → 2026-10) | 425 trades, win rate 51 %, mean +5.9 % / median +0.6 % on margin, **0 liquidations** |
| **≥ $100 within 24h from $1000**, each trade on a fresh $1000 | **148 trades on 126 distinct tokens** |
| One $1000 account — 20 % of equity per trade, ≤ 5 open, ≤ 30 % per announcement (the live rules) | **$1000 → $3,483** (+248 %), max drawdown −42 %; 18 trades made ≥ 10 % of the balance in < 24h, on 17 tokens |
| Announcement-clustered bootstrap (276 announcements) | mean +5.9 % on margin, 90 % interval +2.3 % … +9.6 %, P(mean ≤ 0) = 0.3 % |
| Account without the 5 / 10 most profitable announcements | +30 % / −13 % |
| Account with entries 3 min / 5 min late | +57 % / +10 % |
| Account with 2× / 3× slippage | +165 % / +62 % |

The edge is **statistically real but fragile and unsteady**: only 6 of 12 half-years were profitable, 2026-H1 alone
made +208 % (without it: +13 % over 5.5 years), and 2026-H2 so far is −32 %. Three event types carry it with
intervals that exclude zero: `binance_monitoring_tag`, `binance_spot_delisting` and `upbit_listing`. Upbit KRW
listings — the most famous catalyst — are *skipped*: the jump happens within seconds, before a 60 s reaction can
fill, and fading it afterwards loses. Claude's verdict (`reports/event_research_review.md`): **paper trade first**.

Continuous strategies on majors (`reports/strategy_selection.md`, 1 year, 15m bars, weekly walk-forward) found
**no robust edge** — BTC +48 % with a −65 % drawdown, ETH/SOL/DOGE/XRP lost — so the selector currently stays flat.

## How it works

| step | module |
|---|---|
| notice boards & media → `NewsItem` (resumable backfill + live polling every 15 s / 120 s) | `services/news.py`, `integrations/{upbit,binance,rss}.py` |
| rule classification into events (listings, KRW listings, delistings, warnings, monitoring tags…) | `services/events.py` |
| 1m klines + funding from `data.binance.vision` (survivorship-free) + REST, parquet cache | `services/market_data.py` |
| leveraged backtest engine (numba): next-open fills, fees, slippage, gap-through stops, funding, isolated liquidation | `services/engine.py` |
| playbook grid (side × delay × stop × TP × trail × hold × leverage, stops always before liquidation) → walk-forward LCB selection → one-account replay → robustness, concentration and clustered-bootstrap checks | `services/playbooks.py`, `services/report.py` |
| per-token strategy selection (trend / breakout / mean reversion / LightGBM) walk-forward | `services/{strategies,features,forecast,selection}.py` |
| Claude: news impact (fast model), desk brief + report review (deep model), structured outputs only | `ai/`, `integrations/llm.py` |
| trading loop with risk rails (margin fraction, max positions, per-announcement cap, daily loss stop, stale-notice guard); paper broker or ccxt live | `services/{trading,broker}.py`, `integrations/exchange.py` |
| HTTP: `/health`, `/ready`, `/metrics`, `/api/v1/{news,trades,portfolio,playbooks,reports/{name},forecast/{symbol},analyze,brief/{symbol}}` | `transports/http/`, `main.py` |

## News & market intelligence (`trader intel`, `src/trader/intel/`)

Many sources → tagged, entity-linked items → hourly per-perp signals that bots can join to 1h bars.

```bash
uv run trader intel sources        # health table: 18 media RSS, Binance/Upbit/Bybit/OKX/KuCoin boards, blogs, Reddit, numeric series
uv run trader intel fetch          # one pass → NewsItem rows, series caches, IntelSignal rows (--llm adds budgeted Claude analysis)
uv run trader intel watch          # poll forever (text every 60 s, numeric series every 15th pass)
uv run trader intel signals SOLUSDT  # last 72 h of mentions/polarity/categories + the latest feature row
uv run trader intel backfill       # resumable history: Fear & Greed, Wikipedia, Binance metrics archive (OI, long/short), GDELT
uv run trader intel retag          # re-run rule tagging + linking on every stored item and rebuild signals
uv run trader intel study          # out-of-sample study → reports/intel_study.{md,json}
```

`trader.intel.signals.features(symbol, start, end)` returns an hourly frame indexed like the 1h panel: news mentions,
burst z, polarity, category counts, market-wide attention, Fear & Greed, OI / long-short ratios, Wikipedia / GDELT z.
A row with open_time t only uses information available at that bar's close (daily series are lagged until published).
Backfill caches live in `data/intel/` (series parquet + one metrics parquet per perp); days that keep failing are
logged and retried by the next run, 404 days (not listed yet / delisted) are remembered.

**Study result (`reports/intel_study.md`, 26 perps, 1.02 M symbol-hours, signs fixed on 2022-01 → 2024-06, scored
once on 2024-07 → 2026-09, Holm-corrected, 5 bps per unit turnover): no intel signal is a tradeable edge.**
OI change, the top-trader position ratio and the Fear & Greed level have Holm-significant rank ICs out of sample
(signed IC +0.01 … +0.16), but — exactly like the short-term-reversal and funding references — every rule built
from them loses after costs (test net −0.7 … −29 bps/day). Exchange-announcement mention counts, bursts and Wikipedia attention are only unadjusted-significant; headline
polarity, account ratios, taker ratio and market-wide news volume fail. Caveats: the 2022–2026 text history is almost
all Binance/Upbit announcements (media feeds only go back weeks), and GDELT throttled this host, so `gdelt_z` is
unscored. Use these as context features, not as standalone triggers.

## Configuration

All settings come from env / `.env` (see `.env.example`). The important ones:

| variable | default | meaning |
|---|---|---|
| `ANTHROPIC_API_KEY` | – | enables Claude features |
| `LLM_FAST_MODEL` / `LLM_DEEP_MODEL` | `claude-haiku-5-5` / `claude-opus-5-5` | news triage / briefs & reviews |
| `TRADING_MODE` | `paper` | `live` sends real orders through ccxt (needs `BINANCE_API_KEY`/`BINANCE_API_SECRET`, or `CCXT_API_KEY`/`CCXT_SECRET`) |
| `MARGIN_FRACTION` | `0.2` | isolated margin per trade, fraction of equity |
| `MAX_NOTICE_FRACTION` | `0.3` | margin all trades triggered by one announcement may share |
| `MAX_OPEN_POSITIONS` / `MAX_DAILY_LOSS` / `MAX_LEVERAGE` | `5` / `0.2` / `20` | risk rails |
| `ENTRY_LATENCY_S` | `60` | reaction time assumed by research (`trader research events --latency-s`) |
| `MAX_NOTICE_AGE_S` | `300` | notices first seen later than this are recorded, never traded |
| `LLM_NEWS_TRADING` | `false` | trade free-text news on Claude's word alone (no learned playbook) |

## Limits

* **Latency is the edge.** The account result falls from +248 % to +10 % when entries are 5 minutes late. Live
  trading must see notices within seconds (the watcher polls every 15 s; faster feeds would help).
* **Fat tails.** The median trade makes +0.6 %; a handful of announcements make the result (without the best 10 it
  is negative). Expect long flat or losing stretches.
* **Capacity & microstructure.** Most events hit small caps; slippage grows with size, and Binance may cut leverage,
  shorten funding intervals or switch tagged/delisting contracts to reduce-only — not modelled. Results assume ~$1–10k.
* **Regime dependence.** 6 of 12 half-years lost money; 2026-H1 drove most of the gain; 2026-H2 is negative so far.
* **Exchange rules change.** Notice formats and listing practices move; re-run `trader research events`
  regularly — live playbooks are refitted from it.
* **Not financial advice.** Run paper first; size live trading so that a total loss of the margin is acceptable.

## Development

```bash
uv run pytest            # engine, events, playbooks, features, news backfill, trading loop, API
uv run ruff check . && uv run ruff format --check .
uv run prek run --all-files
```

Layout follows the team service architecture: `core/` (config, db, logging, metrics), `models/`, `services/`,
`integrations/`, `ai/`, `transports/{cli.py,http/}`, `main.py`. Docker: `docker build -t trader .` (non-root, state
lives in the `/data` volume).
