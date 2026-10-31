import clsx from "clsx"
import { useMemo, useState, type ReactNode } from "react"

import { exitReason, fmt, plural, ticker, when } from "../lib/format"
import type { PairDay, PairRole, PairTactic, PairTrade, TacticFamily } from "../lib/types"
import { Signed } from "./Print"
import { TimeChart, type SeriesSpec } from "./TimeChart"
import { Dock, Panel, Tip } from "./ui"

const FAMILY_UA: Record<TacticFamily, string> = { trend: "Тренд", revert: "Відкат до середньої", pattern: "Патерни графіка й свічок", ml: "Прогноз моделі" }

const ROLE_UA: Record<PairRole, string> = { best: "найкраща за день", second: "друге правило", third: "третє правило", reference: "найкраща за 2023–24", worst: "найгірша за день" }

const PANELS = [
  { id: "pair.summary", title: "Підсумок" },
  { id: "pair.chart", title: "Угоди тактики" },
  { id: "pair.conditions", title: "Умови тесту" },
  { id: "pair.trades", title: "Угоди" },
  { id: "pair.families", title: "За типом" },
  { id: "pair.tactics", title: "Усі тактики" },
]

const WHY: Record<string, [string, (v: number) => string]> = {
  rsi_14: ["RSI 14", (v) => fmt.ratio(v, 0)],
  adx: ["ADX", (v) => fmt.ratio(v, 0)],
  atr_pct: ["ATR", (v) => fmt.pctPlain(100 * v, 2)],
  ema_dist_200: ["від EMA 200", (v) => `${fmt.ratio(v, 1)} ATR`],
  bb_pctb: ["Боллінджер %B", (v) => fmt.ratio(v, 2)],
  supertrend: ["SuperTrend", (v) => (v > 0 ? "вгору" : "вниз")],
  zz_structure: ["структура", (v) => (v > 0 ? "вищі максимуми" : v < 0 ? "нижчі мінімуми" : "змішана")],
  volume_z24: ["обсяг", (v) => `z ${fmt.ratio(v, 1)}`],
  funding_z: ["фандінг", (v) => `z ${fmt.ratio(v, 1)}`],
  btc_ret_24: ["BTC за 24 год", (v) => fmt.pct(100 * v, 1)],
}

const LEGEND =
  "Тактика входить лише за своїм правилом; індикатори — для довідки. RSI 14: понад 70 ціну перекупили, нижче 30 перепродали. ADX понад 25 — сильний тренд. ATR — середній хід ціни за годину. Від EMA 200 — на скільки ATR ціна вища чи нижча за середню за 200 год. Боллінджер %B: 0 — нижня межа смуги, 1 — верхня. Обсяг z і фандінг z — наскільки вони більші чи менші за звичайні."

const isoHour = (ms: number) => when.dateTime(new Date(ms).toISOString())
const exitAt = (t: PairTrade) => Math.floor(t.exit_time / 1000) - (t.reason === "end" || t.reason === "time" ? 3600 : 0)

function markers(trades: PairTrade[]): NonNullable<SeriesSpec["markers"]> {
  return trades.flatMap((t) => [
    { time: Math.floor(t.entry_time / 1000), position: t.side === "LONG" ? ("belowBar" as const) : ("aboveBar" as const), color: "var(--text)", shape: t.side === "LONG" ? ("arrowUp" as const) : ("arrowDown" as const), text: t.side === "LONG" ? "лонг" : "шорт" },
    { time: exitAt(t), position: t.side === "LONG" ? ("aboveBar" as const) : ("belowBar" as const), color: t.pnl >= 0 ? "var(--gain)" : "var(--loss)", shape: "circle" as const, text: fmt.pnl(t.pnl) },
  ])
}

function levels(trades: PairTrade[]): SeriesSpec[] {
  return trades.flatMap((t) => {
    const from = Math.floor(t.entry_time / 1000)
    const to = exitAt(t)
    if (to <= from) return []
    const line = (price: number, color: string): SeriesSpec => ({ kind: "line", quiet: true, color, priceFormat: "price", data: [{ time: from, value: price }, { time: to, value: price }] })
    return [...(t.stop ? [line(t.stop, "var(--loss)")] : []), ...(t.take ? [line(t.take, "var(--gain)")] : [])]
  })
}

