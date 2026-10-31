# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Вимоги до коду (діють завжди)

- **Елегантність і компактність — скрізь і всюди.** Вираз кращий за пʼятирядковий блок. Код пишеться так, щоб його було легко підтримувати.
- **Коментарі — тільки там, де вони справді потрібні і цінні**, і тільки лаконічні (максимум 1 рядок).
- **Двічі переконайся, що функціоналу справді нема, перш ніж його писати.** Спершу перевір, що
  вже є в цьому репозиторії, потім — що дає вже встановлена бібліотека чи фреймворк. Дублікат
  або власна обгортка над чужим викликом — гірше, ніж нічого не зробити.

## Документація і беклог (діють завжди)

Уся документація — у `docs/`. У корені лишаються тільки `README.md` і `CLAUDE.md`, новий документ теж іде в `docs/`.

| Файл | Що там | Коли оновлювати |
|---|---|---|
| `docs/BACKLOG.md` | Єдиний список усього, що треба зробити: баги, покращення, ідеї, дослідження, рішення власника | Щойно в розмові чи роботі з'явилась ідея, баг чи покращення — одразу новий рядок; зроблене — статус і дата |
| `docs/ARCHITECTURE.md` | Архітектура: Mermaid-діаграми й таблиці | Коли змінюються процеси, потоки даних, сторінки пульта чи файли в `data/` |
| `docs/RESEARCH.md` | Журнал гіпотез (H — бот №1, I — ідеї, Q — бот №2) з результатами; його цитують README і сторінка «Докази» | Після кожної серії експериментів: гіпотеза, результат, висновок |
| `docs/AUDIT.md` | Аудит 2026-10-28: дефекти з file:line і план виправлень | Читати перед зміною логіки ботів, чисел доказів чи реальних виконавців |
| `docs/PRODUCT.md`, `docs/DESIGN.md` | Продукт і дизайн-система пульта (`.impeccable` знаходить їх у `docs/`) | Коли змінюється продукт чи візуальні правила |

- **Файли в `docs/` завжди актуальні.** Зміна, що зачіпає зміст документа, оновлює його в тій самій роботі, а не
  «потім». Застаріле, помічене мимохідь, виправляй одразу.
- Задачі й «треба доробити» записуй тільки в `docs/BACKLOG.md`, не в RESEARCH, AUDIT чи нотатки пам'яті. Перед новою
  задачею глянь беклог: якщо вона там є, онови рядок, а не дублюй. Формат і пріоритети — на початку самого файлу.
- Документи пиши українською, простими словами для розробника, який прийшов тиждень тому; перевага — Mermaid і таблицям.

## Кінець кожної відповіді (діє завжди)

Кожна відповідь закінчується топ-5 пропозиціями, куди йти далі. Кожна несе суттєву цінність для застосунку й наближає
до стабільного, безперебійного заробітку. Бери їх із `docs/BACKLOG.md`, а нову ідею спершу запиши туди.

## What this is

Research and trading for Binance USDⓈ-M perpetuals: two bots, a news-intelligence module and a localhost web
control room. Everything defaults to paper trading.

- **Bot #1 «Анонси» (`notice`)** — Binance / Upbit announcements → rule classifier → a playbook learned
  walk-forward → a leveraged trade on the token's perpetual. Code in `services/` + `integrations/`.
- **Bot #2 «Квант» (`quant`)** — once a day a market-neutral book (30 long / ≤30 short, shorts ≤ 4 %, no new short on
  a token up > 50 % in 7 days, BTC beta hedge, 2x gross, 1 % rebalance band) ranked by two LightGBM models over all
  liquid perps. Code in `quant/`. Single-pair timing (305 tactics in `quant/tactics.py`) was tested and loses out of
  sample (RESEARCH Q43–Q44); it lives on only as the pair lab.
- **Intel (`intel/`)** — media RSS, exchange boards, Reddit, positioning, attention → hourly per-perp signals via
  `intel.signals.features(symbol, start, end)`. No bot consumes these signals yet.
- **Web control room (`web/`)** — React 19 + Vite + Tailwind 4 SPA, built to `web/dist` and served by `trader serve`.

## Commands

```bash
uv sync && uv run prek install --prepare-hooks
uv run pytest                                      # whole suite, ~35 s
uv run pytest tests/test_trading.py -q             # one file
uv run pytest tests/test_trading.py::test_name -q  # one test
uv run ruff check . && uv run ruff format --check .
uv run prek run --all-files                        # the only CI job (.gitlab-ci.yml)

cd web && pnpm install && pnpm build               # trader serve only serves the built web/dist
cd web && pnpm dev                                 # hot reload on :5173, proxies /api to :8710
cd web && pnpm typecheck && pnpm test              # tsc + vitest
```

Running things (`trader --help`, `trader quant|intel|research --help` list everything):

