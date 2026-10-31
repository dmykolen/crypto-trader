import clsx from "clsx"
import { ChartCandlestick, Cpu, FlaskConical, LayoutGrid, Megaphone, Moon, PanelLeftClose, PanelLeftOpen, PanelTopClose, PanelTopOpen, Search, ShieldCheck, Sun, TriangleAlert } from "lucide-react"
import { Link, NavLink } from "react-router-dom"

import { when } from "../lib/format"
import { useNow, useOverview } from "../lib/hooks"
import { setChrome, useChrome } from "../lib/layout"
import { setEdition, useEdition } from "../lib/theme"
import type { BotState } from "../lib/types"
import { ModeChip, Pulse, Tip } from "./ui"

const kyiv = new Intl.DateTimeFormat("uk-UA", { hour: "2-digit", minute: "2-digit", second: "2-digit", timeZone: "Europe/Kyiv" })
const utc = new Intl.DateTimeFormat("uk-UA", { hour: "2-digit", minute: "2-digit", second: "2-digit", timeZone: "UTC" })

export const NAV = [
  { to: "/", label: "Огляд", icon: LayoutGrid, end: true },
  { to: "/bots/quant", label: "Квант", icon: ChartCandlestick },
  { to: "/bots/notice", label: "Анонси", icon: Megaphone },
  { to: "/lab", label: "Лабораторія", short: "Лаб", icon: FlaskConical },
  { to: "/evidence", label: "Докази", icon: ShieldCheck },
  { to: "/processes", label: "Процеси", icon: Cpu },
]

const two = (n: number) => String(n).padStart(2, "0")

export function countdown(iso: string | undefined, now: number): string {
  if (!iso) return "—"
  const s = Math.max(0, Math.round((new Date(iso).getTime() - now) / 1000))
  return `${two(Math.floor(s / 3600))}:${two(Math.floor((s % 3600) / 60))}:${two(s % 60)}`
}

export function Logo({ size = 26 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden className="flex-none">
      <rect width="32" height="32" rx="7" fill="var(--raised)" stroke="var(--line-strong)" />
      <path d="M5 18h6l3-8 4 13 3-7h6" stroke="var(--brand)" strokeWidth="2.6" fill="none" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  )
}

function BotLight({ bot, compact }: { bot: BotState; compact: boolean }) {
  const live = bot.running && bot.mode === "live"
  return (
    <Link to="/processes" className="group flex items-center gap-2 rounded-md px-1.5 py-1 no-underline transition-colors hover:bg-raised" title={bot.running ? `${bot.name}: працює ${when.duration(bot.uptime_s)}` : `${bot.name}: зупинений`}>
      <Pulse state={bot.running ? "on" : "off"} beat={bot.last_log_at} label={bot.running ? "працює" : "зупинений"} />
      {!compact && <span className={clsx("text-[12.5px] font-semibold", bot.running ? "text-text" : "text-text-3")}>{bot.name}</span>}
      {!compact && bot.running && <span className="display hidden text-[11.5px] text-text-3 2xl:inline">{when.duration(bot.uptime_s)}</span>}
      {live && <ModeChip live />}
    </Link>
  )
}

