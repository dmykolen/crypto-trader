import clsx from "clsx"
import { useMemo, useState } from "react"

import { exitReason, fmt, triggerParts, when } from "../lib/format"
import type { BookSummary, SeriesResult, Stats } from "../lib/types"
import { KV, Signed } from "./Print"
import { TimeChart, type SeriesSpec } from "./TimeChart"
import { Dock, Panel } from "./ui"

export function StatsTable({ stats }: { stats: Stats }) {
  return (
    <KV
      rows={[
        ["Капітал: старт → фініш", `${fmt.usd0(stats.start_equity)} → ${fmt.usd(stats.final_equity)}`],
        ["Дохід за період", <Signed value={stats.return_pct}>{fmt.pct(stats.return_pct)}</Signed>],
        ["Річний темп", <Signed value={stats.annual_return_pct} digits={1}>{fmt.pct(stats.annual_return_pct, 1)}</Signed>],
        ["Sharpe (річний)", fmt.ratio(stats.sharpe)],
        ["Найбільше просідання", <Signed value={stats.max_drawdown_pct} arrow={false} digits={1}>{fmt.pct(stats.max_drawdown_pct, 1)}</Signed>],
        ["Найгірший / найкращий день", `${fmt.pct(stats.worst_day_pct, 1)} / ${fmt.pct(stats.best_day_pct, 1)}`],
        ["Днів у плюсі", fmt.pctPlain(stats.positive_days_pct)],
        ["Місяців у плюсі", `${stats.positive_months} з ${stats.months}`],
        ["Днів у тесті", fmt.int(stats.days)],
      ]}
    />
  )
}

export function EquityChart({ result }: { result: SeriesResult }) {
  const series = useMemo<SeriesSpec[]>(
    () => [{ kind: "line", color: "var(--data)", priceFormat: "usd", baseline: { value: result.stats.start_equity, title: "старт" }, data: result.days.map((d, i) => ({ time: d, value: result.equity[i] ?? 0 })) }],
    [result],
  )
  return <TimeChart series={series} height={300} label="Крива капіталу за днями" />
}

export function DrawdownChart({ result }: { result: SeriesResult }) {
  const series = useMemo<SeriesSpec[]>(() => [{ kind: "underwater", color: "var(--loss)", priceFormat: "pct", data: result.days.map((d, i) => ({ time: d, value: result.drawdown[i] ?? 0 })) }], [result])
  return <TimeChart series={series} height={170} label="Просідання від піку за днями" />
}

