import { ArrowLeft, Square } from "lucide-react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { Link, useParams } from "react-router-dom"

import { ErrorNote, KV } from "../components/Print"
import { PairDayView } from "../components/PairDay"
import { BookListing, bookLine, DayBook, DrawdownChart, EquityChart, MonthlyTable, ReplayResult, StatsTable, type DayView, type ReplayDoc } from "../components/Results"
import { Dock, Panel } from "../components/ui"
import { api } from "../lib/api"
import { fmt, when } from "../lib/format"
import { useJob } from "../lib/hooks"
import type { BookSummary, PairDay, SeriesResult } from "../lib/types"
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
  leverage: (v) => fmt.times(Number(v), 1),
  upload: () => "так",
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
  symbol: "пара",
  leverage: "плече",
  upload: "свій CSV",
}

function params(p: Record<string, unknown>): string {
  return Object.entries(p)
    .filter(([k, v]) => v !== null && v !== undefined && !(k === "days" && v === 1))
    .map(([k, v]) => `${PARAM_UA[k] ?? k}\u00a0${(PARAM_FMT[k] ?? String)(v)}`)
    .join(" · ")
}

type PeriodResult = SeriesResult & { book_last_day?: BookSummary | null; sources?: { data: string; from: string; to: string }[]; book_next_day?: { longs: Record<string, number>; shorts: Record<string, number>; decided_at: string } }

function SeriesView({ result }: { result: PeriodResult }) {
  const next = result.book_next_day
  const nextBook: BookSummary | undefined = next && {
    longs: Object.entries(next.longs).map(([symbol, weight]) => ({ symbol, weight })),
    shorts: Object.entries(next.shorts).map(([symbol, weight]) => ({ symbol, weight })),
    gross: [...Object.values(next.longs), ...Object.values(next.shorts)].reduce((a, v) => a + Math.abs(v), 0),
    net: [...Object.values(next.longs), ...Object.values(next.shorts)].reduce((a, v) => a + v, 0),
    positions: Object.keys(next.longs).length + Object.keys(next.shorts).length,
  }
  const panels = [
    { id: "series.summary", title: "Підсумок" },
    { id: "series.equity", title: "Капітал" },
    { id: "series.drawdown", title: "Просідання від піку" },
    { id: "series.monthly", title: "Помісячно" },
    ...(result.book_last_day ? [{ id: "series.book", title: "Книга на останній день" }] : []),
    ...(next ? [{ id: "series.next", title: `Книга на ${next.decided_at}` }] : []),
  ]
  const sources = result.sources?.map((s) => `${s.data === "data_pre" ? "незайманий rebuild" : "основний набір"} ${s.from}…${s.to}`).join("; ")
  return (
    <>
      <Dock panels={panels} />
      <div className="grid items-start gap-3 lg:grid-cols-12">
        <Panel id="series.summary" title="Підсумок" index={0} className="lg:col-span-4 lg:row-span-2" summary={fmt.pct(result.stats.return_pct)} tip={sources && `Дані: ${sources}.`}>
          <StatsTable stats={result.stats} />
        </Panel>
        <Panel id="series.equity" title="Капітал" index={1} className="lg:col-span-8" bodyClass="px-3 pb-3" summary={`${fmt.usd0(result.stats.start_equity)} → ${fmt.usd(result.stats.final_equity)}`}>
          <EquityChart result={result} />
        </Panel>
        <Panel id="series.drawdown" title="Просідання від піку" index={2} className="lg:col-span-8" bodyClass="px-3 pb-3" summary={fmt.pct(result.stats.max_drawdown_pct, 1)}>
          <DrawdownChart result={result} />
        </Panel>
        <Panel id="series.monthly" title="Помісячно" index={3} className="lg:col-span-12" bodyClass="overflow-x-auto">
          <MonthlyTable monthly={result.monthly} />
        </Panel>
        {result.book_last_day && (
          <Panel id="series.book" title="Книга на останній день" index={4} className="lg:col-span-6" summary={bookLine(result.book_last_day)} tip={bookLine(result.book_last_day)}>
            <BookListing book={result.book_last_day} />
          </Panel>
        )}
        {next && nextBook && (
          <Panel id="series.next" title={`Книга на ${next.decided_at}`} index={5} className="lg:col-span-6" summary={bookLine(nextBook)} tip={bookLine(nextBook)}>
            <BookListing book={nextBook} />
          </Panel>
        )}
      </div>
    </>
  )
}

function Plain({ value }: { value: Record<string, unknown> }) {
  return (
    <Panel id="job.result" title="Результат" className="lg:col-span-12">
      <KV rows={Object.entries(value).map(([k, v]) => [k, typeof v === "object" ? <code className="font-mono text-[11.5px]">{JSON.stringify(v)}</code> : String(v)])} />
    </Panel>
  )
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
      <div className="mb-3">
        <Link to="/lab" className="inline-flex items-center gap-1 text-[12.5px] text-text-3 no-underline hover:text-text">
          <ArrowLeft size={13} aria-hidden /> Лабораторія
        </Link>
        <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1">
          <h1 className="text-[20px] font-semibold tracking-[-0.01em]">{j.title}</h1>
          <StatusMark status={j.status} />
          <span className="text-[12.5px] text-text-3">{params(j.params)}</span>
          {running && (
            <button type="button" className="btn btn-ghost ml-auto h-8 px-3 text-[12.5px]" onClick={() => cancel.mutate()} disabled={cancel.isPending}>
              <Square size={13} aria-hidden /> Скасувати
            </button>
          )}
        </div>
        <p className="mt-1 flex flex-wrap gap-x-3 text-[12px] text-text-3" role="status">
          <span>поставлено {when.dateTime(j.created_at)}</span>
          {j.finished_at && <span>завершено {when.dateTime(j.finished_at)}</span>}
          {running && j.progress && <span className="text-text">{j.progress}</span>}
        </p>
        {running && (
          <div className="mt-3 h-[3px] w-full overflow-hidden rounded-full bg-raised" aria-hidden>
            <div className="progress-run h-full w-1/3 rounded-full bg-brand" />
          </div>
        )}
      </div>
      <div>
        {j.status === "failed" && (
          <div className="panel p-4">
            <p className="font-semibold">⚠ Тест упав: {j.error}</p>
            {j.trace && (
              <details className="mt-2">
                <summary className="cursor-pointer text-[13px] text-text-2">Трасування</summary>
                <pre className="mt-2 overflow-x-auto rounded-lg bg-bg p-3 font-mono text-[11.5px] leading-relaxed">{j.trace}</pre>
              </details>
            )}
          </div>
        )}
        {j.status === "done" && result && (j.kind === "quant_period" || j.kind === "quant_forward") && <SeriesView result={result as unknown as PeriodResult} />}
        {j.status === "done" && result && j.kind === "quant_book" && <DayBook view={result as unknown as DayView} />}
        {j.status === "done" && result && j.kind === "quant_day" && <PairDayView doc={result as unknown as PairDay} />}
        {j.status === "done" && result && j.kind === "notice_replay" && <ReplayResult doc={result as unknown as ReplayDoc} />}
        {j.status === "done" && result && (j.kind === "quant_retrain" || j.kind === "quant_evidence") && <Plain value={result} />}
        {running && <p className="py-6 text-[13px] text-text-3">Результат з’явиться тут, щойно тест завершиться.</p>}
      </div>
    </Page>
  )
}
