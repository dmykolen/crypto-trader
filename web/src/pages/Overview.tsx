import { useQuery } from "@tanstack/react-query"
import { ArrowUpRight } from "lucide-react"
import { useState, type ReactNode } from "react"
import { Link } from "react-router-dom"

import { BotColumn } from "../components/BotColumn"
import { DayBars } from "../components/DayBars"
import { EventTape } from "../components/EventTape"
import { PositionsTable } from "../components/PositionsTable"
import { Empty, ErrorNote, KV, Signed } from "../components/Print"
import { Spark } from "../components/Spark"
import { api } from "../lib/api"
import { fmt, plural, when } from "../lib/format"
import { useEvidence, useLedger, useOverview, useWet } from "../lib/hooks"
import type { DayCount, Evidence, NoticePaper, QuantLedger, SystemInfo } from "../lib/types"

export function Page({ children }: { children: ReactNode }) {
  return <main className="mx-auto w-full max-w-[1480px] px-5 pb-20 md:px-8">{children}</main>
}

export function Loading({ what = "випуск" }: { what?: string }) {
  return <p className="py-10 text-ink-3">Набираю {what}…</p>
}

function Hero({ value, children, hue, stamp }: { value: string; children?: ReactNode; hue: string; stamp?: number }) {
  return (
    <p key={stamp} className={stamp ? "wet" : undefined} style={{ ["--wet" as string]: hue }}>
      <span className="head num text-[2.75rem] font-black leading-none">{value}</span>
      <span className="mt-1 block sm:mt-0 sm:inline">{children}</span>
    </p>
  )
}

function NoticeFigures({ paper, system, daily }: { paper: NoticePaper; system: SystemInfo; daily: DayCount[] | undefined }) {
  const today = daily?.[daily.length - 1]
  return (
    <div>
      {paper.closed ? (
        <Hero value={fmt.pnl(paper.realized_pnl)} hue="var(--notice)">
          <span className="text-[13px] text-ink-3 sm:ml-2">реалізовано · {plural(paper.closed, "закрита угода", "закриті угоди", "закритих угод")}</span>
        </Hero>
      ) : (
        <Hero value="0 угод" hue="var(--notice)">
          <span className="text-[13px] text-ink-3 sm:ml-2">бот торгує лише події з перевіреним плейбуком</span>
        </Hero>
      )}
      <KV
        className="mt-3"
        rows={[
          ["Відкритих позицій", paper.open],
          ["Влучність", paper.win_rate_pct == null ? "угод ще немає" : fmt.pctPlain(paper.win_rate_pct)],
          ["Анонсів сьогодні · з подією", today ? `${today.total} · ${today.events}` : "—"],
          ["Канал анонсів Binance", system.live_ready ? "WebSocket, ~1 с" : "опитування, ~5 с"],
        ]}
      />
    </div>
  )
}

function QuantFigures({ ledger }: { ledger: QuantLedger }) {
  const stamp = useWet(Math.round(ledger.equity_now * 100))
  const longs = ledger.positions.filter((p) => p.side === "long").length
  return (
    <div>
      <Hero value={fmt.usd(ledger.equity_now)} hue="var(--quant)" stamp={stamp}>
        <Signed value={ledger.return_now_pct} className="text-[1.05rem] font-semibold sm:ml-3">
          {fmt.pct(ledger.return_now_pct)}
        </Signed>
        <span className="ml-1.5 text-[13px] text-ink-3">від старту {fmt.usd0(ledger.start_equity)}</span>
      </Hero>
      <KV
        className="mt-3"
        rows={[
          ["Нереалізований P&L з ребалансу", <Signed value={ledger.unrealized}>{fmt.pnl(ledger.unrealized)}</Signed>],
          ["Позиції: лонги / шорти", `${longs} / ${ledger.positions.length - longs}`],
          ["Експозиція · чиста", `${fmt.times(ledger.gross)} · ${fmt.weight(ledger.net)}`],
          ["Наступний ребаланс", `${when.time(ledger.next_rebalance)}, ${when.until(ledger.next_rebalance)}`],
        ]}
      />
    </div>
  )
}

