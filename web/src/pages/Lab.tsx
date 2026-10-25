import clsx from "clsx"
import { useState, type ReactNode } from "react"
import { Link, useNavigate } from "react-router-dom"

import { Headline } from "../components/Print"
import { JOB_STATUS, when } from "../lib/format"
import { useCreateJob, useJobs, useNow } from "../lib/hooks"
import type { Job, JobKind } from "../lib/types"
import { Page } from "./Overview"


function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: ReactNode }) {
  return (
    <label className="block text-[12.5px] text-ink-2">
      {label}
      <span className="mt-1 block">{children}</span>
      {hint && <span className="mt-0.5 block text-[11.5px] text-ink-3">{hint}</span>}
    </label>
  )
}

const PERIODS = [
  { label: "Незайманий 2021–23", start: "2021-07-01", end: "2023-06-30" },
  { label: "Перевірочний 2023–24", start: "2023-07-01", end: "2024-12-31" },
  { label: "Новий 2025–26", start: "2025-01-01", end: "2026-09-30" },
  { label: "Усе 2021–26", start: "2021-07-01", end: "2026-09-30" },
]

const PROD = { capital: 1000, gross: 2, per_side: 30, short_cap: 4, band: 1, beta_days: 60, family: "blend" }

function Hint({ prod, value, unit = "" }: { prod: number | string; value: number | string; unit?: string }) {
  const differs = String(prod) !== String(value)
  return differs ? <span className="font-semibold text-live">{`у бою ${prod}${unit} — змінено`}</span> : <span aria-hidden>{"\u00a0"}</span>
}

function PeriodForm({ submit }: { submit: (params: Record<string, unknown>) => void }) {
  const [p, setP] = useState({ start: "2025-01-01", end: "2026-09-30", ...PROD })
  const set = (k: keyof typeof p) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setP({ ...p, [k]: e.target.type === "number" ? Number(e.target.value) : e.target.value })
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault()
        submit({ ...p, short_cap: p.short_cap / 100, band: p.band / 100 })
      }}
    >
      <div className="flex flex-wrap items-center gap-1.5 pb-3" role="group" aria-label="Готові періоди">
        <span className="mr-1 text-[12.5px] text-ink-2">Період:</span>
        {PERIODS.map((x) => (
          <button
            key={x.label}
            type="button"
            aria-pressed={p.start === x.start && p.end === x.end}
            className={clsx("btn h-7 px-2.5 text-[12.5px]", !(p.start === x.start && p.end === x.end) && "btn-ghost border-rule")}
            onClick={() => setP({ ...p, start: x.start, end: x.end })}
          >
            {x.label}
          </button>
        ))}
      </div>
      <p className="pb-3 text-[12.5px] text-ink-3">Усі значення за замовчуванням — бойові; змінені підсвічуються.</p>
      <div className="grid grid-cols-1 gap-x-5 gap-y-3 sm:grid-cols-3">
        <Field label="З дня (UTC)" hint="дані є з 1 лип. 2021">
          <input type="date" className="field w-full" min="2021-07-01" max="2026-09-30" value={p.start} onChange={set("start")} required />
        </Field>
        <Field label="По день (UTC)" hint="прогнози є до 30 вер. 2026">
          <input type="date" className="field w-full" min="2021-07-02" max="2026-09-30" value={p.end} onChange={set("end")} required />
        </Field>
        <Field label="Стартовий капітал, $" hint="результат масштабується лінійно">
          <input type="number" className="field w-full text-right" min={100} step={100} value={p.capital} onChange={set("capital")} />
        </Field>
        <Field label="Сигнал" hint={p.family === PROD.family ? "\u00a0" : <span className="font-semibold text-live">у бою суміш — змінено</span>}>
          <select className="field w-full" value={p.family} onChange={set("family")}>
            <option value="blend">суміш двох моделей</option>
            <option value="edge">модель бар’єра</option>
            <option value="xs7">7-денна модель</option>
          </select>
        </Field>
        <Field label="Експозиція (лонги + шорти), ×" hint={<Hint prod={PROD.gross} value={p.gross} unit="×" />}>
          <input type="number" className="field w-full text-right" min={0.5} max={6} step={0.5} value={p.gross} onChange={set("gross")} />
        </Field>
        <Field label="Позицій на кожну сторону" hint={<Hint prod={PROD.per_side} value={p.per_side} />}>
          <input type="number" className="field w-full text-right" min={5} max={100} value={p.per_side} onChange={set("per_side")} />
        </Field>
        <Field label="Найбільша вага шорту, %" hint={<Hint prod={PROD.short_cap} value={p.short_cap} unit=" %" />}>
          <input type="number" className="field w-full text-right" min={0.5} max={100} step={0.5} value={p.short_cap} onChange={set("short_cap")} />
        </Field>
        <Field label="Не торгувати зміни ваги менші за, %" hint={<Hint prod={PROD.band} value={p.band} unit=" %" />}>
          <input type="number" className="field w-full text-right" min={0} max={10} step={0.25} value={p.band} onChange={set("band")} />
        </Field>
        <Field label="Бета-хедж через BTC: вікно, днів" hint={p.beta_days === 0 ? "0 — без хеджу" : <Hint prod={PROD.beta_days} value={p.beta_days} />}>
          <input type="number" className="field w-full text-right" min={0} max={365} value={p.beta_days} onChange={set("beta_days")} />
        </Field>
      </div>
      <Submit>Порахувати період</Submit>
    </form>
  )
}

