# Design

<!-- impeccable:design-schema 1 -->

The control room is a fresh edition of a **market page** (біржова сторінка): the bots reported like listed
securities, in dense agate tables and word-sized charts, on newsprint and carbon ink. Chosen by the operator
from the direction page (`.impeccable/decision-direction.json`, option «Біржова сторінка»).

## Principles in pixels

- **State first.** Every bot column opens with name → state line (dot, mode, uptime, PID) → one hero figure →
  four agate rows → a word-sized chart → the last thing it did → its controls. Both columns share these bands.
- **Truth over comfort.** Losses are printed as prominently as gains; charts never auto-zoom a small move into a
  crash (equity scales span at least ±5 % of the start, the start is always drawn as a dashed line).
- **Direction is never color alone.** Signed figures carry sign, ▲/▼ and ink together. Sign and color are computed
  from the same rounding (`tone(value, digits)`), so `−0,004` never prints `0,00 %` in red.
- **Real money is a signed ticket.** Live controls are amber, sit at the far end of the button row away from
  «Зупинити», open a dialog that states the bot's real limits (read from settings, not hard-coded), focuses
  «Лишити папір», and needs the typed phrase `LIVE <BOT>`.

## Type

| role | face | notes |
|---|---|---|
| headlines, masthead, nav, sub-heads | **Fira Sans Extra Condensed** 700/800/900 | condensed grotesque of the FF Meta lineage |
| text, tables, buttons, inputs | **Fira Sans** 400/500/600/700 | `tnum` + `lnum` in `.num` and `.agate` |
| logs, code | JetBrains Mono | |

Rejected: Archivo and Public Sans have no Cyrillic; **Sofia Sans renders Bulgarian letterforms by default**
(т like *m*, д like *g*, и like *u*) and keeps standard forms only under a `RUS` `locl` that `lang="uk"` never
selects. Any replacement face must pass: Cyrillic + Cyrillic-ext subsets, no `locl` substitution needed for
standard Ukrainian forms, `tnum` present, glyphs for `ІіЇїЄєҐґ’«»—–№×−`.

Hangul and CJK in exchange headlines fall back to Apple SD Gothic Neo / Noto Sans KR / PingFang SC.

## Color

Two editions, switched instantly (transitions are suspended during the swap).

| token | day | night | use |
|---|---|---|---|
| `--paper` | `#f2f2ee` | `#121311` | page |
| `--shade` | `#e7e7e1` | `#1b1c19` | hover, log panes |
| `--ink` | `#141414` | `#e9e9e3` | text, active tabs |
| `--ink-2` | `#45453f` | `#b5b5ac` | secondary text |
| `--ink-3` | `#5f5f58` | `#8c8c84` | captions, meta (≥ 4.5:1 on paper) |
| `--rule` | `#bfbfb4` | `#34352f` | hairlines |
| `--heavy` | `= --ink` | `#a3a39a` | heavy and double rules |
| `--gain` / `--loss` | `#0a7445` / `#b3261e` | `#3dba7f` / `#f26a56` | signed figures only |
| `--live` | `#8f5000` | `#f0a33a` | real-money controls and states only |
| `--notice` | `#1d3d9f` | `#8aa2ff` | bot #1 «Анонси» section color |
| `--quant` | `#69308c` | `#c896e6` | bot #2 «Квант» section color |

Bot colors run through headings, tape markers, charts and wet-ink highlights. Fills are flat tints (two-ink print):
no gradients.

## Components

- **Masthead** — dateline, Kyiv and UTC clocks, edition switch (Денний | Нічний, `aria-pressed`), title, system
  status with data freshness («оновлено N с тому», red after 20 s or on a lost connection), section nav.
- **BotColumn** — the bot band described above; `heading={false}` on the bot's own page (the page H1 names it).
- **KV / `.agate`** — ruled tables, right-aligned figures, condensed sub-head rows («Лонги · 30»).
- **EventTape** — newest first, bot square + label + UTC time, a title clamped to three lines, then the detail line
  with the signed amount at its right. All wording comes from `describeEvent()`; the API sends facts only.
- **Spark** — word-sized line with baseline, observations dotted while the series is short, flat 10 % fill.
- **DayBars** — notices per day: grey for all, the bot color for those with a tradable event, legend above, dates below.
- **TimeChart** — lightweight-charts in the page's ink: Ukrainian axis labels, cents on dollar scales, optional
  dashed baseline and minimum range, `underwater` drawdown filled from zero.
- **EvidenceChart** — the 2021–2026 equity on a log scale with one band per evidence period.
- **LiveArm** — the real-money dialog.

## Numbers and words

- `$1 000,00`, `+13,2 %`, `−$1,29` (true minus), `1,93×`, thousands with a no-break space, dates in UTC with the
  zone printed.
- Prices take the precision of their magnitude (≥ 1000 → 1 decimal, ≥ 100 → 2, ≥ 1 → 3, else 4 significant); a row's
  price reuses its entry's precision.
- Playbook shorthand is read out in Ukrainian («шорт 10× тримати 10 хв стоп 5 % тейк 10 %»); event types, exit
  reasons and job states have Ukrainian labels; raw identifiers never reach the page.

## Motion

- New tape lines and changed figures arrive in **wet ink**: the bot color fades out over 7 s (2.5 s with reduced
  motion), new tape lines press in from 6 px above.
- No other decorative motion. Running jobs show a thin indeterminate bar (static under reduced motion).

## Layout

12-column grid, max 1480 px. Front page: bots 4 + 5 columns with the book under them, the tape in the last 3
columns (no inner scroll; «Ще події» extends it), evidence strip full width. Mobile: one column, nav wraps,
buttons and fields at least 40 px tall.
