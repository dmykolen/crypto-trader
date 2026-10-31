import clsx from "clsx"
import { FileUp } from "lucide-react"
import { useState, type ReactNode } from "react"
import { Link, useNavigate } from "react-router-dom"

import { Dock, Panel, Pulse, Tip } from "../components/ui"
import { api } from "../lib/api"
import { fmt, JOB_STATUS, when } from "../lib/format"
import { useCreateJob, useJobs, useNow } from "../lib/hooks"
import type { Job, JobKind, Upload } from "../lib/types"
import { Page } from "./Overview"


function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: ReactNode }) {
  return (
    <label className="block text-[12.5px] text-text-2">
      {label}
      <span className="mt-1 block">{children}</span>
      {hint && <span className="mt-0.5 block text-[11.5px] text-text-3">{hint}</span>}
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
  return differs ? <span className="font-semibold text-text">{`у бою ${prod}${unit} — змінено`}</span> : <span aria-hidden>{"\u00a0"}</span>
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
        <span className="mr-1 text-[12.5px] text-text-2">Період:</span>
        {PERIODS.map((x) => (
          <button
            key={x.label}
            type="button"
            aria-pressed={p.start === x.start && p.end === x.end}
            className={clsx("btn h-7 px-2.5 text-[12.5px]", !(p.start === x.start && p.end === x.end) && "btn-ghost border-line")}
            onClick={() => setP({ ...p, start: x.start, end: x.end })}
          >
            {x.label}
          </button>
        ))}
      </div>
      <p className="pb-3 text-[12.5px] text-text-3">Усі значення за замовчуванням — бойові; змінені підсвічуються.</p>
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
        <Field label="Сигнал" hint={p.family === PROD.family ? "\u00a0" : <span className="font-semibold text-text">у бою суміш — змінено</span>}>
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

const yesterday = () => new Date(Date.now() - 86400000).toISOString().slice(0, 10)

function PairForm({ submit }: { submit: (params: Record<string, unknown>) => void }) {
  const [symbol, setSymbol] = useState("SOLUSDT")
  const [day, setDay] = useState(yesterday())
  const [days, setDays] = useState(1)
  const [leverage, setLeverage] = useState("")
  const [upload, setUpload] = useState<Upload | null>(null)
  const [error, setError] = useState("")
  const [busy, setBusy] = useState(false)
  const [fileName, setFileName] = useState("")
  const pair = symbol.trim().toUpperCase().replace(/\/|-/g, "")
  const onFile = async (file: File | undefined) => {
    setError("")
    setUpload(null)
    setFileName(file?.name ?? "")
    if (!file) return
    setBusy(true)
    try {
      setUpload(await api.upload(file))
      setDay("")
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault()
        submit({ symbol: pair.endsWith("USDT") || upload ? pair : `${pair}USDT`, days, ...(day ? { day } : {}), ...(leverage ? { leverage: Number(leverage) } : {}), ...(upload ? { upload: upload.upload } : {}) })
      }}
    >
      <div className="grid grid-cols-1 gap-x-5 gap-y-3 sm:grid-cols-4">
        <Field label="Пара" hint="будь-який ф’ючерс USDⓈ-M">
          <input className="field w-full uppercase" value={symbol} onChange={(e) => setSymbol(e.target.value)} required />
        </Field>
        <Field label="З дня (UTC)" hint={upload ? "порожньо — останній день файлу" : "за замовчуванням — учора"}>
          <input type="date" className="field w-full" value={day} max={yesterday()} onChange={(e) => setDay(e.target.value)} required={!upload} />
        </Field>
        <Field label="Днів" hint="1–30">
          <input type="number" className="field w-full text-right" min={1} max={30} value={days} onChange={(e) => setDays(Number(e.target.value))} />
        </Field>
        <Field label="Плече, ×" hint="порожньо — авто, ≤ 5×">
          <input type="number" className="field w-full text-right" min={1} max={20} step={0.5} value={leverage} placeholder="авто" onChange={(e) => setLeverage(e.target.value)} />
        </Field>
      </div>
      <div className="mt-3">
        <Field
          label="Свої котирування (необов’язково)"
          hint={
            busy ? "завантажую …" : upload ? `${fmt.int(upload.bars)} годинних свічок, ${when.dateTime(upload.from)} — ${when.dateTime(upload.to)}` : "CSV: час, open, high, low, close[, volume]; свічки 1 год або дрібніші. Для індикаторів потрібно ≈ 300 свічок до обраного дня."
          }
        >
          <span className="flex items-center gap-2.5">
            <span className="btn btn-ghost h-8 px-3 has-[+input:focus-visible]:outline-2 has-[+input:focus-visible]:outline-brand">
              <FileUp size={14} aria-hidden /> Вибрати CSV
            </span>
            <input type="file" accept=".csv,text/csv" className="sr-only" onChange={(e) => void onFile(e.target.files?.[0])} />
            <span className="min-w-0 truncate text-[12.5px] text-text-3">{fileName || "файл не вибрано"}</span>
          </span>
        </Field>
        {error && <p className="mt-1 text-[12.5px] font-semibold">⚠ Файл не прочитано: {error}</p>}
      </div>
      <Submit>Показати день</Submit>
    </form>
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
  {
    kind: "quant_day",
    label: "Пара за день",
    about: "Котирування однієї пари за вчора чи будь-який день (або ваш CSV) → 305 тактик на індикаторах, патернах і моделі з плечем, стопами й повторним входом → угоди кожної на графіку, поруч — історія цієї ж тактики на всіх ф’ючерсах і позиція книги Кванта. Триває 10–20 секунд.",
    Form: PairForm,
  },
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
    <span className={clsx("inline-flex flex-none items-center gap-1.5 text-[12px]", status === "failed" || status === "running" || status === "queued" ? "font-semibold text-text" : status === "done" ? "text-text-2" : "text-text-3")}>
      {status === "failed" ? "⚠" : <Pulse state={status === "running" || status === "queued" ? "on" : "off"} />}
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

const PANELS = [
  { id: "lab.new", title: "Новий тест" },
  { id: "lab.jobs", title: "Журнал тестів" },
]

export function Lab() {
  const jobs = useJobs()
  const create = useCreateJob()
  const navigate = useNavigate()
  const now = useNow(1000)
  const [active, setActive] = useState<JobKind>("quant_day")
  const current = KINDS.find((k) => k.kind === active) ?? KINDS[0]!
  const submit = (params: Record<string, unknown>) => create.mutate({ kind: active, params }, { onSuccess: (job) => navigate(`/lab/${job.id}`) })
  const running = (jobs.data ?? []).filter((j) => j.status === "running" || j.status === "queued").length
  return (
    <Page>
      <div className="mb-3 flex items-center gap-3">
        <h1 className="text-[20px] font-semibold tracking-[-0.01em]">Лабораторія</h1>
        <Tip align="start">Тести на історичних даних. Кожен тест іде окремим процесом, тож сторінку можна закрити: результат чекатиме в журналі.</Tip>
      </div>
      <Dock panels={PANELS} />
      <div className="grid items-start gap-3 lg:grid-cols-12">
        <Panel
          id="lab.new"
          title="Новий тест"
          index={0}
          className="lg:col-span-8"
          summary={current.label}
          bodyClass="p-4"
        >
          <div className="mb-4 flex items-center gap-2">
            <div className="-ml-1 flex min-w-0 gap-1 overflow-x-auto [scrollbar-width:none]" role="tablist" aria-label="Вид тесту">
              {KINDS.map((k) => (
                <button
                  key={k.kind}
                  type="button"
                  role="tab"
                  aria-selected={k.kind === active}
                  onClick={() => setActive(k.kind)}
                  className={clsx("h-7 flex-none rounded-md px-2.5 text-[12px] whitespace-nowrap transition-colors", k.kind === active ? "bg-press text-text" : "text-text-3 hover:bg-raised hover:text-text")}
                >
                  {k.label}
                </button>
              ))}
            </div>
            <Tip align="end" label={`Що таке «${current.label}»`}>
              {current.about}
            </Tip>
          </div>
          <current.Form submit={submit} />
          {create.error && <p className="mt-3 text-[13px] font-semibold">⚠ Не вдалося поставити тест: {(create.error as Error).message}</p>}
        </Panel>
        <Panel id="lab.jobs" title="Журнал тестів" index={1} className="lg:col-span-4" summary={running ? `рахується: ${running}` : `${jobs.data?.length ?? 0}`} bodyClass="max-h-[640px] overflow-auto">
          {jobs.data?.length ? (
            <ol className="divide-y divide-line">
              {jobs.data.map((j) => (
                <li key={j.id}>
                  <Link to={`/lab/${j.id}`} className="block px-3.5 py-2.5 no-underline transition-colors hover:bg-raised">
                    <span className="flex items-baseline justify-between gap-2">
                      <span className="truncate text-[13px] font-medium">{j.title}</span>
                      <StatusMark status={j.status} />
                    </span>
                    <span className="num block text-[11.5px] text-text-3">
                      {when.dateTime(j.created_at)} · {j.finished_at ? `тривав ${duration(j, now)}` : `іде ${duration(j, now)}`}
                      {j.progress && j.status === "running" ? ` · ${j.progress}` : ""}
                    </span>
                  </Link>
                </li>
              ))}
            </ol>
          ) : (
            <p className="px-3.5 py-6 text-[13px] text-text-3">Тестів ще не було.</p>
          )}
        </Panel>
      </div>
    </Page>
  )
}
