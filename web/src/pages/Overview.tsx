import { ArrowUpRight } from "lucide-react"
import { useMemo, type ReactNode } from "react"
import { Link } from "react-router-dom"

import { BookStrip } from "../components/BookStrip"
import { Feed } from "../components/Feed"
import { PIPELINE_TIP, Pipeline, type Lane } from "../components/Pipeline"
import { ErrorNote, Signed } from "../components/Print"
import { TimeChart, type SeriesSpec } from "../components/TimeChart"
import { Dock, ModeChip, Odometer, Panel, Pulse, Skeleton, Stat, Tip } from "../components/ui"
import { fmt, ticker, triggerParts, when } from "../lib/format"
import { useJobs, useLedger, useNow, useOverview } from "../lib/hooks"
import type { BotState, NoticePaper, QuantLedger } from "../lib/types"

export function Page({ children }: { children: ReactNode }) {
  return <div className="mx-auto w-full max-w-[1600px] px-3 pt-3 pb-20 md:px-5 md:pb-10">{children}</div>
}

export function Loading({ what = "дані" }: { what?: string }) {
  return (
    <div className="space-y-3" role="status" aria-label={`Завантажую ${what}`}>
      <Skeleton className="h-12 w-full" />
      <div className="grid gap-3 lg:grid-cols-12">
        <Skeleton className="h-[420px] lg:col-span-8" />
        <Skeleton className="h-[420px] lg:col-span-4" />
      </div>
    </div>
  )
}

const PANELS = [
  { id: "overview.flow", title: "Потік" },
  { id: "overview.quant", title: "Квант" },
  { id: "overview.feed", title: "Події" },
  { id: "overview.notice", title: "Анонси" },
  { id: "overview.processes", title: "Процеси" },
]

function equitySeries(book: QuantLedger): SeriesSpec[] {
  const today = new Date().toISOString().slice(0, 10)
  const points = book.history.filter((h) => h.day !== today).map((h) => ({ time: h.day, value: h.equity }))
  points.push({ time: today, value: book.equity_now })
  return [{ kind: "area", color: "var(--data)", priceFormat: "usd", data: points, baseline: { value: book.start_equity, title: "старт" }, minRange: 0.1 * book.start_equity }]
}

function QuantPanel({ bot, book, className }: { bot?: BotState; book: QuantLedger | null; className?: string }) {
  const series = useMemo(() => (book ? equitySeries(book) : []), [book])
  const longs = book?.positions.filter((p) => p.weight > 0).length ?? 0
  const shorts = book?.positions.filter((p) => p.weight < 0).length ?? 0
  return (
    <Panel
      id="overview.quant"
      title="Квант"
      index={1}
      className={className}
      summary={book ? `${fmt.usd(book.equity_now)} · ${fmt.pct(book.return_now_pct)} від старту` : undefined}
      side={bot && <ModeChip live={bot.running && bot.mode === "live"} />}
      actions={
        <Link to="/bots/quant" className="btn btn-quiet h-7 px-2 text-[12px] no-underline">
          Портфель <ArrowUpRight size={13} aria-hidden />
        </Link>
      }
      bodyClass="p-3.5"
    >
      {book ? (
        <>
          <div className="grid gap-5 xl:grid-cols-[minmax(230px,280px)_1fr]">
            <div className="flex flex-col gap-4">
              <div>
                <div className="flex items-center gap-1.5">
                  <span className="label">Рахунок</span>
                  <Tip align="start">Віртуальні гроші: старт $1 000 24.10.2026. Сума враховує переоцінку відкритих позицій за поточними цінами Binance.</Tip>
                </div>
                <Odometer text={fmt.usd(book.equity_now)} className="display mt-1.5 text-[44px] leading-none font-semibold" />
              </div>
              <div className="grid grid-cols-2 gap-x-4 gap-y-3">
                <Stat label="З ребалансу" tip="Прибуток чи збиток відкритих позицій від останнього ребалансу о 00:15 UTC за поточними цінами.">
                  <Signed value={book.unrealized}>{fmt.pnl(book.unrealized)}</Signed>
                </Stat>
                <Stat label="Від старту">
                  <Signed value={book.return_now_pct}>{fmt.pct(book.return_now_pct)}</Signed>
                </Stat>
                <Stat label="Позиції" tip="Лонги / шорти.">
                  <span className="num">
                    {longs} / {shorts}
                  </span>
                </Stat>
                <Stat label="Плече" tip="Сума всіх позицій, лонгів і шортів, поділена на рахунок. Стопів у Кванта немає: позиції змінюються раз на добу.">
                  <span className="num">{fmt.times(book.gross)}</span>
                </Stat>
              </div>
            </div>
            <div className="min-w-0">
              <TimeChart series={series} height={212} label="Рахунок Кванта по днях" />
            </div>
          </div>
          <div className="mt-4 border-t border-line pt-3.5">
            <BookStrip positions={book.positions} />
          </div>
        </>
      ) : (
        <p className="py-8 text-center text-[13px] text-text-3">Рахунок ще не відкрито: запустіть Квант у «Процесах».</p>
      )}
    </Panel>
  )
}