function QuantSpark({ ledger }: { ledger: QuantLedger }) {
  const first = ledger.history[0]
  if (!first) return null
  const series = [ledger.start_equity, ...ledger.history.map((h) => h.equity), ledger.equity_now]
  return (
    <figure>
      <figcaption className="num mb-1 text-[11.5px] text-ink-3">Капітал після кожного ребалансу · пунктир — старт {fmt.usd0(ledger.start_equity)} · шкала ±5 %</figcaption>
      <Spark values={series} baseline={ledger.start_equity} minSpan={0.1 * ledger.start_equity} width={520} height={52} color="var(--quant)" fill className="block w-full" label="Капітал паперового рахунку після кожного ребалансу" />
      <div className="num mt-1 flex justify-between gap-2 text-[11.5px] text-ink-3" aria-hidden>
        <span>{when.dayShort(first.day)}</span>
        <span>зараз {fmt.usd(ledger.equity_now)}</span>
      </div>
    </figure>
  )
}

function EvidenceStrip({ evidence }: { evidence: Evidence }) {
  const index = new Map(evidence.days.map((d, i) => [d, i]))
  return (
    <div className="grid grid-cols-1 gap-x-6 gap-y-6 sm:grid-cols-2 xl:grid-cols-4">
      {evidence.periods.map((p, k) => {
        const a = index.get(p.from) ?? 0
        const b = index.get(p.to) ?? evidence.days.length - 1
        const slice = evidence.equity.slice(a, b + 1)
        const base = slice[0] ?? 1
        return (
          <article key={p.key} className={k ? "sm:colrule sm:pl-6" : ""}>
            <h3 className="head text-[1.35rem] font-extrabold">{p.name}</h3>
            <p className="num text-[12px] text-ink-3">
              {when.dayShort(p.from)} — {when.day(p.to)} · {p.note}
            </p>
            <Spark values={slice.map((v) => (1000 * v) / base)} baseline={1000} width={300} height={54} color="var(--quant)" className="mt-2 block w-full" label={`${p.name}: капітал на $1 000`} />
            <p className="num mt-1 flex flex-wrap gap-x-3 text-[13px]">
              <Signed value={p.stats.return_pct} digits={1} className="font-semibold">
                {fmt.pct(p.stats.return_pct, 1)}
              </Signed>
              <span className="text-ink-2">Sharpe {fmt.ratio(p.stats.sharpe)}</span>
              <span className="text-ink-2">просідання {fmt.pct(p.stats.max_drawdown_pct, 1)}</span>
            </p>
          </article>
        )
      })}
    </div>
  )
}