```bash
uv run trader serve                           # API + UI on http://127.0.0.1:8710
uv run trader run                             # bot #1 loop
uv run trader quant paper --loop              # bot #2 paper loop, rebalances 00:15 UTC
uv run trader status                          # both bots' paper records
uv run trader replay 2026-10-22 --days 30     # the real bot #1 loop over past days
uv run trader quant book 2026-09-29           # bot #2 book held on a day
uv run trader quant forward 2026-10-01        # bot #2 on days no model saw (fresh REST quotes)
uv run trader quant day SOLUSDT 2026-10-27    # pair lab: 305 tactics on one pair/day (--days, --csv, --leverage)
uv run trader quant tactics                   # per-token walk-forward tactic study, all perps, ~30 s
uv run trader quant limits                    # shadow test of limit orders vs market orders on the paper rebalances
```

`trader research events|ticks`, `trader quant research|retrain` and `trader intel backfill` download archives from
data.binance.vision and run for minutes to hours; run them in the background.

Tests never touch the network or the dev journal: `tests/conftest.py` points `DATABASE_URL`, `DATA_DIR` and
`REPORTS_DIR` at a temp dir before `trader` is imported, and the `client` fixture already sends `X-Trader-UI: 1`.
That temp DB is shared by the whole session, so rows from one test file leak into the next (`test_api.py` fails
when run after `test_ui_*`).

## Architecture

Diagrams and tables of the whole system: `docs/ARCHITECTURE.md`. The layout follows the team scaffold (`core/ models/ services/ integrations/ ai/ transports/ main.py`) with two
self-contained feature packages beside it, `quant/` and `intel/`, each with its own Typer `cli.py` that
`transports/cli.py` mounts. `bots.py` is the bot registry, `status.py` the paper summary.

**Settings** (`core/config.py`) are a module-level singleton `settings` read once from env / `.env`. Some CLI
commands mutate it at runtime (`research events --latency-s`), and subprocesses receive overrides through env
(`TRADING_MODE`).

**State on disk** — all under gitignored `data/` and `reports/` (only top-level `reports/*.md|*.json` are tracked):

| path | what | written by |
|---|---|---|
| `data/trader.db` | SQLite: `NewsItem` (every notice and media item), `Trade` (journal, `mode` = paper / live / replay), `IntelSignal` | bots, `backfill`, `intel` |
| `data/playbooks.json` | slow-path playbook per event type | `trader research events` |
| `data/fast_playbooks.json` | playbooks per event type and latency bucket (0.5…5 s) | `trader research ticks` |
| `data/klines`, `funding`, `ticks`, `universe/` | parquet caches of Binance archives | `services/market_data.py`, `ticks.py`, `universe.py` |
| `data/quant/` | feature panel, predictions, `models/` (walk-forward, final, archived finals per quarter), `paper/ledger.json` (each history row carries its `trades` and, from 2026-11-01, the held `book`), `paper/limit_orders.jsonl` (limit-order shadow test), `live/` (REST bar caches, `forward_book.parquet`), `book_history.parquet` (held book 2021-07…2026-09), `tactics/` (per-tactic portfolio returns) | `quant/*`, `evidence.build`, `live.forward`, `tactic_study` |
| `data_pre/` | the separate 2021-07…2023-06 rebuild used as the untouched test period | `quant` with a panel start date |
| `data/run/<bot>.{json,log}`, `data/jobs/*.json`, `data/uploads/<sha16>.csv` | bots and jobs started from the UI, CSV quotes uploaded for the pair lab | `services/processes.py`, `services/jobs.py`, `POST /api/v1/uploads` |

**Bot #1 live path** (`services/trading.py`). `Trader.run` gathers async loops: the slow board poll
(`poll_notices`, 15 s) classifies new notices (`services/events.py`) and schedules an entry at
`published_at + ENTRY_LATENCY_S + playbook delay`; the fast path — Upbit / Binance pollers (1 s / 5 s) or the signed
Binance announcement WebSocket (`integrations/binance_ws.py`, needs API keys) — goes through `on_fast_notice`, which
picks the fast playbook for the latency actually measured (`fast.for_latency`) and skips anything slower than
`FAST_MAX_LATENCY_S`. `monitor` closes on liquidation (paper only) / stop / take-profit / time and ratchets trailing
stops. Risk rails live in `Trader._blocked` and `Trader._margin`. `PaperBroker` fills at the live price plus event
slippage; `LiveBroker` → `integrations/exchange.py` (ccxt `binanceusdm`, isolated margin, reduce-only exchange stop;
take-profit and time exits exist only in the bot). Media RSS goes to Claude (`ai/news_analyst.py`) and trades only
with `LLM_NEWS_TRADING=true`.

**Bot #1 research.** `services/engine.py` is the numba leveraged backtester (next-open fills, gap-through stops,
funding, isolated liquidation); `playbooks.py` + `report.py` grid-search and pick playbooks walk-forward by lower
confidence bound; `ticks.py` + `fast.py` replay aggTrades around each notice for the latency study; `replay.py` drives
the real `Trader` on a simulated clock and historical prices under assumed detection latencies (`SCENARIOS`).
`universe.py`, `lab.py`, `xsection.py` (price events, cross-section) and `strategies.py`, `features.py`,
`forecast.py`, `selection.py` (per-token continuous strategies behind `trader forecast` / `brief`) are research
that found no edge.

