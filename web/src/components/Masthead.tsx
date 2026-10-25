import clsx from "clsx"
import { Moon, Sun } from "lucide-react"
import { NavLink } from "react-router-dom"

import { when } from "../lib/format"
import { useNow, useOverview } from "../lib/hooks"
import { setEdition, useEdition } from "../lib/theme"

const SECTIONS = [
  { to: "/", label: "Огляд", end: true },
  { to: "/bots/notice", label: "Анонси" },
  { to: "/bots/quant", label: "Квант" },
  { to: "/lab", label: "Лабораторія" },
  { to: "/evidence", label: "Докази" },
  { to: "/system", label: "Система" },
]

const kyiv = new Intl.DateTimeFormat("uk-UA", { hour: "2-digit", minute: "2-digit", second: "2-digit", timeZone: "Europe/Kyiv" })
const utc = new Intl.DateTimeFormat("uk-UA", { hour: "2-digit", minute: "2-digit", second: "2-digit", timeZone: "UTC" })

export function Masthead() {
  const now = useNow(1000)
  const edition = useEdition()
  const { data, dataUpdatedAt, isError } = useOverview()
  const age = Math.max(0, Math.round((now - dataUpdatedAt) / 1000))
  const running = data?.bots.filter((b) => b.running) ?? []
  const live = running.some((b) => b.mode === "live")
  return (
    <header className="mx-auto w-full max-w-[1480px] px-5 pt-4 md:px-8">
      <div className="num flex flex-wrap items-center justify-between gap-x-6 gap-y-1 text-[12px] text-ink-2">
        <span className="first-letter:uppercase">{when.edition(new Date(now).toISOString())}</span>
        <span className="flex items-center gap-4">
          <span>
            Київ <b className="text-ink">{kyiv.format(now)}</b>
          </span>
          <span>
            UTC <b className="text-ink">{utc.format(now)}</b>
          </span>
          <span role="group" aria-label="Випуск" className="flex">
            {(["day", "night"] as const).map((e, i) => (
              <button key={e} type="button" aria-pressed={edition === e} onClick={() => setEdition(e)} className={clsx("btn h-6 px-2 text-[12px]", edition !== e && "btn-ghost border-rule font-normal text-ink-3", i && "-ml-px")}>
                {e === "day" ? <Sun size={12} aria-hidden /> : <Moon size={12} aria-hidden />}
                {e === "day" ? "Денний" : "Нічний"}
              </button>
            ))}
          </span>
        </span>
      </div>
      <div className="rule-double mt-2 flex flex-wrap items-baseline justify-between gap-x-8 gap-y-2 pt-3 pb-1">
        <NavLink to="/" className="head text-[2.9rem] font-black tracking-[-0.02em] no-underline md:text-[3.4rem]">
          Крипто-Трейдер
        </NavLink>
        <p className={clsx("num text-[13px]", live ? "live-hatch px-2 py-1 font-semibold text-live" : "text-ink-2")} role="status">
          {data
            ? running.length === 0
              ? "Усі боти зупинені"
              : `${running.length === 2 ? "Обидва боти працюють" : `Працює: ${running.map((b) => b.name).join(", ")}`} · ${live ? "РЕАЛЬНІ ГРОШІ" : "паперовий рахунок"}`
            : "Звʼязуюсь із сервером…"}
          {isError ? (
            <b className="font-semibold text-loss"> · немає звʼязку з сервером, дані {age} с тому</b>
          ) : (
            data && <span className={clsx(age > 20 ? "text-loss" : "text-ink-3")}> · оновлено {age < 3 ? "щойно" : `${age} с тому`}</span>
          )}
        </p>
      </div>
      <nav aria-label="Розділи" className="rule mt-2 flex flex-wrap gap-x-1 py-1.5 md:flex-nowrap">
        {SECTIONS.map((s) => (
          <NavLink
            key={s.to}
            to={s.to}
            end={s.end}
            className={({ isActive }) =>
              clsx("head px-2.5 py-1 text-[16px] font-bold whitespace-nowrap no-underline transition-colors", isActive ? "bg-ink text-paper" : "text-ink-2 hover:bg-shade hover:text-ink")
            }
          >
            {s.label}
          </NavLink>
        ))}
      </nav>
      <div className="rule-heavy mt-0" />
    </header>
  )
}