export function Overview() {
  const overview = useOverview()
  const ledger = useLedger()
  const evidence = useEvidence()
  const daily = useQuery({ queryKey: ["notice-daily", 14], queryFn: () => api.noticeDaily(14), refetchInterval: 60_000 })
  const [tapeLimit, setTapeLimit] = useState(14)
  if (overview.isLoading) return <Page>{<Loading />}</Page>
  if (overview.error || !overview.data) return <Page>{<ErrorNote error={overview.error} />}</Page>
  const { bots, system, paper, events } = overview.data
  const notice = bots.find((b) => b.key === "notice")
  const quant = bots.find((b) => b.key === "quant")
  const book = ledger.data && ledger.data.started ? (ledger.data as QuantLedger) : null
  const lastNotice = events.find((e) => e.kind === "notice")
  const lastRebalance = book?.history[book.history.length - 1]
  return (
    <Page>
      <div className="grid grid-cols-12 gap-x-6">
        <div className="col-span-12 lg:col-span-9">
          <div className="grid grid-cols-9 gap-x-6">
            <div className="col-span-9 pt-5 md:col-span-4">
              {notice && (
                <BotColumn
                  bot={notice}
                  system={system}
                  dek="Ловить анонси Binance і Upbit і за секунди торгує ф’ючерс токена. Перевага існує лише в перші 1–2 секунди після публікації."
                  figures={<NoticeFigures paper={paper.notice} system={system} daily={daily.data} />}
                  chart={daily.data ? <DayBars days={daily.data} /> : undefined}
                  last={lastNotice?.kind === "notice" ? <>Останній анонс {when.dateTime(lastNotice.at)}: «{lastNotice.title}»</> : "Анонсів у журналі ще немає."}
                />
              )}
            </div>
            <div className="col-span-9 mt-6 border-t border-rule pt-5 md:col-span-5 md:mt-0 md:border-t-0 md:colrule md:pl-6">
              {quant && (
                <BotColumn
                  bot={quant}
                  system={system}
                  dek="Щодня о 00:15 UTC ребалансує ринково-нейтральну книгу: до 30 лонгів і 30 шортів за рейтингом двох моделей, бета-хедж через BTC, експозиція 2×."
                  figures={book ? <QuantFigures ledger={book} /> : <Empty>Паперовий рахунок ще не відкрито — запустіть бота.</Empty>}
                  chart={book ? <QuantSpark ledger={book} /> : undefined}
                  last={
                    lastRebalance ? (
                      <>
                        Останній ребаланс {when.dateTime(lastRebalance.rebalanced_at)}: P&L з попереднього{" "}
                        <Signed value={lastRebalance.pnl_since_last} arrow={false}>
                          {fmt.pnl(lastRebalance.pnl_since_last)}
                        </Signed>
                        , витрати {fmt.usd(lastRebalance.cost)}.
                      </>
                    ) : undefined
                  }
                />
              )}
            </div>
          </div>
          <section className="rule-heavy mt-8 pt-3" aria-labelledby="book">
            <div className="flex flex-wrap items-end justify-between gap-2 pb-2">
              <div>
                <h2 id="book" className="head text-[1.75rem] font-extrabold">
                  Книга Кванта
                </h2>
                <p className="text-[12.5px] text-ink-3">{book ? `Переоцінка за цінами Binance о ${when.time(book.priced_at)}; «рух» — на користь позиції.` : "Паперового рахунку ще немає."}</p>
              </div>
              <Link to="/bots/quant" className="head flex items-center gap-1 text-[15px] font-bold">
                Уся книга й історія <ArrowUpRight size={14} aria-hidden />
              </Link>
            </div>
            {book ? <PositionsTable positions={book.positions} limit={8} /> : ledger.isLoading ? <Loading what="книгу" /> : <Empty>Позицій немає.</Empty>}
          </section>
        </div>
        <aside className="col-span-12 mt-8 border-t-[3px] border-ink pt-5 lg:col-span-3 lg:mt-0 lg:border-t-0 lg:colrule lg:pl-6" aria-labelledby="tape">
          <h2 id="tape" className="head text-[1.6rem] font-extrabold">
            Стрічка
          </h2>
          <p className="text-[12.5px] text-ink-3">Анонси, угоди, ребаланси й тести, найновіші згори.</p>
          <div className="mt-2">
            <EventTape events={events} limit={tapeLimit} />
          </div>
          {events.length > tapeLimit && (
            <button type="button" className="btn btn-ghost mt-3 w-full justify-center" onClick={() => setTapeLimit((n) => n + 14)}>
              Ще події
            </button>
          )}
        </aside>
      </div>
      <section className="rule-heavy mt-10 pt-3" aria-labelledby="evidence">
        <div className="flex flex-wrap items-end justify-between gap-2 pb-3">
          <div>
            <h2 id="evidence" className="head text-[1.75rem] font-extrabold">
              Чому Кванту можна вірити — і наскільки
            </h2>
            <p className="max-w-[80ch] text-[12.5px] text-ink-3">Бойова конфігурація, $1 000 на кожен період, витрати й фандінг враховано. Перевірочний період оптимістичний: на ньому обирались налаштування.</p>
          </div>
          <Link to="/evidence" className="head flex items-center gap-1 text-[15px] font-bold">
            Усі докази <ArrowUpRight size={14} aria-hidden />
          </Link>
        </div>
        {evidence.data ? <EvidenceStrip evidence={evidence.data} /> : evidence.isLoading ? <Loading what="докази" /> : <Empty>Докази ще не зібрано — запустіть «Перебудова доказів» у Лабораторії.</Empty>}
      </section>
    </Page>
  )
}
