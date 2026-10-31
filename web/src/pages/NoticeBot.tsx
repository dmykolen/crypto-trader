import { useQuery } from "@tanstack/react-query"
import clsx from "clsx"
import { ArrowUpRight, ExternalLink } from "lucide-react"
import { useMemo, useState } from "react"
import { Link } from "react-router-dom"

import { DayBars } from "../components/DayBars"
import { Signed } from "../components/Print"
import { TimeChart, type SeriesSpec } from "../components/TimeChart"
import { Dock, ModeChip, Odometer, Panel, Pulse, Skeleton, Tip } from "../components/ui"
import { api } from "../lib/api"
import { eventLabel, exitReason, fmt, playbookText, ticker, triggerParts, when } from "../lib/format"
import { useOverview } from "../lib/hooks"
import type { NoticeItem, Trade } from "../lib/types"
import { Page } from "./Overview"

const PANELS = [
  { id: "notice.feed", title: "Стрічка анонсів" },
  { id: "notice.trades", title: "Угоди" },
  { id: "notice.chart", title: "Графік угоди" },
  { id: "notice.rules", title: "Правила входу" },
  { id: "notice.days", title: "Анонси по днях" },
]

const OUTCOME: Record<NonNullable<NoticeItem["decisions"]>[number]["outcome"], string> = {
  entered: "зайшов",
  scheduled: "вхід заплановано",
  no_rule: "немає правила",
  too_old: "запізнився",
  too_slow: "запізнився",
  no_perp: "немає ф'ючерса",
  blocked: "ліміт ризику",
}

const SOURCE: Record<string, string> = { binance: "Binance", upbit: "Upbit" }
const hhmm = new Intl.DateTimeFormat("uk-UA", { hour: "2-digit", minute: "2-digit", timeZone: "UTC" })

type Summary = {
  playbooks: { fitted_at?: string; types?: Record<string, { describe?: string; playbook: unknown; events: number; win_rate?: number; mean_ret?: number; worst_ret?: number }> }
  fast_playbooks?: { by_latency?: Record<string, Record<string, { describe?: string; playbook: unknown; events: number; oos_trades?: number; oos_mean_ret?: number }>> }
}

function Decision({ d }: { d: NonNullable<NoticeItem["decisions"]>[number] }) {
  const entered = d.outcome === "entered"
  const detail = d.outcome === "scheduled" ? ` о ${hhmm.format(new Date(d.detail))}` : d.outcome === "too_slow" || d.outcome === "too_old" ? ` (${fmt.ratio(Number(d.detail), 1)} с)` : ""
  return (
    <span className={clsx("chip", entered ? "border-text text-text" : "text-text-3")} title={d.detail || undefined}>
      {entered ? "✓ " : ""}
      {ticker(d.token)}: {OUTCOME[d.outcome]}
      {detail}
    </span>
  )
}

function Feed({ items }: { items: NoticeItem[] }) {
  if (!items.length) return <p className="px-3.5 py-6 text-[13px] text-text-3">Анонсів ще не було.</p>
  return (
    <ol className="divide-y divide-line">
      {items.map((n) => (
        <li key={n.id} className="grid grid-cols-[3rem_1fr] gap-x-2 px-3.5 py-2.5">
          <time dateTime={n.published_at} className="display pt-0.5 text-[12px] text-text-3">
            {hhmm.format(new Date(n.published_at))}
          </time>
          <div className="min-w-0">
            <div className="flex min-w-0 items-baseline gap-2">
              <span className="flex-none text-[11px] font-semibold text-text-3">{SOURCE[n.source] ?? n.source}</span>
              {n.url ? (
                <a href={n.url} target="_blank" rel="noreferrer" className="group/a min-w-0 truncate text-[13px] text-text no-underline hover:underline" title={n.title}>
                  {n.title} <ExternalLink size={11} className="inline opacity-0 group-hover/a:opacity-60" aria-hidden />
                </a>
              ) : (
                <span className="min-w-0 truncate text-[13px]">{n.title}</span>
              )}
            </div>
            <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[11.5px] text-text-3">
              {n.events.map((e, i) => (
                <span key={i} className="chip">
                  {eventLabel(e.type)}
                  {e.symbols.length ? `: ${e.symbols.map(ticker).join(", ")}` : ""}
                </span>
              ))}
              <span>побачив за {fmt.ratio(n.latency_s, 1)} с</span>
              {(n.decisions ?? []).map((d, i) => (
                <Decision key={i} d={d} />
              ))}
            </div>
          </div>
        </li>
      ))}
    </ol>
  )
}

