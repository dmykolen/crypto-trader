import { useNavigate } from "react-router-dom"

import { EvidenceChart } from "../components/EvidenceChart"
import { Signed } from "../components/Print"
import { Dock, Odometer, Panel, Tip } from "../components/ui"
import { fmt, when } from "../lib/format"
import { useCreateJob, useEvidence } from "../lib/hooks"
import { Loading, Page } from "./Overview"

const PANELS = [
  { id: "evidence.chart", title: "Рахунок на історії" },
  { id: "evidence.periods", title: "Періоди" },
  { id: "evidence.notes", title: "Як читати" },
]

const NOTES = [
  {
    title: "Що тут чесно",
    text: "Незайманий період 2021–2023 перебудовано з нуля і ніколи не використано для вибору. Там стратегія в плюсі, але не щопівроку: перше півріччя 2022 (крах LUNA) — мінус 12 %. Форвард-тест — дні, яких не бачила жодна модель.",
  },
  { title: "Що оптимістично", text: "На перевірочному періоді 2023–2024 обирались налаштування, тож його цифри завищені. Новий період 2025–2026 слугував лише вето для змін, але результати багатьох варіантів на ньому я бачив." },
  { title: "Чого чекати", text: "Де налаштування не обирались — 16–42 % на рік при плечі 2×, просідання до −40 %, найгірший день до −23 %: це шорт монети, яку пампнули за одну добу. Бувають і збиткові півроку." },
]

export function Evidence() {
  const evidence = useEvidence()
  const create = useCreateJob()
  const navigate = useNavigate()
  const e = evidence.data
  if (evidence.isLoading)
    return (
      <Page>
        <Loading what="докази" />
      </Page>
    )
  return (
    <Page>
      <div className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-2">
        <h1 className="text-[20px] font-semibold tracking-[-0.01em]">Докази</h1>
        <Tip align="start">Бойова конфігурація Кванта на всій історії, $1 000 від липня 2021, витрати й фандінг враховано. Кожен день оцінено моделлю, яка його не бачила.</Tip>
        {e && (
          <span className="flex items-baseline gap-2">
            <Odometer text={fmt.usd(e.stats.final_equity)} className="display text-[22px] font-semibold" />
            <span className="text-[12.5px] text-text-3">
              з {fmt.usd0(e.stats.start_equity)} · {fmt.pct(e.stats.annual_return_pct, 1)} на рік · Sharpe {fmt.ratio(e.stats.sharpe)} · просідання {fmt.pct(e.stats.max_drawdown_pct, 1)}
            </span>
          </span>
        )}
      </div>
      {!e ? (
        <div className="panel p-6 text-center">
          <p className="text-[13px] text-text-3">Докази ще не зібрано.</p>
          <button type="button" className="btn mt-3" onClick={() => create.mutate({ kind: "quant_evidence", params: {} }, { onSuccess: (job) => navigate(`/lab/${job.id}`) })}>
            Зібрати докази
          </button>
        </div>
      ) : (
        <>
          <Dock panels={PANELS} />
          <div className="grid items-start gap-3 lg:grid-cols-12">
            <Panel id="evidence.chart" title="Рахунок на історії" index={0} className="lg:col-span-12" summary={`${fmt.usd0(e.stats.start_equity)} → ${fmt.usd(e.stats.final_equity)}`} bodyClass="px-3 pb-3" tip={`Логарифмічна шкала. Смуги — періоди перевірки. Зібрано ${when.dateTime(e.built_at)}.`}>
              <EvidenceChart evidence={e} height={360} />
            </Panel>
            <Panel id="evidence.periods" title="Періоди" index={1} className="lg:col-span-12" summary={`${e.periods.length}`}>
              <div className="overflow-x-auto">
                <table className="agate min-w-[860px]">
                  <thead>
                    <tr>
                      <th className="pl-3.5">Період</th>
                      <th>Дати</th>
                      <th className="r">Дохід</th>
                      <th className="r">Річний</th>
                      <th className="r">Sharpe</th>
                      <th className="r">Просідання</th>
                      <th className="r">Найгірший день</th>
                      <th className="r pr-3.5">Місяці в плюсі</th>
                    </tr>
                  </thead>
                  <tbody>
                    {e.periods.map((p) => (
                      <tr key={p.key}>
                        <td className="pl-3.5">
                          <span className="flex items-center gap-1.5 font-semibold">
                            {p.name}
                            <Tip align="start">{p.note}</Tip>
                          </span>
                        </td>
                        <td className="num whitespace-nowrap text-text-2">
                          {when.day(p.from)} — {when.day(p.to)}
                        </td>
                        <td className="r">
                          <Signed value={p.stats.return_pct} digits={1}>
                            {fmt.pct(p.stats.return_pct, 1)}
                          </Signed>
                        </td>
                        <td className="r num">{fmt.pct(p.stats.annual_return_pct, 1)}</td>
                        <td className="r num">{fmt.ratio(p.stats.sharpe)}</td>
                        <td className="r num">{fmt.pct(p.stats.max_drawdown_pct, 1)}</td>
                        <td className="r num">{fmt.pct(p.stats.worst_day_pct, 1)}</td>
                        <td className="r num pr-3.5">
                          {p.stats.positive_months} з {p.stats.months}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Panel>
            <Panel id="evidence.notes" title="Як читати" index={2} className="lg:col-span-12" bodyClass="grid gap-3 p-3.5 md:grid-cols-3">
              {NOTES.map((n) => (
                <p key={n.title} className="flex items-center gap-1.5 text-[13px] font-medium">
                  {n.title}
                  <Tip align="start">{n.text}</Tip>
                </p>
              ))}
            </Panel>
          </div>
        </>
      )}
    </Page>
  )
}
