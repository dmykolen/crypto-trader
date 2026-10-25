import clsx from "clsx"
import { Play, ShieldAlert, Square } from "lucide-react"
import { useState, type ReactNode } from "react"

import { ApiError } from "../lib/api"
import { when } from "../lib/format"
import { useBotControl, useWet } from "../lib/hooks"
import { BOT_HUE } from "../lib/theme"
import type { BotState, SystemInfo } from "../lib/types"
import { LiveArm } from "./LiveArm"
import { Dot } from "./Print"

interface Props {
  bot: BotState
  system: SystemInfo
  dek: ReactNode
  figures: ReactNode
  chart?: ReactNode
  last?: ReactNode
  compact?: boolean
  heading?: boolean
}

/** One bot reported like a listed security: name and dek, its state line, the figures, and the desk controls. */
export function BotColumn({ bot, system, dek, figures, chart, last, compact = false, heading = true }: Props) {
  const { start, stop } = useBotControl()
  const [arming, setArming] = useState(false)
  const stamp = useWet(`${bot.running}-${bot.mode}`)
  const busy = start.isPending || stop.isPending
  const error = (start.error ?? stop.error) as ApiError | null
  const live = bot.running && bot.mode === "live"
  const hue = BOT_HUE[bot.key]

  async function goLive(phrase: string) {
    if (bot.running) await stop.mutateAsync(bot.key)
    await start.mutateAsync({ bot: bot.key, mode: "live", confirm: phrase })
    setArming(false)
  }

  return (
    <section aria-labelledby={`bot-${bot.key}`} className={clsx("flex min-w-0 flex-col", live && "live-hatch -mx-2 px-2")}>
      <h2 id={`bot-${bot.key}`} className={clsx("head text-[2rem] font-extrabold", !heading && "sr-only")} style={{ color: hue }}>
        {bot.name}
        <span className="ml-2 align-middle text-[0.95rem] font-bold text-ink-3">бот №{bot.number}</span>
      </h2>
      {!compact && <p className="mt-1 text-[13px] text-ink-2 md:min-h-[3lh]">{dek}</p>}
      <p key={stamp} className={clsx("num mt-2 flex flex-wrap items-center gap-x-2 text-[13px]", stamp && "wet")} style={{ ["--wet" as string]: hue }} role="status">
        <Dot on={bot.running} live={live} />
        <b className={clsx(live && "text-live")}>{bot.running ? (live ? "Працює з реальними грошима" : "Працює на папері") : "Зупинено"}</b>
        {bot.running && (
          <span className="text-ink-2">
            · {when.duration(bot.uptime_s)} · PID {bot.pid}
          </span>
        )}
        {!bot.running && bot.last_stop && <span className="text-ink-2">· з {when.dateTime(bot.last_stop)}</span>}
      </p>
      <div className="mt-3">{figures}</div>
      {chart && <div className="mt-3">{chart}</div>}
      {last && <p className="mt-2 line-clamp-2 text-[12.5px] text-ink-2 md:min-h-[2lh]">{last}</p>}
      <div className="mt-auto flex flex-wrap gap-3 pt-4">
        {bot.running ? (
          <button type="button" className="btn btn-ghost" disabled={busy} onClick={() => stop.mutate(bot.key)}>
            <Square size={11} fill="currentColor" aria-hidden /> {stop.isPending ? "Зупиняю…" : "Зупинити"}
          </button>
        ) : (
          <button type="button" className="btn" disabled={busy} onClick={() => start.mutate({ bot: bot.key, mode: "paper" })}>
            <Play size={13} aria-hidden /> {start.isPending ? "Запускаю…" : "Запустити на папері"}
          </button>
        )}
        {!live && (
          <button type="button" className="btn btn-live ml-auto" disabled={busy} onClick={() => setArming(true)} title={system.live_ready ? undefined : "Потрібні ключі Binance API у .env"}>
            <ShieldAlert size={13} aria-hidden /> Увімкнути реальні гроші
          </button>
        )}
      </div>
      {error && !arming && <p className="mt-2 text-[12.5px] text-loss">{error.message}</p>}
      {arming && <LiveArm bot={bot} system={system} busy={busy} error={error?.message ?? null} onConfirm={(p) => void goLive(p).catch(() => undefined)} onClose={() => setArming(false)} />}
    </section>
  )
}