function Sharpe({ value }: { value: number | null | undefined }) {
  return value == null ? (
    <span className="text-text-3">—</span>
  ) : (
    <Signed value={value} arrow={false}>
      {fmt.ratio(value)}
    </Signed>
  )
}

function Money({ value }: { value: number | null | undefined }) {
  return (
    <Signed value={value} arrow={false}>
      {fmt.pnl(value)}
    </Signed>
  )
}

function Figure({ label, value, tip }: { label: string; value: ReactNode; tip?: ReactNode }) {
  return (
    <div className="min-w-0">
      <div className="flex items-center gap-1.5">
        <span className="label truncate">{label}</span>
        {tip && <Tip align="start">{tip}</Tip>}
      </div>
      <div className="display mt-1.5 text-[24px] leading-none font-semibold">{value}</div>
    </div>
  )
}

function TacticRows({ rows }: { rows: PairTactic[] }) {
  return (
    <>
      {rows.map((r) => (
        <tr key={r.key}>
          <td className="max-w-[28rem] pl-3.5">{r.label}</td>
          <td className="r">
            <Money value={r.pnl} />
          </td>
          <td className="r num">{fmt.int(r.in_market_hours)}</td>
          <td className="r">
            <Sharpe value={r.pair_90d_sharpe} />
          </td>
          <td className="r">
            <Sharpe value={r.record.untouched} />
          </td>
          <td className="r">
            <Sharpe value={r.record.dev} />
          </td>
          <td className="r pr-3.5">
            <Sharpe value={r.record.holdout} />
          </td>
        </tr>
      ))}
    </>
  )
}

