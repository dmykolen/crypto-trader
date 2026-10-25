import { useMemo } from "react"
import { useQuery } from "@tanstack/react-query"

import { BotColumn } from "../components/BotColumn"
import { PositionsTable } from "../components/PositionsTable"
import { Empty, ErrorNote, Headline, KV, Signed } from "../components/Print"
import { TimeChart, type SeriesSpec } from "../components/TimeChart"
import { api } from "../lib/api"
import { fmt, when } from "../lib/format"
import { useLedger, useOverview } from "../lib/hooks"
import type { QuantLedger } from "../lib/types"
import { Loading, Page } from "./Overview"

const LABELS: Record<string, string> = {
  family: "Сигнал",
  k: "Токенів на сторону в книгах",
  hold_days: "Утримання, днів",
  weighting: "Зважування",
  gross: "Експозиція (gross)",
  per_side: "Максимум позицій на сторону",
  short_cap: "Ліміт ваги шорту",
  beta_days: "Бета до BTC, днів",
  band: "Коридор ребалансу",
}

function show(key: string, value: unknown): string {
  if (Array.isArray(value)) return value.join(" · ")
  if (key === "short_cap" || key === "band") return `${(100 * Number(value)).toFixed(1).replace(".", ",")} %`
  if (key === "gross") return `${value}×`
  if (key === "family") return value === "blend" ? "суміш двох моделей" : String(value)
  return String(value)
}