function Submit({ children }: { children: ReactNode }) {
  return (
    <div className="mt-5">
      <button type="submit" className="btn h-9 px-5 text-[14px]">
        {children}
      </button>
    </div>
  )
}

function DayForm({ submit }: { submit: (params: Record<string, unknown>) => void }) {
  const [day, setDay] = useState("2026-09-29")
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault()
        submit({ day })
      }}
    >
      <Field label="День (UTC)" hint="історія прогнозів: 2 лип. 2023 — 29 вер. 2026">
        <input type="date" className="field" min="2023-07-02" max="2026-09-29" value={day} onChange={(e) => setDay(e.target.value)} required />
      </Field>
      <Submit>Показати книгу дня</Submit>
    </form>
  )
}

function ForwardForm({ submit }: { submit: (params: Record<string, unknown>) => void }) {
  const [start, setStart] = useState("2026-10-01")
  const [end, setEnd] = useState("")
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault()
        submit(end ? { start, end } : { start })
      }}
    >
      <div className="flex flex-wrap gap-4">
        <Field label="З дня" hint="дні після 30 вер. 2026 моделі не бачили">
          <input type="date" className="field" min="2026-07-01" value={start} onChange={(e) => setStart(e.target.value)} required />
        </Field>
        <Field label="По день" hint="порожньо — по вчора">
          <input type="date" className="field" value={end} onChange={(e) => setEnd(e.target.value)} />
        </Field>
      </div>
      <Submit>Прогнати форвард-тест</Submit>
    </form>
  )
}

function ReplayForm({ submit }: { submit: (params: Record<string, unknown>) => void }) {
  const [day, setDay] = useState(new Date(Date.now() - 86400000).toISOString().slice(0, 10))
  const [days, setDays] = useState(1)
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault()
        submit({ day, days })
      }}
    >
      <div className="flex flex-wrap gap-4">
        <Field label="З дня (UTC)">
          <input type="date" className="field" value={day} onChange={(e) => setDay(e.target.value)} required />
        </Field>
        <Field label="Днів">
          <input type="number" className="field w-24" min={1} max={90} value={days} onChange={(e) => setDays(Number(e.target.value))} />
        </Field>
      </div>
      <Submit>Прогнати реплей анонсів</Submit>
    </form>
  )
}

function RetrainForm({ submit }: { submit: (params: Record<string, unknown>) => void }) {
  const [skip, setSkip] = useState(false)
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault()
        submit({ skip_download: skip })
      }}
    >
      <label className="flex items-center gap-2 text-[13px]">
        <input type="checkbox" checked={skip} onChange={(e) => setSkip(e.target.checked)} /> Не качати нові архіви, лише перебудувати панелі й моделі
      </label>
      <Submit>Перенавчити моделі</Submit>
    </form>
  )
}

const KINDS: { kind: JobKind; label: string; about: string; Form: (p: { submit: (params: Record<string, unknown>) => void }) => ReactNode }[] = [
  { kind: "quant_period", label: "Період на історії", about: "Бойова книга Кванта на будь-якому відрізку 2021–2026 з вашими параметрами. Навчання покрокове: кожен день оцінено моделлю, що його не бачила. Триває хвилину-дві.", Form: PeriodForm },
  { kind: "quant_book", label: "Книга за день", about: "Що Квант тримав у конкретний день: кожен лонг і шорт, вага, рух ціни та P&L на $1 000.", Form: DayForm },
  { kind: "quant_forward", label: "Форвард-тест", about: "Свіжі котирування всіх ліквідних ф’ючерсів з Binance → ознаки → фінальні моделі → книга день за днем. Перший запуск качає дані кілька хвилин.", Form: ForwardForm },
  { kind: "notice_replay", label: "Реплей анонсів", about: "Справжній торговий цикл бота Анонси на історичних тиках у трьох сценаріях затримки входу.", Form: ReplayForm },
  { kind: "quant_retrain", label: "Перенавчання", about: "Щоквартальне оновлення: нові місячні архіви, панелі ознак і фінальні моделі. Десятки хвилин; замінені моделі зберігаються для чесних бектестів.", Form: RetrainForm },
  {
    kind: "quant_evidence",
    label: "Перебудова доказів",
    about: "Перераховує криву капіталу 2021–2026 і статистику періодів для розділу «Докази».",
    Form: ({ submit }) => (
      <form
        onSubmit={(e) => {
          e.preventDefault()
          submit({})
        }}
      >
        <Submit>Перебудувати</Submit>
      </form>
    ),
  },
]