function NoticePanel({ bot, paper, className }: { bot?: BotState; paper: NoticePaper; className?: string }) {
  return (
    <Panel
      id="overview.notice"
      title="Анонси"
      index={2}
      className={className}
      summary={`${fmt.pnl(paper.realized_pnl)} · угод ${paper.trades}`}
      side={bot && <ModeChip live={bot.running && bot.mode === "live"} />}
      actions={
        <Link to="/bots/notice" className="btn btn-quiet h-7 px-2 text-[12px] no-underline">
          Стрічка <ArrowUpRight size={13} aria-hidden />
        </Link>
      }
      bodyClass="p-3.5"
    >
      <div className="flex items-center gap-1.5">
        <span className="label">Прибуток</span>
        <Tip align="start">Віртуальні гроші. Бот входить лише в перші секунди після анонсу лістингу, делістингу чи попередження на Binance або Upbit.</Tip>
      </div>
      <Odometer text={fmt.pnl(paper.realized_pnl)} className="display mt-1.5 text-[30px] leading-none font-semibold" />
      <div className="mt-4 grid grid-cols-3 gap-3">
        <Stat label="Угод">
          <span className="num">{paper.trades}</span>
        </Stat>
        <Stat label="Відкрито">
          <span className="num">{paper.open}</span>
        </Stat>
        <Stat label="Виграшні">
          <span className="num">{paper.win_rate_pct == null ? "—" : fmt.pctPlain(paper.win_rate_pct, 0)}</span>
        </Stat>
      </div>
      {paper.latest.length ? (
        <ul className="mt-4 divide-y divide-line border-t border-line">
          {paper.latest.slice(0, 3).map((t) => (
            <li key={`${t.symbol}${t.entry_time}`} className="flex items-baseline gap-2 py-2 text-[12.5px]">
              <b>{ticker(t.symbol)}</b>
              <span className={t.side === "LONG" ? "text-gain" : "text-loss"}>{t.side === "LONG" ? "лонг" : "шорт"}</span>
              <span className="min-w-0 truncate text-text-3">{triggerParts(t.trigger).event}</span>
              <span className="ml-auto">
                {t.pnl == null ? (
                  <span className="text-text-3">відкрита</span>
                ) : (
                  <Signed value={t.pnl} arrow={false}>
                    {fmt.pnl(t.pnl)}
                  </Signed>
                )}
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-4 border-t border-line pt-3 text-[12.5px] text-text-3">Угод ще не було.</p>
      )}
    </Panel>
  )
}

function ProcessesPanel({ bots, online, running, className }: { bots: BotState[]; online: boolean; running: number; className?: string }) {
  const rows = [
    { key: "server", name: "Сервер пульта", state: online ? ("on" as const) : ("down" as const), meta: online ? "на звʼязку" : "не відповідає", beat: undefined as string | null | undefined },
    ...bots.map((b) => ({
      key: b.key,
      name: b.name,
      state: b.running ? ("on" as const) : ("off" as const),
      meta: b.running ? `працює ${when.duration(b.uptime_s)}` : b.last_stop ? `зупинений ${when.ago(b.last_stop)}` : "зупинений",
      beat: b.last_log_at,
    })),
    { key: "jobs", name: "Задачі лабораторії", state: running ? ("on" as const) : ("off" as const), meta: running ? `рахується: ${running}` : "черга порожня", beat: undefined },
  ]
  return (
    <Panel
      id="overview.processes"
      title="Процеси"
      index={3}
      className={className}
      summary={`${online ? "сервер на звʼязку" : "сервер не відповідає"} · ботів працює: ${bots.filter((b) => b.running).length}`}
      actions={
        <Link to="/processes" className="btn btn-quiet h-7 px-2 text-[12px] no-underline">
          Керувати <ArrowUpRight size={13} aria-hidden />
        </Link>
      }
    >
      <ul className="divide-y divide-line">
        {rows.map((r) => (
          <li key={r.key} className="flex items-center gap-2.5 px-3.5 py-2.5">
            <Pulse state={r.state} beat={r.beat} />
            <span className="text-[13px] font-medium">{r.name}</span>
            <span className="display ml-auto text-[11.5px] text-text-3">{r.meta}</span>
          </li>
        ))}
      </ul>
    </Panel>
  )
}

export function Overview() {
  const overview = useOverview()
  const ledger = useLedger()
  const jobs = useJobs()
  const now = useNow(1000)
  if (overview.isLoading)
    return (
      <Page>
        <Loading what="огляд" />
      </Page>
    )
  if (!overview.data)
    return (
      <Page>
        <ErrorNote error={overview.error} />
      </Page>
    )
  const { bots, paper, events } = overview.data
  const quant = bots.find((b) => b.key === "quant")
  const notice = bots.find((b) => b.key === "notice")
  const book = ledger.data && ledger.data.started ? (ledger.data as QuantLedger) : null
  const lanes: Lane[] = [
    { key: "quant", source: "Binance", bot: quant, account: book ? fmt.usd(book.equity_now) : "—", last: events.find((e) => e.bot === "quant") },
    { key: "notice", source: "Binance · Upbit", bot: notice, account: fmt.pnl(paper.notice.realized_pnl), last: events.find((e) => e.bot === "notice") },
  ]
  const running = (jobs.data ?? []).filter((j) => j.status === "running" || j.status === "queued").length
  const latest = events[0]
  return (
    <Page>
      <h1 className="sr-only">Огляд</h1>
      <Dock panels={PANELS} />
      <div className="grid items-start gap-3 lg:grid-cols-12">
        <Panel
          id="overview.flow"
          title="Потік"
          tip={PIPELINE_TIP}
          index={0}
          className="lg:col-span-12"
          summary={lanes.map((l) => `${l.bot?.name ?? l.key}: ${l.bot?.running ? "працює" : "зупинений"}`).join(" · ")}
        >
          <Pipeline lanes={lanes} now={now} />
        </Panel>
        <QuantPanel bot={quant} book={book} className="lg:col-span-8" />
        <Panel
          id="overview.feed"
          title="Події"
          index={4}
          className="max-h-[560px] lg:col-span-4 lg:row-span-2 lg:h-0 lg:max-h-none lg:min-h-full"
          wideClass="max-h-[520px] lg:col-span-12"
          foldClass="lg:h-auto! lg:min-h-0! lg:row-span-1!"
          summary={latest ? `${events.length} · остання ${when.time(latest.at)}` : "подій немає"}
          bodyClass="overflow-auto"
        >
          <Feed events={events} limit={60} />
        </Panel>
        <NoticePanel bot={notice} paper={paper.notice} className="lg:col-span-4" />
        <ProcessesPanel bots={bots} online={!overview.isError} running={running} className="lg:col-span-4" />
      </div>
    </Page>
  )
}