export function PairDayView({ doc }: { doc: PairDay }) {
  const [pick, setPick] = useState(doc.detail[0]?.key ?? "")
  const [all, setAll] = useState(false)
  const detail = doc.detail.find((d) => d.key === pick) ?? doc.detail[0]
  const start = Date.parse(`${doc.from}T00:00:00Z`) / 1000
  const series = useMemo<SeriesSpec[]>(() => [{ kind: "candles", data: doc.candles, markers: markers(detail?.trades ?? []), muteBefore: start }, ...levels(detail?.trades ?? [])], [doc.candles, detail, start])
  const s = doc.summary
  const coin = ticker(doc.symbol)
  const one = doc.days === 1
  const held = doc.book.filter((b) => b.weight !== 0)
  const row = Object.fromEntries(doc.tactics.map((r) => [r.key, r]))
  const best = doc.tactics[0]
  const worst = doc.tactics[doc.tactics.length - 1]
  const total = doc.tactics.reduce((sum, r) => sum + r.pnl, 0)
  const tied = doc.tactics.filter((r) => r.pnl === best?.pnl).length
  const shown = all ? doc.tactics : [...doc.tactics.slice(0, 15), ...doc.tactics.slice(-5)]
  const record = detail ? row[detail.key]?.record : undefined
  const inBook = held.length ? held.map((b) => `${when.dayShort(b.day)} ${b.weight > 0 ? "лонг" : "шорт"} ${fmt.pctPlain(100 * Math.abs(b.weight), 2)}`).join("; ") : doc.book_known ? "не було" : "немає даних"
  return (
    <div>
      <p className="mb-3 flex items-center gap-1.5 text-[13px] text-text-2">
        {s.tactics} тактик окремо торгували {coin} {one ? when.day(doc.from) : `з ${when.day(doc.from)} по ${when.day(doc.to)}`}, кожна з {fmt.usd0(doc.capital)} і плечем {fmt.times(doc.leverage)}
        <Tip align="start">Це перевірка простих правил на одній парі, а не повтор роботи бота Квант: бот щодня тримає портфель із кількох десятків монет. За одним днем тактику не обирають: чи вміє вона заробляти, показує її історія (Sharpe).</Tip>
      </p>
      <Dock panels={PANELS} />
      <div className="grid items-start gap-3 lg:grid-cols-12">
        <Panel id="pair.summary" title="Підсумок" index={0} className="lg:col-span-12" bodyClass="grid grid-cols-1 gap-x-6 gap-y-4 p-4 sm:grid-cols-2 lg:grid-cols-4" summary={`бот ${doc.bot ? fmt.pct(doc.bot.return_pct) : "—"} · тактики разом ${fmt.pnl(total)}`}>
          <Figure
            label={`Бот Квант, уся книга`}
            value={doc.bot ? <Signed value={doc.bot.return_pct}>{doc.bot.pnl != null ? fmt.pnl(doc.bot.pnl) : fmt.pct(doc.bot.return_pct)}</Signed> : <span className="text-text-3">—</span>}
            tip={
              <>
                {doc.bot ? (doc.bot.source === "paper" ? `Віртуальний рахунок бота від ребалансу цього дня до наступного, з комісіями й фандінгом: ${fmt.pct(doc.bot.return_pct)}.` : "Тест бота на історії; моделі цього дня не бачили.") : "День поза віртуальним рахунком і тестом на історії."} {coin} у книзі: {inBook}.
              </>
            }
          />
          <Figure label={`Ціна ${coin}`} value={<Signed value={doc.price_move_pct}>{fmt.pct(doc.price_move_pct)}</Signed>} tip="Від ціни на початку до ціни в кінці тесту. Ціни в угодах гірші на проковзування 0,03 %." />
          <Figure label={`Усі ${s.tactics} тактик разом`} value={<Money value={total} />} tip={`З ${fmt.usd0(doc.capital * s.tactics)}. У плюсі ${s.positive}, у мінусі ${s.negative}, без угод ${s.flat}.`} />
          <Figure
            label="Найкраща / найгірша"
            value={
              <>
                <Money value={best?.pnl} /> <span className="text-text-3">/</span> <Money value={worst?.pnl} />
              </>
            }
            tip={`Найкраща: ${best?.label.split(";")[0]}${tied > 1 ? ` (і ще ${tied - 1} з таким самим результатом)` : ""}; найгірша: ${worst?.label.split(";")[0]}. Один день нічого не доводить: на всіх ліквідних ф’ючерсах за 2021–2026 ${s.robust ? `у всіх трьох періодах заробляли лише ${s.robust} з ${s.tactics}` : `жодна з ${s.tactics} тактик не заробляла в усіх трьох періодах`}.`}
          />
        </Panel>
        <Panel
          id="pair.chart"
          title="Угоди тактики"
          index={1}
          className="lg:col-span-8"
          summary={detail?.title}
          tip="Кнопки: найкраща тактика дня, ще дві найкращі з інших правил, тактика з найкращим Sharpe за 2023–24 (її обрали б за історією, не знаючи цього дня) і найгірша тактика дня."
          bodyClass="px-3 pb-3"
        >
          <div className="flex flex-wrap gap-1.5 pb-2.5" role="group" aria-label="Тактика на графіку">
            {doc.detail.map((d) => (
              <button
                key={d.key}
                type="button"
                aria-pressed={d.key === detail?.key}
                onClick={() => setPick(d.key)}
                title={[d.role && ROLE_UA[d.role], d.key === doc.reference && d.role !== "reference" && ROLE_UA.reference].filter(Boolean).join(" · ")}
                className={clsx("flex h-auto flex-col items-start rounded-lg border px-2.5 py-1 text-left text-[12px] leading-snug transition-colors", d.key === detail?.key ? "border-text bg-raised" : "border-line hover:border-line-strong hover:bg-raised")}
              >
                <span className="text-[10.5px] text-text-3">{[d.role && ROLE_UA[d.role], d.key === doc.reference && d.role !== "reference" && ROLE_UA.reference].filter(Boolean).join(" · ")}</span>
                <span className="font-medium">
                  {d.title ?? d.label.split(";")[0]} · <Money value={d.pnl ?? row[d.key]?.pnl} />
                </span>
              </button>
            ))}
          </div>
          <TimeChart series={series} height={340} label={`Свічки ${doc.symbol} з угодами тактики`} />
          <p className="mt-1.5 flex items-center gap-1.5 text-[12px] text-text-3">
            ▲ лонг · ▼ шорт · коло — вихід · пунктир — стоп і тейк
            <Tip align="start">Сірі свічки — попередня доба для контексту; тактика торгувала лише кольорові. Червоний пунктир — стоп-лос угоди, зелений — тейк-профіт. Трейлінг-стоп рухається за ціною, тож показано його початковий рівень.</Tip>
          </p>
          {detail && (
            <p className="mt-2 flex items-start gap-1.5 text-[13px]">
              <span>
                <b>{detail.title ?? detail.label.split(";")[0]}.</b> {detail.about ?? detail.label}
              </span>
              {record && (
                <Tip align="end">
                  Ця тактика на всіх ліквідних ф’ючерсах, Sharpe: 2021–23 {fmt.ratio(record.untouched)}, 2023–24 {fmt.ratio(record.dev)}, 2025–26 {fmt.ratio(record.holdout)}. Sharpe — річний прибуток, поділений на коливання: понад 1 добре, нижче 0 тактика втрачала.
                </Tip>
              )}
            </p>
          )}
        </Panel>
        <Panel id="pair.conditions" title="Умови тесту" index={2} className="lg:col-span-4" summary={`плече ${fmt.times(doc.leverage)}`}>
          <dl className="divide-y divide-line text-[12.5px]">
            {(
              [
                ["Капітал на тактику", fmt.usd0(doc.capital)],
                ["Плече", fmt.times(doc.leverage), `Плече ${doc.leverage_rule}.`],
                ["Комісія + проковзування", "0,05 % + 0,03 %", "На вхід і стільки ж на вихід. Фандінг і ліквідацію враховано."],
                ...(doc.atr_pct ? [["ATR перед тестом", `${fmt.pctPlain(doc.atr_pct, 2)} за годину`, "Середній хід ціни за годину за 14 год до початку тесту. Стопи й тейки тактик задано в ATR."]] : []),
                ["Дані", `${plural(doc.bars_in_window, "свічка", "свічки", "свічок")} по 1 год`, `І ще ${fmt.int(Math.round(doc.warmup_bars / 24))} днів перед тестом, щоб порахувати індикатори; ${doc.source}. Позицію, відкриту в кінці тесту, закрито за ціною останньої свічки.`],
              ] as [string, string, string?][]
            ).map(([k, v, tip]) => (
              <div key={k} className="flex items-center justify-between gap-3 px-3.5 py-2">
                <dt className="flex items-center gap-1.5 text-text-2">
                  {k}
                  {tip && <Tip align="start">{tip}</Tip>}
                </dt>
                <dd className="font-medium">{v}</dd>
              </div>
            ))}
          </dl>
        </Panel>
        {detail && (
          <Panel id="pair.trades" title={`Угоди: ${detail.title ?? detail.label.split(";")[0]}`} index={3} className="lg:col-span-12" summary={plural(detail.trades.length, "угода", "угоди", "угод")}>
            {detail.trades.length ? (
              <div className="overflow-x-auto">
                <table className="agate min-w-[900px]">
                  <thead>
                    <tr>
                      <th className="pl-3.5">Бік</th>
                      <th>Вхід</th>
                      <th className="r">Ціна</th>
                      <th className="r">Стоп</th>
                      <th className="r">Тейк</th>
                      <th>Вихід</th>
                      <th className="r">Ціна</th>
                      <th>Чому вийшла</th>
                      <th className="r">% рахунку</th>
                      <th className="r">P&L</th>
                      <th className="pr-3.5">
                        Індикатори <Tip align="end">{LEGEND}</Tip>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {detail.trades.map((t) => (
                      <tr key={t.entry_time}>
                        <td className={clsx("pl-3.5 font-semibold", t.side === "LONG" ? "text-gain" : "text-loss")}>{t.side === "LONG" ? "лонг" : "шорт"}</td>
                        <td className="num">{isoHour(t.entry_time)}</td>
                        <td className="r num">{fmt.price(t.entry)}</td>
                        <td className="r num text-text-2">{t.stop ? fmt.price(t.stop, t.entry) : "—"}</td>
                        <td className="r num text-text-2">{t.take ? fmt.price(t.take, t.entry) : "—"}</td>
                        <td className="num">{isoHour(t.exit_time)}</td>
                        <td className="r num">{fmt.price(t.exit, t.entry)}</td>
                        <td>{exitReason(t.reason)}</td>
                        <td className="r num">{fmt.pct(t.return_on_margin_pct)}</td>
                        <td className="r">
                          <Money value={t.pnl} />
                        </td>
                        <td className="max-w-[26rem] truncate pr-3.5 text-[11.5px] text-text-3" title={Object.entries(t.why).filter(([k]) => k in WHY).map(([k, v]) => `${WHY[k]![0]} ${WHY[k]![1](v)}`).join("\n")}>
                          {Object.entries(t.why)
                            .filter(([k]) => k in WHY)
                            .map(([k, v]) => `${WHY[k]![0]} ${WHY[k]![1](v)}`)
                            .join(" · ")}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                  <tfoot>
                    <tr>
                      <td colSpan={9} className="pl-3.5 font-semibold">
                        Разом
                      </td>
                      <td className="r font-semibold">
                        <Money value={detail.pnl ?? row[detail.key]?.pnl} />
                      </td>
                      <td />
                    </tr>
                  </tfoot>
                </table>
              </div>
            ) : (
              <p className="px-3.5 py-4 text-[13px] text-text-3">Тактика жодного разу не входила в ринок.</p>
            )}
          </Panel>
        )}
        <Panel id="pair.families" title="Тактики за типом" index={4} className="lg:col-span-4">
          <table className="agate">
            <thead>
              <tr>
                <th className="pl-3.5">Тип</th>
                <th className="r">Тактик</th>
                <th className="r">У плюсі</th>
                <th className="r pr-3.5">Разом</th>
              </tr>
            </thead>
            <tbody>
              {(Object.keys(FAMILY_UA) as TacticFamily[]).map((f) => (
                <tr key={f}>
                  <td className="pl-3.5">{FAMILY_UA[f]}</td>
                  <td className="r num">{doc.families[f]?.tactics ?? 0}</td>
                  <td className="r num">{doc.families[f]?.positive ?? 0}</td>
                  <td className="r pr-3.5">
                    <Money value={doc.families[f]?.pnl_sum} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>
        <Panel
          id="pair.tactics"
          title={all ? `Усі ${doc.tactics.length} тактик` : "15 найкращих і 5 найгірших"}
          index={5}
          className="lg:col-span-8"
          tip={`Sharpe — річний прибуток тактики, поділений на її коливання: понад 1 добре, нижче 0 тактика втрачала. «На ${coin}, 90 днів» — на цій парі за 90 днів до тесту; три праві колонки — на всіх ліквідних ф’ючерсах: 07.2021–06.2023, 07.2023–12.2024, 01.2025–09.2026.`}
          actions={
            <button type="button" className="btn btn-ghost h-7 px-2.5 text-[12px]" onClick={() => setAll(!all)}>
              {all ? "Згорнути" : "Показати всі"}
            </button>
          }
        >
          <div className="overflow-x-auto">
            <table className="agate min-w-[760px]">
              <thead>
                <tr>
                  <th className="pl-3.5">Тактика</th>
                  <th className="r">P&L</th>
                  <th className="r">Год у ринку</th>
                  <th className="r">{coin}, 90 днів</th>
                  <th className="r">2021–23</th>
                  <th className="r">2023–24</th>
                  <th className="r pr-3.5">2025–26</th>
                </tr>
              </thead>
              <tbody>
                <TacticRows rows={shown} />
              </tbody>
            </table>
          </div>
        </Panel>
      </div>
    </div>
  )
}
