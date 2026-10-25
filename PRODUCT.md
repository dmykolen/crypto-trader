# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

React + TypeScript + Vite + Tailwind CSS, built into static files that the existing FastAPI backend (`trader serve`) serves on localhost. Chosen by the user from the offered options ("на твій вибір").

## Users

One operator: the owner of this repository, a developer-trader in Kyiv, working on this Mac. He runs two trading bots on Binance USDⓈ-M perpetuals and comes to the UI in two situations: a quick glance (are the bots alive, what did they do, what is the equity) and long research sessions (re-testing strategies on history, reading the evidence). He reads Ukrainian; the app's existing reports, CLI help texts and research log are in Ukrainian.

## Product Purpose

A control room for two autonomous strategies:

- **Bot #1 «Анонси»** — reads Binance and Upbit announcements (listings, delistings, monitoring tags, warnings) and trades the token's perpetual within seconds; its edge exists only in the first 1–2 s after publication.
- **Bot #2 «Квант»** — every day at 00:15 UTC rebalances a market-neutral book: up to 30 longs and 30 shorts among liquid perpetuals ranked by two LightGBM models, shorts capped at 4 %, beta-hedged with BTC, 2x gross, traded only past a 1 % band.

Success: the operator sees at any moment what each bot is doing and why, can start/stop them, switch a bot to real money with an explicit confirmation, run tests on historical data and read the results as charts — without opening a terminal.

## Positioning

Every number the UI shows is backed by out-of-sample evidence the app produced itself (walk-forward models, an untouched 2021–2023 period, a forward test on unseen days, paper trading), and any claim can be re-tested against history from the same screen.

## Operating Context

- Runs only on localhost of this Mac; no login, no remote access, single user.
- Bots run as separate background processes (`trader run`, `trader quant paper --loop`); the UI starts/stops them and reads their journals: SQLite trade journal, notice feed, the quant paper ledger (`data/quant/paper/ledger.json`), reports under `reports/`.
- Historical tests already exist as engine functions/CLI commands: notice replay (`trader replay`), quant book of a day, single-token day view, forward test on fresh quotes, period backtests over the walk-forward predictions (2023-07…2026-09) and the untouched 2021-07…2023-06 rebuild, quarterly retraining.
- Market data comes from Binance (archives + REST); live trading needs Binance API keys in `.env` (currently not configured).

## Capabilities and Constraints

- Control scope (confirmed): start/stop each bot in paper mode, run backtests, retrain models, and switch a bot to real-money trading from the UI with an explicit confirmation.
- Real-money mode is impossible without API keys; the UI must say so instead of offering a dead control.
- State-changing actions must be protected against cross-site requests from other pages open in the same browser (localhost CSRF / DNS rebinding).
- Long jobs (forward test downloads, retraining) take minutes; the UI must show progress/state and survive page reloads.
- Expected performance must be communicated honestly: ≈ 25–55 %/year at 2x with drawdowns up to ~30 %, not daily miracles.

## Evidence on Hand

- `RESEARCH.md` — hypothesis log (H01–H34, I01–I28, Q01–Q40) with results.
- `reports/quant/forward.json`, `reports/quant/pre_period.json`, `reports/quant/xs7.json`, `reports/replay/*`, `reports/intel_study.md`.
- Paper ledger of bot #2 since 2026-10-24; bot #1 paper journal (no paper trades yet).
- No testimonials, users, or performance claims beyond these files may be invented.

## Product Principles

1. Truth over comfort: show losses, drawdowns and uncertainty as prominently as gains.
2. State first: a glance must answer "is it running, in which mode, what did it last do".
3. Real money is a deliberate act: arming live trading is explicit, explained, reversible.
4. Every chart can be traced to the data and the test that produced it.
5. Research is a first-class workflow, not a hidden admin page.

## Accessibility & Inclusion

Ukrainian UI copy. Numbers in tabular figures; profit/loss never communicated by color alone (sign and text too).
