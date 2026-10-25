import { useNavigate } from "react-router-dom"

import { EvidenceChart } from "../components/EvidenceChart"
import { Empty, Headline, Signed } from "../components/Print"
import { fmt, when } from "../lib/format"
import { useCreateJob, useEvidence } from "../lib/hooks"
import { Loading, Page } from "./Overview"

export function Evidence() {
  const evidence = useEvidence()
  const create = useCreateJob()
  const navigate = useNavigate()
  const e = evidence.data
  return (
    <Page>
      <div className="pt-5">
        <Headline
          as="h1"
          title="Докази"
          dek="Бойова конфігурація Кванта на всій історії, $1 000 від липня 2021, витрати й фандінг враховано. Кожен день оцінено моделлю, що його не бачила; періоди відрізняються тим, скільки рішень на них ухвалювалось."
        />
      </div>
      <section className="rule-heavy pt-4">
        {e ? <EvidenceChart evidence={e} height={340} /> : evidence.isLoading ? <Loading what="докази" /> : <Empty>Докази ще не зібрано.</Empty>}
        {!e && !evidence.isLoading && (
          <button type="button" className="btn" onClick={() => create.mutate({ kind: "quant_evidence", params: {} }, { onSuccess: (job) => navigate(`/lab/${job.id}`) })}>
            Зібрати докази
          </button>
        )}
      </section>
      {e && (
        <>
          <section className="rule-heavy mt-8 overflow-x-auto pt-3">
            <Headline as="h2" title="Періоди" dek={`Уся історія: ${fmt.usd0(e.stats.start_equity)} → ${fmt.usd(e.stats.final_equity)}, ${fmt.pct(e.stats.annual_return_pct, 1)} на рік, Sharpe ${fmt.ratio(e.stats.sharpe)}, найбільше просідання ${fmt.pct(e.stats.max_drawdown_pct, 1)}. Зібрано ${when.dateTime(e.built_at)}.`} />
            <table className="agate min-w-[860px]">
              <thead>
                <tr>
                  <th>Період</th>
                  <th>Статус даних</th>
                  <th>Дати</th>
                  <th className="r">Дохід</th>
                  <th className="r">Річний</th>
                  <th className="r">Sharpe</th>
                  <th className="r">Просідання</th>
                  <th className="r">Найгірший день</th>
                  <th className="r">Місяці в плюсі</th>
                </tr>
              </thead>
              <tbody>
                {e.periods.map((p) => (
                  <tr key={p.key}>
                    <td className="font-semibold">{p.name}</td>
                    <td className="text-ink-2">{p.note}</td>
                    <td className="num whitespace-nowrap">
                      {when.dayShort(p.from)} — {when.day(p.to)}
                    </td>
                    <td className="r">
                      <Signed value={p.stats.return_pct} digits={1}>{fmt.pct(p.stats.return_pct, 1)}</Signed>
                    </td>
                    <td className="r num">{fmt.pct(p.stats.annual_return_pct, 1)}</td>
                    <td className="r num">{fmt.ratio(p.stats.sharpe)}</td>
                    <td className="r num">{fmt.pct(p.stats.max_drawdown_pct, 1)}</td>
                    <td className="r num">{fmt.pct(p.stats.worst_day_pct, 1)}</td>
                    <td className="r num">
                      {p.stats.positive_months} з {p.stats.months}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
          <section className="rule-heavy mt-8 grid grid-cols-1 gap-x-8 gap-y-6 pt-3 md:grid-cols-3">
            <article>
              <h3 className="head text-[1.25rem] font-extrabold">Що тут чесно</h3>
              <p className="mt-1 text-[13.5px] text-ink-2">
                Незайманий період 2021–2023 перебудовано з нуля і ніколи не використано для вибору: стратегія там у плюсі в кожному півріччі, зокрема під час крахів LUNA і FTX. Форвард-тест — дні, яких не бачила жодна модель.
              </p>
            </article>
            <article className="md:colrule md:pl-8">
              <h3 className="head text-[1.25rem] font-extrabold">Що оптимістично</h3>
              <p className="mt-1 text-[13.5px] text-ink-2">
                На перевірочному періоді 2023–2024 обирались налаштування, тож його цифри завищені. Новий період 2025–2026 слугував лише вето для змін, але результати багатьох варіантів на ньому я бачив — він не ідеально чистий.
              </p>
            </article>
            <article className="md:colrule md:pl-8">
              <h3 className="head text-[1.25rem] font-extrabold">Чого чекати</h3>
              <p className="mt-1 text-[13.5px] text-ink-2">
                Близько 25–55 % на рік при експозиції 2× із просіданнями до ~30 %, найгірші дні до −12 % — це приблизно 0,1 % на день. Повний журнал гіпотез і відкинутих ідей — у RESEARCH.md.
              </p>
            </article>
          </section>
        </>
      )}
    </Page>
  )
}
