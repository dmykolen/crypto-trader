import { useQuery } from "@tanstack/react-query"
import clsx from "clsx"
import { ArrowUpRight, Search } from "lucide-react"
import { useMemo, useState, type ReactNode } from "react"
import { Link, useSearchParams } from "react-router-dom"

import { ErrorNote, Signed } from "../components/Print"
import { TimeChart, type SeriesSpec } from "../components/TimeChart"
import { Dock, ModeChip, Odometer, Panel, Pulse, Skeleton, Tip } from "../components/ui"
import { api } from "../lib/api"
import { fmt, ticker, when } from "../lib/format"
import { useEvidence, useLedger, useOverview } from "../lib/hooks"
import type { LedgerRow, LimitTest, LimitVerdict, QuantLedger, QuantPosition, Why, WhyGroup } from "../lib/types"
import { Loading, Page } from "./Overview"

const PANELS = [
  { id: "quant.positions", title: "Позиції" },
  { id: "quant.chart", title: "Графік" },
  { id: "quant.why", title: "Чому" },
  { id: "quant.risk", title: "Ризик" },
  { id: "quant.history", title: "Ребаланси" },
  { id: "quant.limits", title: "Тест лімітних ордерів" },
]

const GROUP: Record<WhyGroup, string> = {
  trend: "Тренд",
  momentum: "Ріст і падіння за останні дні",
  overbought: "Перекупленість",
  volatility: "Коливання ціни",
  volume: "Обсяг і ліквідність",
  funding: "Фандінг",
  btc: "Зв'язок із BTC",
  patterns: "Фігури на графіку",
  regime: "Характер руху",
  time: "День тижня й година",
  other: "Інше",
}

const FRAMES = [
  { key: "1h", label: "1 год", hours: 24 * 14 },
  { key: "4h", label: "4 год", hours: 24 * 60 },
  { key: "1d", label: "1 день", hours: 24 * 120 },
] as const

const VERDICT: Record<LimitVerdict, string> = {
  collecting: "Ще збираю дані.",
  cheaper: "Лімітні ордери дешевші.",
  dearer: "Лімітні ордери дорожчі.",
  unclear: "Різниці не видно.",
}

const pct = (v: number | null | undefined, digits = 1) => fmt.pctPlain(v == null ? null : 100 * v, digits)