export function MonthlyTable({ monthly }: { monthly: SeriesResult["monthly"] }) {
  const years = Array.from(new Set(monthly.map((m) => m.month.slice(0, 4))))
  const byKey = new Map(monthly.map((m) => [m.month, m.return]))
  const months = ["01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12"]
  return (
    <div className="overflow-x-auto">
      <table className="agate min-w-[760px] table-fixed">
        <colgroup>
          <col className="w-[5.5rem]" />
          {months.map((m) => (
            <col key={m} />
          ))}
          <col className="w-[6rem]" />
        </colgroup>
        <thead>
          <tr>
            <th>Рік</th>
            {["січ.", "лют.", "бер.", "квіт.", "трав.", "черв.", "лип.", "серп.", "вер.", "жовт.", "лист.", "груд."].map((m) => (
              <th key={m} className="r">
                {m}
              </th>
            ))}
            <th className="r">За рік</th>
          </tr>
        </thead>
        <tbody>
          {years.map((y) => {
            const values = months.map((m) => byKey.get(`${y}-${m}`))
            const year = values.reduce<number>((acc, v) => (v == null ? acc : acc * (1 + v)), 1) - 1
            return (
              <tr key={y}>
                <td className="font-semibold">{y}</td>
                {values.map((v, i) => (
                  <td
                    key={i}
                    className="r num"
                    style={v == null ? undefined : { background: `color-mix(in oklab, var(${v >= 0 ? "--gain" : "--loss"}) ${Math.min(42, Math.sqrt(Math.abs(v)) * 85).toFixed(1)}%, transparent)` }}
                  >
                    {v == null ? <span className="text-text-3">·</span> : fmt.pct(100 * v, 1)}
                  </td>
                ))}
                <td className="r">
                  <Signed value={year} arrow={false} digits={3} className="font-semibold">
                    {fmt.pct(100 * year, 1)}
                  </Signed>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

export const bookLine = (book: BookSummary) => `${book.positions} позицій · експозиція ${fmt.times(book.gross)} · чиста ${fmt.weight(book.net)}`

export function BookListing({ book }: { book: BookSummary }) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2">
      {(["longs", "shorts"] as const).map((side) => (
        <table key={side} className="agate">
          <thead>
            <tr>
              <th>
                {side === "longs" ? "Лонги" : "Шорти"} · {book[side].length}
                {book[side].length > 15 ? ", найбільші 15" : ""}
              </th>
              <th className="r">Вага</th>
            </tr>
          </thead>
          <tbody>
            {book[side].slice(0, 15).map((p) => (
              <tr key={p.symbol}>
                <td>{p.symbol.replace(/USDT$/, "")}</td>
                <td className="r num">{fmt.weight(p.weight)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ))}
    </div>
  )
}

export interface DayView {
  day: string
  book: string
  positions: number
  longs: number
  shorts: number
  gross_exposure_pct: number
  net_exposure_pct: number
  rebalance_cost: number
  pnl: number
  return_pct: number
  table: { symbol: string; side: string; weight_pct: number; notional: number; day_return_pct: number; pnl: number }[]
}

const DAY_PANELS = [
  { id: "daybook.summary", title: "Підсумок дня" },
  { id: "daybook.table", title: "Позиції" },
]

export function DayBook({ view }: { view: DayView }) {
  const rows = [...view.table].sort((a, b) => b.pnl - a.pnl)
  return (
    <>
      <Dock panels={DAY_PANELS} />
      <div className="grid items-start gap-3 lg:grid-cols-12">
        <Panel id="daybook.summary" title="Підсумок дня" index={0} className="lg:col-span-4" summary={fmt.pnl(view.pnl)} tip={view.book}>
          <KV
            rows={[
              ["День", when.day(view.day)],
              ["P&L дня на $1 000", <Signed value={view.pnl}>{fmt.pnl(view.pnl)}</Signed>],
              ["Дохід дня", <Signed value={view.return_pct} digits={3}>{fmt.pct(view.return_pct, 3)}</Signed>],
              ["Позицій · лонги / шорти", `${view.positions} · ${view.longs} / ${view.shorts}`],
              ["Експозиція · чиста", `${fmt.pctPlain(view.gross_exposure_pct)} · ${fmt.pct(view.net_exposure_pct, 1)}`],
              ["Витрати ребалансу", fmt.usd(view.rebalance_cost)],
            ]}
          />
        </Panel>
        <Panel id="daybook.table" title="Позиції" index={1} className="lg:col-span-8" summary={`${rows.length}`} bodyClass="overflow-x-auto">
          <table className="agate min-w-[520px]">
            <thead>
              <tr>
                <th>Токен</th>
                <th>Бік</th>
                <th className="r">Вага</th>
                <th className="r">Сума</th>
                <th className="r">Рух дня</th>
                <th className="r">P&L</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.symbol}>
                  <td className="font-semibold">{r.symbol.replace(/USDT$/, "")}</td>
                  <td className={clsx(r.side === "LONG" ? "text-gain" : "text-loss")}>{r.side === "LONG" ? "лонг" : "шорт"}</td>
                  <td className="r num">{fmt.pctPlain(r.weight_pct, 2)}</td>
                  <td className="r num">{fmt.usd(r.notional)}</td>
                  <td className="r num">{fmt.pct(r.day_return_pct)}</td>
                  <td className="r">
                    <Signed value={r.pnl} arrow={false}>
                      {fmt.pnl(r.pnl)}
                    </Signed>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>
      </div>
    </>
  )
}

interface ReplayTrade {
  entry_time: string
  symbol: string
  side: string
  leverage: number
  margin: number
  entry_price: number
  exit_time: string | null
  exit_price: number | null
  exit_reason: string | null
  pnl: number
  return_on_margin_pct: number | null
  trigger: string
}

interface ReplayScenario {
  latency_s: Record<string, number> | null
  trades: number
  winners: number
  pnl: number
  final_equity: number
  max_drawdown_pct: number
  trades_log: ReplayTrade[]
}

export interface ReplayDoc {
  period: { start: string; end: string; days: number }
  playbooks_fitted_on: string
  notices: { published: string; source: string; title: string; events: { type: string; token: string; perpetual: string | null }[] }[]
  scenarios: Record<string, ReplayScenario>
}

const SCENARIO_UA: Record<string, string> = {
  "fast feed, 1 s (WebSocket key, server near Binance)": "Швидкий канал, 1 с (WebSocket-ключ)",
  "as configured now (Upbit 1 s polling, Binance 5 s polling)": "Як зараз (Upbit 1 с, Binance 5 с)",
  "slow path only (60 s entry)": "Лише повільний шлях (вхід за 60 с)",
}

const REPLAY_PANELS = [
  { id: "replay.scenarios", title: "Сценарії затримки" },
  { id: "replay.trades", title: "Угоди" },
  { id: "replay.notices", title: "Анонси періоду" },
]

export function ReplayResult({ doc }: { doc: ReplayDoc }) {
  const names = Object.keys(doc.scenarios)
  const [pick, setPick] = useState(names[0] ?? "")
  const chosen = doc.scenarios[pick]
  return (
    <>
      <Dock panels={REPLAY_PANELS} />
      <div className="grid items-start gap-3 lg:grid-cols-12">
        <Panel
          id="replay.scenarios"
          title="Сценарії затримки"
          index={0}
          className="lg:col-span-12"
          summary={`${names.length}`}
          bodyClass="overflow-x-auto"
          tip={`${when.day(doc.period.start)}, ${doc.period.days} дн. Плейбуки навчено лише на анонсах до ${when.day(doc.period.start)}. Анонсів у періоді: ${doc.notices.length}. Рядок таблиці відкриває угоди сценарію.`}
        >
          <table className="agate min-w-[640px]">
            <thead>
              <tr>
                <th>Сценарій</th>
                <th className="r">Угод</th>
                <th className="r">У плюсі</th>
                <th className="r">P&L</th>
                <th className="r">Капітал</th>
                <th className="r">Просідання</th>
              </tr>
            </thead>
            <tbody>
              {names.map((n) => {
                const s = doc.scenarios[n] as ReplayScenario
                return (
                  <tr key={n} className={clsx("cursor-pointer", n === pick && "bg-raised")} onClick={() => setPick(n)} aria-selected={n === pick}>
                    <td>{SCENARIO_UA[n] ?? n}</td>
                    <td className="r num">{s.trades}</td>
                    <td className="r num">{s.winners}</td>
                    <td className="r">
                      <Signed value={s.pnl}>{fmt.pnl(s.pnl)}</Signed>
                    </td>
                    <td className="r num">{fmt.usd(s.final_equity)}</td>
                    <td className="r num">{fmt.pct(s.max_drawdown_pct, 1)}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </Panel>
        {chosen && (
          <Panel id="replay.trades" title={`Угоди: ${SCENARIO_UA[pick] ?? pick}`} index={1} className="lg:col-span-12" summary={`${chosen.trades_log.length}`} bodyClass="overflow-x-auto">
            {chosen.trades_log.length === 0 ? (
              <p className="px-3.5 py-4 text-[13px] text-text-3">Жодної угоди: для анонсів цього періоду не було плейбука з перевагою або вікно затримки пропущено.</p>
            ) : (
              <table className="agate min-w-[760px]">
                <thead>
                  <tr>
                    <th>Вхід</th>
                    <th>Токен</th>
                    <th>Бік</th>
                    <th>Подія</th>
                    <th className="r">Плече</th>
                    <th className="r">Маржа</th>
                    <th>Вихід</th>
                    <th className="r">P&L</th>
                    <th className="r">На маржу</th>
                  </tr>
                </thead>
                <tbody>
                  {chosen.trades_log.map((t, i) => (
                    <tr key={i}>
                      <td className="num">{when.dateTime(t.entry_time)}</td>
                      <td className="font-semibold">{t.symbol.replace(/USDT$/, "")}</td>
                      <td>{t.side === "LONG" ? "лонг" : "шорт"}</td>
                      <td title={triggerParts(t.trigger).playbook}>{triggerParts(t.trigger).event}</td>
                      <td className="r num">{t.leverage}×</td>
                      <td className="r num">{fmt.usd(t.margin)}</td>
                      <td>{exitReason(t.exit_reason)}</td>
                      <td className="r">
                        <Signed value={t.pnl} arrow={false}>
                          {fmt.pnl(t.pnl)}
                        </Signed>
                      </td>
                      <td className="r num">{fmt.pct(t.return_on_margin_pct, 1)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Panel>
        )}
        <Panel id="replay.notices" title="Анонси періоду" index={2} className="lg:col-span-12" summary={`${doc.notices.length}`} bodyClass="max-h-[480px] overflow-auto">
          <table className="agate">
            <tbody>
              {doc.notices.map((n, i) => (
                <tr key={i}>
                  <td className="num whitespace-nowrap">{when.dateTime(n.published)}</td>
                  <td>{n.source}</td>
                  <td>{n.title}</td>
                  <td>{n.events.map((e) => `${e.type} ${e.perpetual ?? e.token}`).join(", ")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>
      </div>
    </>
  )
}