export function TopBar({ onCommand }: { onCommand: () => void }) {
  const now = useNow(1000)
  const edition = useEdition()
  const { data, isError } = useOverview()
  const { compactBar } = useChrome()
  const bots = data?.bots ?? []
  return (
    <header className={clsx("sticky top-0 z-40 flex items-center gap-2 border-b border-line bg-bg/85 px-3 backdrop-blur-md transition-[height] duration-200 md:gap-4 md:px-4", compactBar ? "h-10" : "h-12", isError && "offline-hatch")}>
      <Link to="/" className="flex items-center gap-2.5 no-underline" aria-label="Крипто-Трейдер, огляд">
        <Logo />
        {!compactBar && <span className="hidden text-[13.5px] font-semibold tracking-[-0.01em] lg:inline">Крипто-Трейдер</span>}
      </Link>
      <span className="hidden h-5 w-px bg-line sm:block" aria-hidden />
      <nav aria-label="Стан процесів" className="flex min-w-0 items-center gap-0.5 md:gap-1.5">
        <Link to="/processes" className="flex items-center gap-2 rounded-md px-1.5 py-1 no-underline transition-colors hover:bg-raised" title={isError ? "Сервер пульта не відповідає" : "Сервер пульта на звʼязку"}>
          <Pulse state={isError ? "down" : data ? "on" : "off"} label={isError ? "немає звʼязку" : "на звʼязку"} />
          {!compactBar && <span className="text-[12.5px] font-semibold">Сервер</span>}
        </Link>
        {bots.map((b) => (
          <BotLight key={b.key} bot={b} compact={compactBar} />
        ))}
      </nav>
      {data && (
        <div className="hidden items-center gap-2 border-l border-line pl-4 md:flex">
          {!compactBar && <span className="label">До ребалансу</span>}
          <span className="display text-[13px] font-medium text-text">{countdown(data.system.next_quant_rebalance, now)}</span>
          {!compactBar && <Tip side="bottom">Квант перебудовує портфель щодня о 00:15 UTC (02:15 за Києвом).</Tip>}
        </div>
      )}
      <div className="flex-1" />
      {isError && (
        <span className="flex items-center gap-1.5 text-[12px] font-semibold text-text" role="status">
          <TriangleAlert size={14} aria-hidden />
          <span className="hidden sm:inline">Немає звʼязку з сервером · пробую знову</span>
        </span>
      )}
      <button type="button" onClick={onCommand} className="hidden h-8 items-center gap-2 rounded-md border border-line px-2.5 text-[12px] text-text-2 transition-colors hover:border-line-strong hover:bg-raised hover:text-text md:flex">
        <Search size={13} aria-hidden />
        Дії
        <kbd className="display rounded border border-line px-1 text-[10.5px] text-text-3">⌘K</kbd>
      </button>
      <div className={clsx("display hidden gap-3 text-[12px] text-text-3", !compactBar && "xl:flex")} aria-label="Час">
        <span>
          Київ <span className="text-text">{kyiv.format(now)}</span>
        </span>
        <span>
          UTC <span className="text-text">{utc.format(now)}</span>
        </span>
      </div>
      <button
        type="button"
        onClick={() => setEdition(edition === "night" ? "day" : "night")}
        className="btn btn-quiet h-8 w-8 px-0"
        aria-label={edition === "night" ? "Увімкнути світлу тему" : "Увімкнути темну тему"}
        title={edition === "night" ? "Світла тема" : "Темна тема"}
      >
        {edition === "night" ? <Sun size={15} aria-hidden /> : <Moon size={15} aria-hidden />}
      </button>
      <button
        type="button"
        onClick={() => setChrome({ compactBar: !compactBar })}
        className="btn btn-quiet hidden h-8 w-8 px-0 md:inline-flex"
        aria-label={compactBar ? "Розгорнути верхню смугу" : "Згорнути верхню смугу"}
        title={compactBar ? "Розгорнути смугу" : "Згорнути смугу"}
      >
        {compactBar ? <PanelTopOpen size={15} aria-hidden /> : <PanelTopClose size={15} aria-hidden />}
      </button>
    </header>
  )
}

export function Rail() {
  const { compactRail, compactBar } = useChrome()
  return (
    <nav
      aria-label="Розділи"
      className={clsx(
        "fixed inset-x-0 bottom-0 z-40 flex h-14 border-t border-line bg-bg/90 backdrop-blur-md md:sticky md:flex-none md:flex-col md:self-start md:gap-1 md:border-t-0 md:border-r md:bg-bg md:py-2 md:backdrop-blur-none",
        compactBar ? "md:top-10 md:h-[calc(100vh-2.5rem)]" : "md:top-12 md:h-[calc(100vh-3rem)]",
        compactRail ? "md:w-[56px]" : "md:w-[76px]",
      )}
    >
      {NAV.map(({ to, label, short, icon: Icon, end }) => (
        <NavLink
          key={to}
          to={to}
          end={end}
          className={({ isActive }) =>
            clsx("group flex flex-1 flex-col items-center justify-center gap-1 text-[10px] font-medium no-underline transition-colors md:flex-none md:py-1.5", isActive ? "text-text" : "text-text-3 hover:text-text")
          }
        >
          {({ isActive }) => (
            <>
              <span className={clsx("flex h-8 w-11 items-center justify-center rounded-lg transition-colors", isActive ? "bg-press" : "group-hover:bg-raised")}>
                <Icon size={18} strokeWidth={isActive ? 2.1 : 1.8} aria-hidden />
              </span>
              <span className={clsx(compactRail && "md:sr-only")}>{short ?? label}</span>
            </>
          )}
        </NavLink>
      ))}
      <button
        type="button"
        onClick={() => setChrome({ compactRail: !compactRail })}
        className="mt-auto hidden h-9 items-center justify-center text-text-3 transition-colors hover:text-text md:flex"
        aria-label={compactRail ? "Показати підписи розділів" : "Сховати підписи розділів"}
        title={compactRail ? "Показати підписи" : "Сховати підписи"}
      >
        {compactRail ? <PanelLeftOpen size={16} aria-hidden /> : <PanelLeftClose size={16} aria-hidden />}
      </button>
    </nav>
  )
}
