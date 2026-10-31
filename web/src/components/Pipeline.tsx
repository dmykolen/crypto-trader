import clsx from "clsx"
import { useEffect, useRef, useState, type ReactNode } from "react"

import { fmt, when } from "../lib/format"
import type { ActivityEvent, BotState } from "../lib/types"
import { Signed } from "./Print"
import { Pulse } from "./ui"

export interface Lane {
  key: "quant" | "notice"
  source: string
  bot?: BotState
  account: string
  last?: ActivityEvent
}

const hhmm = new Intl.DateTimeFormat("uk-UA", { hour: "2-digit", minute: "2-digit", timeZone: "UTC" })

function lastText(e: ActivityEvent | undefined, now: number) {
  if (!e) return <span className="text-text-3">подій ще не було</span>
  const at = (
    <span className="text-text-3">
      {hhmm.format(new Date(e.at))} UTC · {when.ago(e.at, now)}
    </span>
  )
  if (e.kind === "rebalance")
    return (
      <>
        Ребаланс{" "}
        <Signed value={e.pnl} arrow={false}>
          {fmt.pnl(e.pnl)}
        </Signed>{" "}
        {at}
      </>
    )
  if (e.kind === "trade_open" || e.kind === "trade_close") return <>Угода {at}</>
  if (e.kind === "notice") return <>Анонс {at}</>
  return at
}

function Track({ fire, delay = 0 }: { fire: number; delay?: number }) {
  return (
    <span className="relative mx-2 h-px bg-line" aria-hidden>
      {fire > 0 && <span key={fire} className="packet" style={{ animationDelay: `${delay}ms` }} />}
    </span>
  )
}

function Node({ children, live, className }: { children: ReactNode; live?: boolean; className?: string }) {
  return <span className={clsx("flex h-8 min-w-0 items-center gap-2 rounded-md border px-2.5 text-[12px]", live ? "border-line-strong bg-raised" : "border-line", className)}>{children}</span>
}

function LaneRow({ lane, now }: { lane: Lane; now: number }) {
  const [fire, setFire] = useState(0)
  const seen = useRef<string | undefined>(lane.last?.at)
  useEffect(() => {
    if (lane.last?.at && lane.last.at !== seen.current) {
      seen.current = lane.last.at
      setFire((f) => f + 1)
    }
  }, [lane.last?.at])
  const running = Boolean(lane.bot?.running)
  return (
    <div className="grid grid-cols-[minmax(0,7rem)_minmax(1rem,1fr)_minmax(0,13rem)_minmax(1rem,1fr)_minmax(0,7rem)] items-center py-1 xl:grid-cols-[8.5rem_minmax(2rem,1fr)_15rem_minmax(2rem,1fr)_8rem_minmax(14rem,24rem)]">
      <Node>
        <span className="truncate text-text-2">{lane.source}</span>
      </Node>
      <Track fire={fire} />
      <Node live={running} className="justify-between">
        <span className="flex min-w-0 items-center gap-2">
          <Pulse state={running ? "on" : "off"} beat={lane.bot?.last_log_at} />
          <span className="truncate font-semibold">{lane.bot?.name ?? lane.key}</span>
        </span>
        <span className="display hidden flex-none text-[11px] text-text-3 sm:inline">{running ? when.duration(lane.bot?.uptime_s) : "стоп"}</span>
      </Node>
      <Track fire={fire} delay={700} />
      <Node className="justify-end">
        <span className="display truncate font-medium text-text">{lane.account}</span>
      </Node>
      <span className="hidden min-w-0 truncate pl-4 text-[12px] text-text-2 xl:block">{lastText(lane.last, now)}</span>
    </div>
  )
}

export const PIPELINE_TIP = "Дані з бірж ідуть до бота, бот торгує на свій рахунок. Коли бот щось робить, лінією пробігає світна точка; крапка біля бота блимає, коли він пише в журнал роботи."

export function Pipeline({ lanes, now }: { lanes: Lane[]; now: number }) {
  return (
    <div className="px-3.5 pb-2.5">
      {lanes.map((lane) => (
        <LaneRow key={lane.key} lane={lane} now={now} />
      ))}
    </div>
  )
}