function Trades({ trades, selected, onSelect }: { trades: Trade[]; selected?: number; onSelect: (t: Trade) => void }) {
  if (!trades.length) return <p className="px-3.5 py-6 text-[13px] text-text-3">Угод ще не було.</p>
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[520px] text-[12.5px]">
        <thead className="text-[11.5px] text-text-3">
          <tr>
            <th className="px-3.5 py-1.5 text-left font-medium">Монета</th>
            <th className="py-1.5 text-left font-medium">Правило</th>
            <th className="py-1.5 text-left font-medium">Вхід</th>
            <th className="py-1.5 text-left font-medium">Вихід</th>
            <th className="px-3.5 py-1.5 text-right font-medium">P&L</th>
          </tr>
        </thead>
        <tbody>
          {trades.map((t) => {
            const rule = triggerParts(t.trigger)
            return (
              <tr key={t.id} onClick={() => onSelect(t)} className={clsx("cursor-pointer border-y", selected === t.id ? "border-line-strong bg-raised" : "border-transparent hover:bg-raised")}>
                <td className="px-3.5 py-1.5">
                  <b>{ticker(t.symbol)}</b> <span className={t.side > 0 ? "text-gain" : "text-loss"}>{t.side > 0 ? "лонг" : "шорт"}</span> <span className="text-text-3">{fmt.times(t.leverage, 0)}</span>
                </td>
                <td className="max-w-[16rem] truncate py-1.5 text-text-2" title={`${rule.event} · ${rule.playbook}`}>
                  {rule.event}
                </td>
                <td className="num py-1.5 text-text-2">{when.dateTime(t.entry_time)}</td>
                <td className="py-1.5 text-text-2">{t.exit_time ? exitReason(t.exit_reason) : "відкрита"}</td>
                <td className="px-3.5 py-1.5 text-right">
                  {t.pnl == null ? (
                    "—"
                  ) : (
                    <Signed value={t.pnl} arrow={false}>
                      {fmt.pnl(t.pnl)}
                    </Signed>
                  )}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function TradeChart({ trade }: { trade?: Trade }) {
  const end = trade ? new Date(Math.min(Date.now(), Date.parse(trade.exit_time ?? trade.exit_due) + 30 * 60_000)).toISOString() : undefined
  const hours = trade ? Math.max(1, Math.ceil((Date.parse(end as string) - Date.parse(trade.entry_time) + 30 * 60_000) / 3_600_000)) : 1
  const klines = useQuery({ queryKey: ["trade-klines", trade?.id], queryFn: () => api.klines((trade as Trade).symbol, hours > 24 ? "5m" : "1m", hours, end), enabled: Boolean(trade) })
  const series = useMemo<SeriesSpec[]>(() => {
    if (!trade || !klines.data) return []
    const step = hours > 24 ? 300 : 60
    const at = (iso: string) => Math.floor(Date.parse(iso) / 1000 / step) * step
    const markers: NonNullable<SeriesSpec["markers"]> = [
      { time: at(trade.entry_time), position: trade.side > 0 ? "belowBar" : "aboveBar", color: "var(--text)", shape: trade.side > 0 ? "arrowUp" : "arrowDown", text: trade.side > 0 ? "лонг" : "шорт" },
    ]
    if (trade.exit_time && trade.pnl != null) markers.push({ time: at(trade.exit_time), position: trade.side > 0 ? "aboveBar" : "belowBar", color: trade.pnl >= 0 ? "var(--gain)" : "var(--loss)", shape: "circle", text: fmt.pnl(trade.pnl) })
    return [
      {
        kind: "candles",
        data: klines.data.bars.map(([t, o, h, l, c]) => ({ time: Math.floor(t / 1000), open: o, high: h, low: l, close: c })),
        markers,
        priceLines: [
          { price: trade.entry_price, title: "вхід", color: "var(--text-2)" },
          ...(trade.stop_price ? [{ price: trade.stop_price, title: "стоп", color: "var(--loss)" }] : []),
          ...(trade.take_profit_price ? [{ price: trade.take_profit_price, title: "тейк", color: "var(--gain)" }] : []),
        ],
      },
    ]
  }, [trade, klines.data, hours])
  if (!trade) return <p className="px-3.5 py-6 text-[13px] text-text-3">Оберіть угоду в таблиці.</p>
  return (
    <div className="px-3 pb-3">
      <p className="mb-2 text-[12.5px] text-text-2">
        <b className="text-text">{ticker(trade.symbol)}</b> · {triggerParts(trade.trigger).playbook}
      </p>
      {klines.isLoading ? <Skeleton className="h-[300px]" /> : <TimeChart series={series} height={300} label={`Угода ${ticker(trade.symbol)}`} />}
    </div>
  )
}

function Rules({ summary }: { summary?: Summary }) {
  const [bucket, setBucket] = useState("1")
  const slow = Object.entries(summary?.playbooks.types ?? {})
  const fast = summary?.fast_playbooks?.by_latency ?? {}
  return (
    <div>
      <table className="w-full text-[12.5px]">
        <thead className="text-[11.5px] text-text-3">
          <tr>
            <th className="px-3.5 py-1.5 text-left font-medium">Подія</th>
            <th className="py-1.5 text-left font-medium">
              Правило <Tip>Що бот робить після анонсу: бік, плече, коли входить, скільки тримає, стоп і тейк. Правила підібрано на історії й перевірено на днях, яких підбір не бачив.</Tip>
            </th>
            <th className="px-3.5 py-1.5 text-right font-medium">Подій на історії</th>
          </tr>
        </thead>
        <tbody>
          {slow.map(([type, pb]) => (
            <tr key={type} className="border-t border-line">
              <td className="px-3.5 py-1.5">{eventLabel(type)}</td>
              <td className={clsx("py-1.5", pb.playbook ? "text-text" : "text-text-3")}>{pb.playbook ? playbookText(pb.describe) : "не торгує"}</td>
              <td className="num px-3.5 py-1.5 text-right text-text-2">{pb.events}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {Object.keys(fast).length > 0 && (
        <div className="mt-3 border-t border-line">
          <div className="flex items-center gap-2 px-3.5 pt-3 pb-1.5">
            <span className="text-[12.5px] font-medium">Швидкий вхід</span>
            <Tip align="start">Якщо бот бачить анонс за кілька секунд після публікації, він діє за окремими правилами для цієї затримки.</Tip>
            <span className="ml-auto flex rounded-lg border border-line p-0.5" role="group" aria-label="Затримка">
              {Object.keys(fast).map((k) => (
                <button key={k} type="button" onClick={() => setBucket(k)} aria-pressed={bucket === k} className={clsx("h-6 rounded-md px-2 text-[12px]", bucket === k ? "bg-press text-text" : "text-text-3 hover:text-text")}>
                  ≤ {k.replace(".", ",")} с
                </button>
              ))}
            </span>
          </div>
          <table className="w-full text-[12.5px]">
            <tbody>
              {Object.entries(fast[bucket] ?? {}).map(([type, pb]) => (
                <tr key={type} className="border-t border-line">
                  <td className="px-3.5 py-1.5">{eventLabel(type)}</td>
                  <td className={clsx("py-1.5", pb.playbook ? "text-text" : "text-text-3")}>{pb.playbook ? playbookText(pb.describe) : "не торгує"}</td>
                  <td className="num px-3.5 py-1.5 text-right text-text-2">{pb.events}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

export function NoticeBot() {
  const overview = useOverview()
  const [all, setAll] = useState(false)
  const feed = useQuery({ queryKey: ["notice-feed", all], queryFn: () => api.noticeFeed(80, !all), refetchInterval: 15_000 })
  const trades = useQuery({ queryKey: ["notice-trades"], queryFn: () => api.trades(200), refetchInterval: 15_000 })
  const daily = useQuery({ queryKey: ["notice-daily"], queryFn: () => api.noticeDaily(30), staleTime: 300_000 })
  const summary = useQuery({ queryKey: ["notice-summary"], queryFn: () => fetch("/api/v1/notice/summary").then((r) => r.json() as Promise<Summary>), staleTime: 300_000 })
  const [picked, setPicked] = useState<number | undefined>()
  const list = trades.data ?? []
  const trade = list.find((t) => t.id === picked) ?? list[0]
  const bot = overview.data?.bots.find((b) => b.key === "notice")
  const paper = overview.data?.paper.notice
  return (
    <Page>
      <div className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-2">
        <h1 className="text-[20px] font-semibold tracking-[-0.01em]">Анонси</h1>
        {bot && (
          <span className="flex items-center gap-2 text-[12.5px] text-text-2">
            <Pulse state={bot.running ? "on" : "off"} beat={bot.last_log_at} />
            {bot.running ? `працює ${when.duration(bot.uptime_s)}` : "зупинений"}
            <ModeChip live={bot.running && bot.mode === "live"} />
          </span>
        )}
        {paper && (
          <span className="flex items-baseline gap-2">
            <Odometer text={fmt.pnl(paper.realized_pnl)} className="display text-[22px] font-semibold" />
            <span className="text-[12.5px] text-text-3">угод {paper.trades}</span>
          </span>
        )}
        <Link to="/processes" className="btn btn-quiet ml-auto h-8 px-2.5 text-[12.5px] no-underline">
          Керувати <ArrowUpRight size={13} aria-hidden />
        </Link>
      </div>
      <Dock panels={PANELS} />
      <div className="grid items-start gap-3 lg:grid-cols-12">
        <Panel
          id="notice.feed"
          title="Стрічка анонсів"
          index={0}
          className="h-[560px] lg:col-span-7 lg:row-span-2 lg:h-[640px]"
          wideClass="h-[600px] lg:col-span-12"
          foldClass="h-auto! lg:h-auto! lg:row-span-1!"
          bodyClass="min-h-0 overflow-auto"
          tip="Усі анонси Binance й Upbit, які побачив бот. Під кожним — коли бот його побачив і що вирішив: зайшов чи пропустив і чому. Рішення бот записує з 31.10.2026."
          actions={
            <span className="flex rounded-lg border border-line p-0.5" role="group" aria-label="Фільтр">
              {[false, true].map((v) => (
                <button key={String(v)} type="button" onClick={() => setAll(v)} aria-pressed={all === v} className={clsx("h-6 rounded-md px-2 text-[12px]", all === v ? "bg-press text-text" : "text-text-3 hover:text-text")}>
                  {v ? "усі" : "з подією"}
                </button>
              ))}
            </span>
          }
          summary={feed.data ? `${feed.data.length}` : undefined}
        >
          {feed.isLoading ? <Skeleton className="m-3.5 h-40" /> : <Feed items={feed.data ?? []} />}
        </Panel>
        <Panel id="notice.trades" title="Угоди" index={1} className="lg:col-span-5" summary={`${list.length}`}>
          {trades.isLoading ? <Skeleton className="m-3.5 h-20" /> : <Trades trades={list} selected={trade?.id} onSelect={(t) => setPicked(t.id)} />}
        </Panel>
        <Panel id="notice.chart" title="Графік угоди" index={2} className="lg:col-span-5" tip="Хвилинні свічки навколо угоди. Лінії: вхід, стоп і тейк. Трейлінг-стоп рухається за ціною, тож лінія стопу — його рівень на момент входу.">
          <TradeChart trade={trade} />
        </Panel>
        <Panel id="notice.rules" title="Правила входу" index={3} className="lg:col-span-7" summary={summary.data?.playbooks.fitted_at ? `підібрано ${when.day(summary.data.playbooks.fitted_at)}` : undefined}>
          <Rules summary={summary.data} />
        </Panel>
        <Panel id="notice.days" title="Анонси по днях" index={4} className="lg:col-span-5" tip="Сірі — усі анонси, світлі — з торговою подією.">
          <div className="px-3.5 py-3">{daily.data ? <DayBars days={daily.data} /> : <Skeleton className="h-14" />}</div>
        </Panel>
      </div>
    </Page>
  )
}
