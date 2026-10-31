import clsx from "clsx"
import { Link } from "react-router-dom"

import { describeEvent, fmt, tone } from "../lib/format"
import { useFreshKeys } from "../lib/hooks"
import type { ActivityEvent } from "../lib/types"
import { Signed } from "./Print"

const BOT = {
  quant: { mark: "К", name: "Квант", color: "var(--text-2)" },
  notice: { mark: "А", name: "Анонси", color: "var(--text-2)" },
  lab: { mark: "Л", name: "Лабораторія", color: "var(--text-2)" },
} as const

const time = new Intl.DateTimeFormat("uk-UA", { hour: "2-digit", minute: "2-digit", timeZone: "UTC" })
const day = new Intl.DateTimeFormat("uk-UA", { day: "numeric", month: "long", timeZone: "UTC" })

function dayLabel(iso: string): string {
  const d = new Date(iso)
  const today = new Date()
  const key = (x: Date) => x.toISOString().slice(0, 10)
  if (key(d) === key(today)) return "Сьогодні"
  if (key(d) === key(new Date(today.getTime() - 86_400_000))) return "Вчора"
  return day.format(d)
}

function eventKey(e: ActivityEvent): string {
  return `${e.at}|${e.kind}|${"title" in e ? e.title : ""}|${e.kind === "job" ? e.status : ""}`
}

export function Feed({ events, limit = 30 }: { events: ActivityEvent[]; limit?: number }) {
  const rows = events.slice(0, limit)
  const keys = rows.map(eventKey)
  const fresh = useFreshKeys(keys)
  if (!rows.length) return <p className="px-3.5 py-6 text-[13px] text-text-3">Подій ще не було.</p>
  return (
    <ol className="flex flex-col">
      {rows.map((e, i) => {
        const key = keys[i] as string
        const line = describeEvent(e)
        const bot = BOT[e.bot]
        const header = i === 0 || dayLabel(e.at) !== dayLabel((rows[i - 1] as ActivityEvent).at)
        const body = (
          <span className="grid grid-cols-[3rem_1.25rem_1fr_auto] items-baseline gap-x-2 px-3.5 py-2">
            <time dateTime={e.at} className="display text-[12px] text-text-3">
              {time.format(new Date(e.at))}
            </time>
            <span className="display flex h-5 w-5 items-center justify-center self-center rounded text-[10.5px] font-bold" style={{ color: bot.color, background: `color-mix(in oklab, ${bot.color} 14%, transparent)` }} title={bot.name}>
              {bot.mark}
            </span>
            <span className="min-w-0">
              <span className={clsx("block truncate text-[13px]", line.quiet ? "text-text-2" : "text-text")} title={line.title}>
                {line.title}
              </span>
              <span className={clsx("block truncate text-[11.5px]", line.alert ? "font-semibold text-text" : "text-text-3")}>
                {line.alert && "⚠ "}
                {line.detail}
              </span>
            </span>
            {line.amount != null && tone(line.amount) !== "flat" ? (
              <Signed value={line.amount} arrow={false} className="text-[12.5px] font-semibold">
                {fmt.pnl(line.amount)}
              </Signed>
            ) : (
              <span />
            )}
          </span>
        )
        return (
          <li key={key} className={clsx(fresh.has(key) && "wet press-in")}>
            {header && <div className="label sticky top-0 z-10 border-b border-line bg-panel px-3.5 py-1.5">{dayLabel(e.at)} · UTC</div>}
            {e.kind === "job" ? (
              <Link to={`/lab/${e.job}`} className="block no-underline transition-colors hover:bg-raised">
                {body}
              </Link>
            ) : (
              <div className="transition-colors hover:bg-raised">{body}</div>
            )}
          </li>
        )
      })}
    </ol>
  )
}