function Positions({ positions, ranks, selected, onSelect }: { positions: QuantPosition[]; ranks: Record<string, { rank: number; of: number }>; selected: string; onSelect: (s: string) => void }) {
  const [query, setQuery] = useState("")
  const rows = positions.filter((p) => ticker(p.symbol).toLowerCase().includes(query.trim().toLowerCase()))
  return (
    <div className="flex h-full min-h-0 flex-col">
      <label className="mx-3 mb-2 flex h-8 flex-none items-center gap-2 rounded-lg border border-line bg-bg px-2.5 text-text-3 focus-within:border-line-strong">
        <Search size={13} aria-hidden />
        <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Монета" className="min-w-0 flex-1 bg-transparent text-[12.5px] text-text outline-none placeholder:text-text-3" />
      </label>
      <div className="min-h-0 flex-1 overflow-auto">
        <table className="w-full text-[12.5px]">
          <thead className="sticky top-0 z-10 bg-panel text-[11.5px] text-text-3">
            <tr>
              <th className="px-3 py-1.5 text-left font-medium">Монета</th>
              <th className="py-1.5 text-right font-medium">Частка</th>
              <th className="py-1.5 text-right font-medium">З ребалансу</th>
              <th className="px-3 py-1.5 text-right font-medium">
                Місце <Tip align="end">Місце монети в рейтингу бота на день ребалансу: 1 — найсильніша. Лонги беруться з верху рейтингу, шорти — з низу; монета лишається в портфелі кілька днів, тож місце могло змінитися.</Tip>
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((p) => {
              const r = ranks[p.symbol]
              return (
                <tr
                  key={p.symbol}
                  onClick={() => onSelect(p.symbol)}
                  className={clsx("cursor-pointer border-y transition-colors", selected === p.symbol ? "border-line-strong bg-raised" : "border-transparent hover:bg-raised")}
                  aria-selected={selected === p.symbol}
                >
                  <td className="px-3 py-1.5">
                    <span className="font-semibold">{ticker(p.symbol)}</span> <span className={clsx("text-[11.5px]", p.side === "long" ? "text-gain" : "text-loss")}>{p.side === "long" ? "лонг" : "шорт"}</span>
                  </td>
                  <td className="num py-1.5 text-right text-text-2">{fmt.pctPlain(100 * Math.abs(p.weight), 2)}</td>
                  <td className="py-1.5 text-right">
                    <Signed value={p.pnl} arrow={false}>
                      {fmt.pnl(p.pnl)}
                    </Signed>
                  </td>
                  <td className="num px-3 py-1.5 text-right text-text-2" title={r ? `${r.rank} з ${r.of}` : undefined}>{r ? r.rank : "—"}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function Chart({ symbol, book }: { symbol: string; book: QuantLedger }) {
  const [frame, setFrame] = useState<(typeof FRAMES)[number]>(FRAMES[0])
  const klines = useQuery({ queryKey: ["klines", symbol, frame.key], queryFn: () => api.klines(symbol, frame.key, frame.hours), refetchInterval: 60_000 })
  const position = book.positions.find((p) => p.symbol === symbol)
  const series = useMemo<SeriesSpec[]>(() => {
    const bars = klines.data?.bars ?? []
    const first = bars[0]?.[0] ?? 0
    const markers = book.history
      .filter((h) => h.trades?.[symbol] && Date.parse(h.rebalanced_at) >= first)
      .map((h) => {
        const change = h.trades?.[symbol] ?? 0
        const step = frame.key === "1h" ? 3600 : frame.key === "4h" ? 14400 : 86400
        return { time: Math.floor(Date.parse(h.rebalanced_at) / 1000 / step) * step, position: change > 0 ? ("belowBar" as const) : ("aboveBar" as const), color: change > 0 ? "var(--gain)" : "var(--loss)", shape: change > 0 ? ("arrowUp" as const) : ("arrowDown" as const), text: `${change > 0 ? "+" : "−"}${fmt.pctPlain(100 * Math.abs(change), 1)}` }
      })
    return [{ kind: "candles", data: bars.map(([t, o, h, l, c]) => ({ time: Math.floor(t / 1000), open: o, high: h, low: l, close: c })), markers, priceLines: position ? [{ price: position.entry, title: "ребаланс" }] : [] }]
  }, [klines.data, book.history, symbol, frame.key, position])
  return (
    <div className="px-3 pb-3">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <span className="text-[15px] font-semibold">{ticker(symbol)}</span>
        {position ? (
          <span className={clsx("chip", position.side === "long" ? "border-gain text-gain" : "border-loss text-loss")}>
            {position.side === "long" ? "лонг" : "шорт"} {fmt.pctPlain(100 * Math.abs(position.weight), 2)} · {fmt.usd(position.notional)}
          </span>
        ) : (
          <span className="chip">не в портфелі</span>
        )}
        {position?.price != null && <span className="num text-[12.5px] text-text-2">ціна {fmt.price(position.price)}</span>}
        <span className="ml-auto flex rounded-lg border border-line p-0.5" role="group" aria-label="Таймфрейм">
          {FRAMES.map((f) => (
            <button key={f.key} type="button" onClick={() => setFrame(f)} aria-pressed={frame.key === f.key} className={clsx("h-6 rounded-md px-2.5 text-[12px] transition-colors", frame.key === f.key ? "bg-press text-text" : "text-text-3 hover:text-text")}>
              {f.label}
            </button>
          ))}
        </span>
      </div>
      {klines.isLoading ? <Skeleton className="h-[340px]" /> : klines.data?.bars.length ? <TimeChart series={series} height={340} label={`Свічки ${ticker(symbol)}`} /> : <p className="py-16 text-center text-[13px] text-text-3">Немає котирувань.</p>}
      <p className="mt-1.5 flex items-center gap-1.5 text-[12px] text-text-3">
        ▲ докупив · ▼ скоротив на ребалансі, пунктир — ціна останнього ребалансу
        <Tip align="start">Угоди по кожній монеті бот записує з ребалансу 30.10.2026; раніших позначок немає. Стопів і тейків у Кванта немає: позиції змінюються лише раз на добу.</Tip>
      </p>
    </div>
  )
}

function RankBars({ history }: { history: Why["history"] }) {
  return (
    <div className="flex h-14 items-end gap-1" aria-label="Місце в рейтингу по днях">
      {history.map((h) => (
        <span key={h.day} className="group relative flex h-full flex-1 items-end" title={`${when.dayShort(h.day)}: ${h.rank} з ${h.of}${h.weight ? ` · ${h.weight > 0 ? "лонг" : "шорт"} ${fmt.pctPlain(100 * Math.abs(h.weight), 1)}` : ""}`}>
          <span className={clsx("grow-y w-full rounded-[3px] opacity-70 transition-opacity group-hover:opacity-100", h.weight > 0 ? "bg-gain" : h.weight < 0 ? "bg-loss" : "bg-line-strong")} style={{ height: `${Math.max(6, 100 * (1 - (h.rank - 1) / h.of))}%` }} />
        </span>
      ))}
    </div>
  )
}

function WhyPanel({ symbol, day }: { symbol: string; day?: string }) {
  const why = useQuery({ queryKey: ["quant-why", symbol, day], queryFn: () => api.quantWhy(symbol, day), staleTime: 300_000, retry: false })
  if (why.isLoading)
    return (
      <div className="space-y-2 p-3.5">
        <Skeleton className="h-8 w-40" />
        <Skeleton className="h-14" />
        <p className="text-[12px] text-text-3">Рахую, до хвилини…</p>
      </div>
    )
  if (!why.data) return <div className="p-3.5">{why.error ? <ErrorNote error={why.error} /> : null}</div>
  const w = why.data
  const prev = w.history[w.history.length - 2]
  const max = Math.max(0.01, ...w.factors.map((f) => Math.abs(f.value)))
  const total = Math.max(0.01, w.factors.reduce((s, f) => s + Math.abs(f.value), 0))
  return (
    <div className="p-3.5">
      {w.rank == null ? (
        <p className="text-[13px] text-text-2">
          {ticker(symbol)} не пройшла відбір того дня
          <Tip>Бот бере монети з оборотом від $10 млн на день і помітним рухом ціни.</Tip>
        </p>
      ) : (
        <>
          <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <span className="display text-[30px] leading-none font-semibold">
              {w.rank}
              <span className="text-[16px] font-medium text-text-3"> з {w.of}</span>
            </span>
            {prev && <span className="text-[12.5px] text-text-2">учора {prev.rank}</span>}
            <span className={clsx("chip", w.weight > 0 ? "border-gain text-gain" : w.weight < 0 ? "border-loss text-loss" : "")}>{w.weight > 0 ? `лонг ${pct(w.weight)}` : w.weight < 0 ? `шорт ${pct(-w.weight)}` : "не в портфелі"}</span>
          </div>
          <p className="mt-1 text-[12px] text-text-3">
            рішення {when.dateTime(w.decided_at)} · модель на 48 год: краща за {pct(w.edge_pct, 0)} монет · модель на 7 днів: за {pct(w.xs_pct, 0)}
          </p>
          <div className="mt-3">
            <RankBars history={w.history} />
          </div>
          <ul className="mt-4 space-y-2">
            {w.factors.map((f) => (
              <li key={f.group} className="grid grid-cols-[minmax(0,11rem)_1fr_3.5rem] items-center gap-3 text-[12.5px]" title={f.top.map((t) => `${t.feature}: ${t.value > 0 ? "+" : ""}${t.value}`).join("\n")}>
                <span className="truncate text-text-2">{GROUP[f.group]}</span>
                <span className="relative h-2.5 rounded-full bg-raised">
                  <span className="absolute top-0 left-1/2 h-full w-px bg-line-strong" aria-hidden />
                  <span
                    className={clsx("absolute top-0 h-full rounded-full", f.value >= 0 ? "bg-gain" : "bg-loss")}
                    style={f.value >= 0 ? { left: "50%", width: `${(50 * f.value) / max}%` } : { right: "50%", width: `${(50 * -f.value) / max}%` }}
                  />
                </span>
                <span className={clsx("num text-right", f.value >= 0 ? "text-gain" : "text-loss")}>
                  {f.value >= 0 ? "+" : "−"}
                  {fmt.pctPlain((100 * Math.abs(f.value)) / total, 0)}
                </span>
              </li>
            ))}
          </ul>
          <p className="mt-3 flex items-center gap-1.5 text-[12px] text-text-3">
            {w.source === "recorded" ? "записано ботом" : "відтворено з цін, які бот зберіг"} під час ребалансу {when.dateTime(w.rebalanced_at)}
            <Tip align="start">
              Праворуч (+) — група показників підняла монету в рейтингу, ліворуч (−) — опустила. Відсоток — частка цієї групи в усьому впливі. Пораховано тими самими моделями й цінами, що були в бота. Наведіть на рядок, щоб побачити три найсильніші показники групи.
            </Tip>
          </p>
        </>
      )}
    </div>
  )
}

function worstDay(days: string[], equity: number[]): { day: string; ret: number } | null {
  let worst: { day: string; ret: number } | null = null
  for (let i = 1; i < equity.length; i++) {
    const ret = (equity[i] as number) / (equity[i - 1] as number) - 1
    if (!worst || ret < worst.ret) worst = { day: days[i] as string, ret }
  }
  return worst
}

function Risk({ book }: { book: QuantLedger }) {
  const overview = useOverview()
  const evidence = useEvidence()
  const worst = evidence.data ? worstDay(evidence.data.days, evidence.data.equity) : null
  const top = [...book.positions].sort((a, b) => Math.abs(b.weight) - Math.abs(a.weight)).slice(0, 3)
  const kill = overview.data?.system.risk.quant.kill_drawdown
  const rows: [string, ReactNode, string?][] = [
    ["Плече портфеля", <span className="num">{fmt.times(book.gross)}</span>, "Сума всіх позицій, лонгів і шортів, поділена на рахунок."],
    ["Найбільші позиції", <span className="num">{top.map((p) => `${ticker(p.symbol)} ${fmt.pctPlain(100 * Math.abs(p.weight), 1)}`).join(" · ")}</span>, "BTC великий, бо врівноважує залежність портфеля від ринку."],
    ["Межа одного шорту", "4 % рахунку", "Новий шорт заборонено на монету, що за 7 днів виросла понад 50 %."],
    ["Стоп-лоси", "немає", "Позиції змінюються лише раз на добу, на ребалансі. Шорт на 4 % монети, що за добу виросте втричі, — це −8 % рахунку."],
    ["Найгірший день на історії", worst ? <Signed value={100 * worst.ret}>{`${fmt.pct(100 * worst.ret)} · ${when.day(worst.day)}`}</Signed> : "—", "Тест бота на 2021–2026 роках, не справжня торгівля."],
    ["Реальні гроші", kill ? `запобіжник −${fmt.pctPlain(100 * kill, 0)} від максимуму` : "—", "Версія на реальні гроші закриває всі позиції й зупиняється, якщо рахунок упаде на цю частку від свого максимуму."],
    ["Таймфрейм", "свічки 1 год · рішення раз на добу", "Рейтинг о 23:00 UTC, угоди о 00:15 UTC; моделі прогнозують на 48 годин і 7 днів."],
  ]
  return (
    <dl className="divide-y divide-line">
      {rows.map(([k, v, tip]) => (
        <div key={k} className="flex items-center justify-between gap-3 px-3.5 py-2 text-[12.5px]">
          <dt className="flex items-center gap-1.5 text-text-2">
            {k}
            {tip && <Tip align="start">{tip}</Tip>}
          </dt>
          <dd className="text-right font-medium">{v}</dd>
        </div>
      ))}
    </dl>
  )
}

function History({ rows }: { rows: LedgerRow[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="agate min-w-[640px] px-3.5">
        <thead>
          <tr>
            <th className="pl-3.5">День</th>
            <th className="r">За добу</th>
            <th className="r">Фандінг</th>
            <th className="r">Витрати</th>
            <th className="r">Обіг</th>
            <th className="r">Угод</th>
            <th className="r pr-3.5">Рахунок</th>
          </tr>
        </thead>
        <tbody>
          {[...rows].reverse().map((h) => (
            <tr key={h.rebalanced_at}>
              <td className="num pl-3.5">{when.dateTime(h.rebalanced_at)}</td>
              <td className="r">
                <Signed value={h.pnl_since_last} arrow={false}>
                  {fmt.pnl(h.pnl_since_last)}
                </Signed>
              </td>
              <td className="r num">{h.funding_paid == null ? "—" : fmt.pnl(-h.funding_paid)}</td>
              <td className="r num">{fmt.usd(h.cost)}</td>
              <td className="r num">{fmt.times(h.turnover)}</td>
              <td className="r num">{h.trades ? Object.keys(h.trades).length : "—"}</td>
              <td className="r num pr-3.5 font-semibold">{fmt.usd(h.equity)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function Limits({ t }: { t: LimitTest }) {
  const cost = (v: number | undefined) => fmt.pctPlain(v == null ? null : 100 * v, 3)
  const rows: [string, ReactNode, string?][] = t.orders
    ? [
        ["Виміряно ордерів", `${fmt.int(t.orders)} з ${fmt.int(t.enough)} · днів ${t.days}`],
        ["Виконались би лімітні", `${fmt.pctPlain(100 * (t.filled_through ?? 0), 0)}`, "Частка суми ордерів, через ціну яких пройшли справжні угоди біржі за 30 хвилин."],
        ["Ринковий коштує", `${cost(t.market_cost)}`, `З них проковзування ${cost(t.market_slippage)}.`],
        ["Лімітний коштує", `${cost(t.limit_cost_through)}`],
        ["Економія на ордер", <Signed value={100 * (t.saving ?? 0)} digits={3}>{`${fmt.pct(100 * (t.saving ?? 0), 3)} ± ${cost(t.saving_se == null ? undefined : 2 * t.saving_se)}`}</Signed>, "± — дві похибки, пораховані по днях."],
      ]
    : []
  return (
    <div>
      {rows.length ? (
        <dl className="divide-y divide-line">
          {rows.map(([k, v, tip]) => (
            <div key={k} className="flex items-center justify-between gap-3 px-3.5 py-2 text-[12.5px]">
              <dt className="flex items-center gap-1.5 text-text-2">
                {k}
                {tip && <Tip align="start">{tip}</Tip>}
              </dt>
              <dd className="text-right font-medium">{v}</dd>
            </div>
          ))}
        </dl>
      ) : (
        <p className="px-3.5 py-3 text-[12.5px] text-text-3">Перший вимір — після ребалансу о 00:15 UTC.</p>
      )}
      <p className="flex items-center gap-1.5 border-t border-line px-3.5 py-2.5 text-[12.5px] font-medium">
        {VERDICT[t.verdict]}
        <Tip align="start">
          Після кожного ребалансу бот уявно ставить ті самі ордери лімітними й 30 хвилин дивиться, чи виконались би вони. Справжніх ордерів не ставить. Висновок — після {fmt.int(t.enough)} ордерів і {t.min_days} днів.
        </Tip>
      </p>
    </div>
  )
}

export function QuantBot() {
  const overview = useOverview()
  const ledger = useLedger()
  const [params, setParams] = useSearchParams()
  const ranks = useQuery({ queryKey: ["quant-ranks"], queryFn: () => api.quantRanks(), staleTime: 300_000, retry: false })
  const limits = useQuery({ queryKey: ["quant-limit-test"], queryFn: api.quantLimitTest, refetchInterval: 60_000 })
  if (ledger.isLoading || overview.isLoading)
    return (
      <Page>
        <Loading what="портфель" />
      </Page>
    )
  const book = ledger.data && ledger.data.started ? (ledger.data as QuantLedger) : null
  const bot = overview.data?.bots.find((b) => b.key === "quant")
  if (!book)
    return (
      <Page>
        <p className="py-10 text-center text-[13px] text-text-3">Рахунок ще не відкрито: запустіть Квант у «Процесах».</p>
      </Page>
    )
  const largest = [...book.positions].sort((a, b) => Math.abs(b.weight) - Math.abs(a.weight)).find((p) => p.symbol !== "BTCUSDT")
  const symbol = (params.get("symbol") ?? largest?.symbol ?? "BTCUSDT").toUpperCase()
  const select = (s: string) => setParams({ symbol: s }, { replace: true })
  return (
    <Page>
      <div className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-2">
        <h1 className="text-[20px] font-semibold tracking-[-0.01em]">Квант</h1>
        {bot && (
          <span className="flex items-center gap-2 text-[12.5px] text-text-2">
            <Pulse state={bot.running ? "on" : "off"} beat={bot.last_log_at} />
            {bot.running ? `працює ${when.duration(bot.uptime_s)}` : "зупинений"}
            <ModeChip live={bot.running && bot.mode === "live"} />
          </span>
        )}
        <span className="flex items-baseline gap-2">
          <Odometer text={fmt.usd(book.equity_now)} className="display text-[22px] font-semibold" />
          <Signed value={book.return_now_pct}>{fmt.pct(book.return_now_pct)}</Signed>
        </span>
        <Link to="/processes" className="btn btn-quiet ml-auto h-8 px-2.5 text-[12.5px] no-underline">
          Керувати <ArrowUpRight size={13} aria-hidden />
        </Link>
      </div>
      <Dock panels={PANELS} />
      <div className="grid items-start gap-3 lg:grid-cols-12">
        <Panel
          id="quant.positions"
          title="Позиції"
          index={0}
          className="h-[480px] lg:col-span-4 lg:row-span-2 lg:h-0 lg:min-h-full"
          wideClass="h-[520px] lg:col-span-12"
          foldClass="h-auto! lg:min-h-0! lg:row-span-1!"
          bodyClass="min-h-0 flex flex-col"
          summary={`${book.positions.length} · плече ${fmt.times(book.gross)}`}
        >
          <Positions positions={book.positions} ranks={ranks.data?.ranks ?? {}} selected={symbol} onSelect={select} />
        </Panel>
        <Panel id="quant.chart" title="Графік" index={1} className="lg:col-span-8" summary={ticker(symbol)}>
          <Chart symbol={symbol} book={book} />
        </Panel>
        <Panel id="quant.why" title={`Чому ${ticker(symbol)}`} index={2} className="lg:col-span-8" summary="місце в рейтингу і що вплинуло">
          <WhyPanel symbol={symbol} />
        </Panel>
        <Panel id="quant.risk" title="Ризик" index={3} className="lg:col-span-4" summary={`плече ${fmt.times(book.gross)} · стопів немає`}>
          <Risk book={book} />
        </Panel>
        <Panel id="quant.history" title="Ребаланси" index={4} className="lg:col-span-4" wideClass="lg:col-span-12" summary={`${book.history.length}`}>
          <History rows={book.history} />
        </Panel>
        <Panel id="quant.limits" title="Тест лімітних ордерів" index={5} className="lg:col-span-4" summary={limits.data ? VERDICT[limits.data.verdict] : undefined}>
          {limits.data ? <Limits t={limits.data} /> : <Skeleton className="m-3.5 h-16" />}
        </Panel>
      </div>
    </Page>
  )
}
