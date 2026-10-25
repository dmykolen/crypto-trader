import { ArrowLeft, Square } from "lucide-react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { Link, useParams } from "react-router-dom"

import { ErrorNote, Headline, KV } from "../components/Print"
import { BookListing, DayBook, EquityCharts, MonthlyTable, ReplayResult, StatsTable, type DayView, type ReplayDoc } from "../components/Results"
import { api } from "../lib/api"
import { fmt, when } from "../lib/format"
import { useJob } from "../lib/hooks"
import type { BookSummary, SeriesResult } from "../lib/types"
import { StatusMark } from "./Lab"
import { Loading, Page } from "./Overview"

const FAMILY: Record<string, string> = { blend: "суміш двох моделей", edge: "модель бар’єра", xs7: "7-денна модель" }

const PARAM_FMT: Record<string, (v: unknown) => string> = {
  capital: (v) => fmt.usd0(Number(v)),
  gross: (v) => fmt.times(Number(v), 1),
  short_cap: (v) => fmt.pctPlain(100 * Number(v), 1),
  band: (v) => fmt.pctPlain(100 * Number(v), 2),
  family: (v) => FAMILY[String(v)] ?? String(v),
  skip_download: (v) => (v ? "так" : "ні"),
  start: (v) => when.day(String(v)),
  end: (v) => when.day(String(v)),
  day: (v) => when.day(String(v)),
}

const PARAM_UA: Record<string, string> = {
  start: "з дня",
  end: "по день",
  day: "день",
  days: "днів",
  capital: "капітал",
  gross: "експозиція",
  per_side: "позицій на сторону",
  short_cap: "ліміт шорту",
  band: "коридор",
  beta_days: "бета, днів",
  family: "сигнал",
  skip_download: "без завантаження",
}

function params(p: Record<string, unknown>): string {
  return Object.entries(p)
    .filter(([, v]) => v !== null && v !== undefined)
    .map(([k, v]) => `${PARAM_UA[k] ?? k}\u00a0${(PARAM_FMT[k] ?? String)(v)}`)
    .join(" · ")
}

type PeriodResult = SeriesResult & { book_last_day?: BookSummary | null; sources?: { data: string; from: string; to: string }[]; book_next_day?: { longs: Record<string, number>; shorts: Record<string, number>; decided_at: string } }

function SeriesView({ result }: { result: PeriodResult }) {
  return (
    <div className="space-y-8">
      <div className="grid grid-cols-12 gap-x-6">
        <div className="col-span-12 lg:col-span-4">
          <h3 className="head text-[1.1rem] font-extrabold">Підсумок</h3>
          <StatsTable stats={result.stats} />
          {result.sources && (
            <p className="mt-2 text-[12px] text-ink-3">
              Дані: {result.sources.map((s) => `${s.data === "data_pre" ? "незайманий rebuild" : "основний набір"} ${s.from}…${s.to}`).join("; ")}.
            </p>
          )}
        </div>
        <div className="col-span-12 lg:col-span-8 lg:colrule lg:pl-6">
          <EquityCharts result={result} />
        </div>
      </div>
      <div>
        <h3 className="head text-[1.1rem] font-extrabold">Помісячно</h3>
        <MonthlyTable monthly={result.monthly} />
      </div>
      {result.book_last_day && <BookListing book={result.book_last_day} />}
      {result.book_next_day && (
        <BookListing
          title={`Книга на ${result.book_next_day.decided_at}`}
          book={{
            longs: Object.entries(result.book_next_day.longs).map(([symbol, weight]) => ({ symbol, weight })),
            shorts: Object.entries(result.book_next_day.shorts).map(([symbol, weight]) => ({ symbol, weight })),
            gross: [...Object.values(result.book_next_day.longs), ...Object.values(result.book_next_day.shorts)].reduce((a, v) => a + Math.abs(v), 0),
            net: [...Object.values(result.book_next_day.longs), ...Object.values(result.book_next_day.shorts)].reduce((a, v) => a + v, 0),
            positions: Object.keys(result.book_next_day.longs).length + Object.keys(result.book_next_day.shorts).length,
          }}
        />
      )}
    </div>
  )
}

function Plain({ value }: { value: Record<string, unknown> }) {
  return <KV rows={Object.entries(value).map(([k, v]) => [k, typeof v === "object" ? <code className="font-mono text-[11.5px]">{JSON.stringify(v)}</code> : String(v)])} />
}

export function JobPage() {
  const { id } = useParams()
  const job = useJob<unknown>(id)
  const client = useQueryClient()
  const cancel = useMutation({ mutationFn: () => api.cancelJob(id as string), onSettled: () => client.invalidateQueries({ queryKey: ["job", id] }) })
  if (job.isLoading) return <Page>{<Loading what="тест" />}</Page>
  if (!job.data) return <Page>{<ErrorNote error={job.error} />}</Page>
  const j = job.data
  const running = j.status === "running" || j.status === "queued"
  const result = j.result as Record<string, unknown> | undefined
  return (
    <Page>
      <div className="pt-5">
        <Link to="/lab" className="head inline-flex items-center gap-1 text-[14px] font-bold no-underline">
          <ArrowLeft size={14} aria-hidden /> Лабораторія
        </Link>
        <Headline as="h1" title={j.title} dek={params(j.params)}>
          {running && (
            <button type="button" className="btn btn-ghost" onClick={() => cancel.mutate()} disabled={cancel.isPending}>
              <Square size={13} aria-hidden /> Скасувати
            </button>
          )}
        </Headline>
        <p className="num flex flex-wrap items-center gap-x-3 text-[12.5px] text-ink-2" role="status">
          <StatusMark status={j.status} />
          <span>поставлено {when.dateTime(j.created_at)}</span>
          {j.finished_at && <span>завершено {when.dateTime(j.finished_at)}</span>}
          {running && j.progress && <span className="text-ink">{j.progress}</span>}
        </p>
        {running && <div className="mt-3 h-[3px] w-full overflow-hidden bg-shade" aria-hidden><div className="progress-run h-full w-1/3 bg-quant" /></div>}
      </div>
      <div className="rule-heavy mt-4 pt-5">
        {j.status === "failed" && (
          <div>
            <p className="text-loss">Тест упав: {j.error}</p>
            {j.trace && (
              <details className="mt-2">
                <summary className="cursor-pointer text-[13px] text-ink-2">Трасування</summary>
                <pre className="mt-2 overflow-x-auto bg-shade p-3 font-mono text-[11.5px] leading-relaxed">{j.trace}</pre>
              </details>
            )}
          </div>
        )}
        {j.status === "done" && result && (j.kind === "quant_period" || j.kind === "quant_forward") && <SeriesView result={result as unknown as PeriodResult} />}
        {j.status === "done" && result && j.kind === "quant_book" && <DayBook view={result as unknown as DayView} />}
        {j.status === "done" && result && j.kind === "notice_replay" && <ReplayResult doc={result as unknown as ReplayDoc} />}
        {j.status === "done" && result && (j.kind === "quant_retrain" || j.kind === "quant_evidence") && <Plain value={result} />}
        {running && <p className="text-ink-3">Результат з’явиться тут, щойно тест завершиться.</p>}
      </div>
    </Page>
  )
}