**Bot #2 pipeline** (`quant/`). `indicators.py`, `mathx.py`, `patterns.py` (numba kernels) → `features.py` (~135
dimensionless features per 1h bar) → `labels.py` (triple barrier) → `model.py` (quarterly walk-forward LightGBM with a
purge gap; `model_for(day)` returns a model that never saw that day) and `xsmodel.py` (7-day cross-sectional rank
model) → `neutral.py` (blended ranking → `pump_guard` → ensemble of books → 30/side, short cap, beta hedge; `drift`
is the numba backtest that trades from drifted weights past the band with the paper's costs — every book return goes
through it) → `live.py` (fresh
REST quotes → final models → today's book; `forward`) → `paper.py` (JSON ledger written via a temp file, one rebalance per UTC day, then `limit_test.measure` prices the same orders as 30-min post-only limits; retries
every 15 min; after each rebalance `why.build` records each token's factor contributions for the «Чому» panel) or
`live_exec.py` (real orders on cross margin, account drawdown kill switch). `retrain.py` refreshes
data and final models quarterly and archives the replaced finals for the quarter they served. `evidence.py` builds
the evidence periods shown in the UI and writes `book_history.parquet`. `tactics.py` is the single-pair tactic
library (rules over `features.frame` + `services/engine.py` with stop / take / trailing / `cooldown` re-entry);
`tactic_study.py` runs it per token in a process pool; `day.py` is the pair lab behind `trader quant day` and the
`quant_day` job (fresh REST quotes or a CSV, the LightGBM edge from `model_for` per quarter, each tactic's record from
`data/quant/tactics/`, the book's weight from `book_history` / `forward_book`, the whole bot's result for the same
days from the paper ledger or else `evidence.json`). Each tactic's plain-Ukrainian name and explanation come from
`LABELS` / `HOW` / `Overlay.explain` in `tactics.py`; the owner once read the lab as a simulation of the bot, so its
page opens by saying it is not. `sim.py`, `research.py` belong to the
rejected hourly barrier policy (Q01–Q06); `trend.py`'s daily trend portfolios are rejected (Q07) but `load_panel`,
`stats`, `COST` and the period constants there are shared.

Research periods are hard-coded: dev 2023-07…2024-12, holdout 2025-01…2026-09, untouched 2021-07…2023-06. Rule
from Q32: a new variant replaces the production one only if it is better on both dev and holdout.

**Web control room.** `main.py` installs `local_only`: requests whose Host is not localhost get 403 (DNS rebinding),
and mutating `/api/` requests need `X-Trader-UI: 1` (CSRF), which `web/src/lib/api.ts` sends. `transports/http/ui.py`
is the UI API, `api.py` the older JSON API (both under `/api/v1`), `system.py` health / ready / metrics; a catch-all
route serves the SPA. `services/processes.py` starts bots as detached `trader run` / `trader quant paper|live --loop`
with `TRADING_MODE` in their env, and finds running bots by matching `ps` command lines — a bot started from a
terminal shows as running, marked «з терміналу», with no log in the UI. Live mode needs Binance keys plus the typed
phrase `LIVE NOTICE` / `LIVE QUANT`. `services/supervisor.py` backs the «Процеси» page: process inventory with CPU and
memory, log tails and errors, disk use and cache cleanup, the schedule, and the launchd autostart agent that runs
`trader boot` (restores the bots that were running, then serves). `services/jobs.py`: every UI test is a JSON doc in `data/jobs/` executed by a
detached `trader job run <id>`; job kinds are `KINDS` / `RUNNERS`. In `web/src`, `lib/types.ts` mirrors the JSON that
`ui.py` returns (change both together) and `lib/format.ts` does all Ukrainian number and date formatting. Visual rules:
`docs/DESIGN.md`, `docs/PRODUCT.md`; `.impeccable/` is the design tool's state. `trader serve` serves whatever is in `web/dist`,
so a running server picks up a new build but not new API routes; `.claude/launch.json` starts a second server on
:8711 for checking changes without restarting the owner's :8710.

## Rules for this repo

- Text the operator reads is Ukrainian: the UI copy, everything in `docs/`, `bots.py` descriptions. Identifiers, CLI help
  and logs stay English.
- **Real money:** never set `TRADING_MODE=live`, start a bot in live mode, or run `trader quant live` without the
  owner's explicit go-ahead in the chat.
- The bots may already be running (started from a terminal — check `ps` or the UI «Система» page). They share
  `data/trader.db` and `data/quant/paper/ledger.json` with your experiments; never wipe or rewrite those.
- Results must stay honest: decisions walk-forward only, costs always on (0.05 % taker, slippage, funding, isolated
  liquidation), every reported number out-of-sample, losses shown as prominently as gains.
- Changing a numba kernel recompiles it on the next run (`*.nbc` caches in `__pycache__`); the first run is slow.