export function QuantBot() {
  const overview = useOverview()
  const ledger = useLedger()
  const config = useQuery({ queryKey: ["quant-config"], queryFn: api.quantConfig, staleTime: 60_000 })
  const live = useQuery({ queryKey: ["quant-live"], queryFn: () => fetch("/api/v1/quant/live").then((r) => r.json()), refetchInterval: 30_000 })
  const book = ledger.data && ledger.data.started ? (ledger.data as QuantLedger) : null
  const series = useMemo<SeriesSpec[]>(() => {
    if (!book) return []
    const today = new Date().toISOString().slice(0, 10)
    const pts = book.history.filter((h) => h.day !== today).map((h) => ({ time: h.day, value: h.equity }))
    pts.push({ time: today, value: book.equity_now })
    return [{ kind: "line", color: "var(--quant)", priceFormat: "usd", data: pts, baseline: { value: book.start_equity, title: "старт" }, minRange: 0.1 * book.start_equity }]
  }, [book])
  if (overview.isLoading) return <Page>{<Loading />}</Page>
  if (!overview.data) return <Page>{<ErrorNote error={overview.error} />}</Page>
  const bot = overview.data.bots.find((b) => b.key === "quant")
  return (
    <Page>
      <div className="pt-5">
        <Headline
          as="h1"
          title="Квант"
          hue="var(--quant)"
          dek="Ринково-нейтральна книга: щодня о 23:00 UTC дві моделі ранжують ліквідні ф’ючерси, о 00:15 UTC бот купує найсильніші й шортить найслабші. Ваги обернені до волатильності, тож спокійні монети важать більше; сума лонгів дорівнює сумі шортів, а залишкову бету до ринку врівноважує позиція в BTC."
        />
      </div>
      <div className="rule-heavy grid grid-cols-12 gap-x-6 pt-4">
        <div className="col-span-12 lg:col-span-4">{bot && <BotColumn bot={bot} system={overview.data.system} dek="" compact heading={false} figures={book ? <KV rows={[["Капітал зараз", <b className="num">{fmt.usd(book.equity_now)}</b>], ["Від старту", <Signed value={book.return_now_pct}>{fmt.pct(book.return_now_pct)}</Signed>], ["Нереалізований P&L", <Signed value={book.unrealized}>{fmt.pnl(book.unrealized)}</Signed>], ["Наступний ребаланс", when.until(book.next_rebalance)]]} /> : <Empty>Рахунок ще не відкрито.</Empty>} />}</div>
        <div className="col-span-12 lg:col-span-8 lg:colrule lg:pl-6">
          <h2 className="head text-[1.25rem] font-extrabold">Паперовий рахунок</h2>
          <p className="text-[12.5px] text-ink-3">Капітал на кожен день після ребалансу; сьогодні — переоцінка за поточними цінами. Пунктир — стартові {fmt.usd0(book?.start_equity)}, шкала щонайменше ±5 %.</p>
          {series.length ? <TimeChart series={series} height={260} label="Капітал паперового рахунку по днях" /> : <Empty>Даних ще немає.</Empty>}
        </div>
      </div>
      <section className="rule-heavy mt-8 pt-3">
        <Headline title="Книга" dek={book ? `${book.positions.length} позицій · експозиція ${fmt.times(book.gross)} · чиста ${fmt.weight(book.net)} · ціни Binance о ${when.time(book.priced_at)}. Вага — частка капіталу на момент ребалансу.` : undefined} />
        {book ? <PositionsTable positions={book.positions} /> : <Empty>Позицій немає.</Empty>}
      </section>
      <section className="rule-heavy mt-8 grid grid-cols-12 gap-x-6 pt-3">
        <div className="col-span-12 overflow-x-auto lg:col-span-8">
          <Headline as="h3" title="Ребаланси" dek="Кожен рядок — переоцінка книги, фандінг і витрати на ордери." />
          {book?.history.length ? (
            <table className="agate min-w-[640px]">
              <thead>
                <tr>
                  <th>День</th>
                  <th className="r">P&L з попереднього</th>
                  <th className="r">Фандінг</th>
                  <th className="r">Витрати</th>
                  <th className="r">Обіг</th>
                  <th className="r">Лонги / шорти</th>
                  <th className="r">Капітал</th>
                </tr>
              </thead>
              <tbody>
                {[...book.history].reverse().map((h) => (
                  <tr key={h.rebalanced_at}>
                    <td className="num">{when.dateTime(h.rebalanced_at)}</td>
                    <td className="r">
                      <Signed value={h.pnl_since_last} arrow={false}>
                        {fmt.pnl(h.pnl_since_last)}
                      </Signed>
                    </td>
                    <td className="r num">{h.funding_paid == null ? "—" : fmt.pnl(-h.funding_paid)}</td>
                    <td className="r num">{fmt.usd(h.cost)}</td>
                    <td className="r num">{fmt.times(h.turnover)}</td>
                    <td className="r num">
                      {h.longs} / {h.shorts}
                    </td>
                    <td className="r num font-semibold">{fmt.usd(h.equity)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <Empty>Ребалансів ще не було.</Empty>
          )}
        </div>
        <div className="col-span-12 lg:col-span-4 lg:colrule lg:pl-6">
          <Headline as="h3" title="Бойова конфігурація" dek={config.data?.decision} />
          {config.data && <KV rows={Object.entries(config.data.ensemble).map(([k, v]) => [LABELS[k] ?? k, show(k, v)])} />}
          <p className="mt-2 text-[12px] text-ink-3">Витрати на сторону: {config.data?.costs.note}. Моделі навчені на даних до {overview.data.system.models_trained_through ? when.day(overview.data.system.models_trained_through) : "30 вер. 2026"}; наступне перенавчання ≈ {when.day(overview.data.system.next_retrain_due)}.</p>
          <h3 className="head mt-6 text-[1.1rem] font-extrabold">Реальні гроші</h3>
          <p className="text-[13px] text-ink-2">
            {live.data?.live_ready ? "Ключі Binance налаштовані." : "Ключі Binance не налаштовані — реальна торгівля недоступна."}{" "}
            {live.data?.halted ? <b className="text-loss">Запобіжник просідання спрацював — бот зупинив торгівлю.</b> : live.data?.history?.length ? `Ребалансів наживо: ${live.data.history.length}.` : "Наживо ще не торгував."}
          </p>
        </div>
      </section>
    </Page>
  )
}