export function StatusMark({ status }: { status: Job["status"] }) {
  return (
    <span className={clsx("num inline-flex items-center gap-1.5 text-[12px]", status === "failed" && "text-loss", status === "done" && "text-ink-2", (status === "running" || status === "queued") && "font-semibold")}>
      <span
        aria-hidden
        className={clsx("inline-block h-2 w-2 rounded-full", status === "done" && "bg-gain", status === "failed" && "bg-loss", status === "cancelled" && "border border-ink-3", (status === "running" || status === "queued") && "animate-pulse bg-quant")}
      />
      {JOB_STATUS[status]}
    </span>
  )
}

function duration(job: Job, now: number): string {
  const start = job.started_at ?? job.created_at
  const end = job.finished_at ? new Date(job.finished_at).getTime() : now
  const s = Math.max(0, Math.round((end - new Date(start).getTime()) / 1000))
  return s < 60 ? `${s} с` : `${Math.floor(s / 60)} хв ${s % 60} с`
}

export function Lab() {
  const jobs = useJobs()
  const create = useCreateJob()
  const navigate = useNavigate()
  const now = useNow(1000)
  const [active, setActive] = useState<JobKind>("quant_period")
  const current = KINDS.find((k) => k.kind === active) ?? KINDS[0]!
  const submit = (params: Record<string, unknown>) => create.mutate({ kind: active, params }, { onSuccess: (job) => navigate(`/lab/${job.id}`) })
  return (
    <Page>
      <div className="pt-5">
        <Headline as="h1" title="Лабораторія" dek="Тести на історичних даних. Кожен тест іде окремим процесом, тож сторінку можна закрити: результат чекатиме тут." />
      </div>
      <div className="rule-heavy grid grid-cols-12 gap-x-6 pt-4">
        <section className="col-span-12 lg:col-span-8" aria-label="Новий тест">
          <div className="flex flex-wrap gap-x-1 border-b border-rule" role="tablist" aria-label="Вид тесту">
            {KINDS.map((k) => (
              <button
                key={k.kind}
                type="button"
                role="tab"
                aria-selected={k.kind === active}
                className={clsx("-mb-px border-b-[3px] px-3 pt-1 pb-1.5 text-[14px] font-semibold first:pl-0", k.kind === active ? "border-ink text-ink" : "border-transparent text-ink-2 hover:text-ink")}
                onClick={() => setActive(k.kind)}
              >
                {k.label}
              </button>
            ))}
          </div>
          <div className="pt-4" role="tabpanel">
            <p className="max-w-[72ch] pb-4 text-[13.5px] text-ink-2">{current.about}</p>
            <current.Form submit={submit} />
            {create.error && <p className="mt-3 text-[13px] text-loss">Не вдалося поставити тест: {(create.error as Error).message}</p>}
          </div>
        </section>
        <aside className="col-span-12 mt-8 lg:col-span-4 lg:mt-0 lg:colrule lg:pl-6" aria-labelledby="jobs">
          <h2 id="jobs" className="head text-[1.5rem] font-extrabold">
            Журнал тестів
          </h2>
          {jobs.data?.length ? (
            <ol className="mt-2 divide-y divide-rule/70 border-y border-rule/70">
              {jobs.data.map((j) => (
                <li key={j.id}>
                  <Link to={`/lab/${j.id}`} className="block py-2 no-underline hover:bg-shade">
                    <span className="flex items-baseline justify-between gap-2">
                      <span className="text-[13px] font-semibold">{j.title}</span>
                      <StatusMark status={j.status} />
                    </span>
                    <span className="num block text-[11.5px] text-ink-3">
                      {when.dateTime(j.created_at)} · {j.finished_at ? `тривав ${duration(j, now)}` : `іде ${duration(j, now)}`}
                      {j.progress && j.status === "running" ? ` · ${j.progress}` : ""}
                    </span>
                  </Link>
                </li>
              ))}
            </ol>
          ) : (
            <p className="py-4 text-ink-3">Тестів ще не було.</p>
          )}
        </aside>
      </div>
    </Page>
  )
}
