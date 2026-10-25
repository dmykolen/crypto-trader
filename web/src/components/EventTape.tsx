import clsx from "clsx"
import { Link } from "react-router-dom"

import { describeEvent, fmt, tone, when } from "../lib/format"
import { useFreshKeys } from "../lib/hooks"
import { BOT_HUE } from "../lib/theme"
import type { ActivityEvent } from "../lib/types"
import { Signed } from "./Print"

const BOT_LABEL = { notice: "Анонси", quant: "Квант", lab: "Лабораторія" } as const

function eventKey(e: ActivityEvent): string {
  return `${e.at}|${e.kind}|${"title" in e ? e.title : ""}|${e.kind === "job" ? e.status : ""}`
}

/** The day's tape: newest first, each line tagged by its bot's hue; money moves are printed as signed figures, new lines arrive in wet ink. */
export function EventTape({ events, limit = 24 }: { events: ActivityEvent[]; limit?: number }) {
  const rows = events.slice(0, limit)
  const keys = rows.map(eventKey)
  const fresh = useFreshKeys(keys)
  if (!rows.length) return <p className="py-4 text-ink-3">Подій поки немає.</p>
  return (
    <ol className="divide-y divide-rule/70">
      {rows.map((e, i) => {
        const key = keys[i] as string
        const line = describeEvent(e)
        const body = (
          <>
            <span className="num flex items-baseline justify-between gap-2 text-[11.5px] text-ink-3">
              <span className="flex items-center gap-1.5">
                <span aria-hidden className="inline-block h-2 w-2" style={{ background: BOT_HUE[e.bot] }} />
                {BOT_LABEL[e.bot]}
              </span>
              <time dateTime={e.at}>{when.dateTime(e.at)}</time>
            </span>
            <span title={line.title} className={clsx("mt-0.5 line-clamp-3 text-[13.5px] leading-snug [overflow-wrap:break-word]", line.quiet && "text-ink-2")}>
              {line.title}
            </span>
            <span className="flex items-baseline justify-between gap-3">
              <span className={clsx("min-w-0 text-[12px] leading-snug", line.alert ? "text-loss" : "text-ink-3")}>{line.detail}</span>
              {line.amount != null && tone(line.amount) !== "flat" && (
                <Signed value={line.amount} arrow={false} className="shrink-0 text-[13px] font-semibold">
                  {fmt.pnl(line.amount)}
                </Signed>
              )}
            </span>
          </>
        )
        return (
          <li key={key} className={clsx("py-2", fresh.has(key) && "wet press-in")} style={{ ["--wet" as string]: BOT_HUE[e.bot] }}>
            {e.kind === "job" ? (
              <Link to={`/lab/${e.job}`} className="block no-underline hover:bg-shade">
                {body}
              </Link>
            ) : (
              body
            )}
          </li>
        )
      })}
    </ol>
  )
}
