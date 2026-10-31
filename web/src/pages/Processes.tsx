import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import clsx from "clsx"
import { Bell, BellOff, Play, RotateCw, ScrollText } from "lucide-react"
import { useState } from "react"

import { LiveArm } from "../components/LiveArm"
import { LogView } from "../components/LogView"
import { Signed } from "../components/Print"
import { ConfirmButton, Dock, ModeChip, Panel, Pulse, Skeleton, Tip } from "../components/ui"
import { api } from "../lib/api"
import { setAlerts, useAlertsEnabled } from "../lib/alerts"
import { fmt, when } from "../lib/format"
import { useNow, useOverview } from "../lib/hooks"
import type { BotKey, DiskInfo, ErrorSummary, ProcessRow, ScheduleItem } from "../lib/types"
import { countdown } from "../components/Shell"
import { Page } from "./Overview"

const PANELS = [
  { id: "processes.list", title: "Процеси" },
  { id: "processes.schedule", title: "Розклад" },
  { id: "processes.log", title: "Лог наживо" },
  { id: "processes.errors", title: "Помилки за добу" },
  { id: "processes.autostart", title: "Автозапуск" },
  { id: "processes.disk", title: "Диск" },
]

const FOLDERS: Record<string, string> = {
  quotes_cache: "Котирування бота (кеш)",
  quant: "Дані Кванта",
  klines: "Свічки, архів",
  ticks: "Тики, архів",
  funding: "Фандінг, архів",
  universe: "Ринок, архів",
  pre_period: "Дані 2021–2023",
  reports: "Звіти",
  logs: "Логи",
  jobs: "Тести лабораторії",
  journal: "Журнал угод",
}

const SCHEDULE: Record<ScheduleItem["key"], { name: string; tip: string }> = {
  rebalance: { name: "Ребаланс Кванта", tip: "Щодня о 00:15 UTC (02:15 за Києвом). Якщо не вдався, бот повторює спробу кожні 15 хвилин." },
  limit_test: { name: "Тест лімітних ордерів", tip: "Після кожного ребалансу 30 хвилин перевіряє, чи дешевші були б лімітні ордери. Справжніх ордерів не ставить." },
  retrain: { name: "Перенавчання моделей", tip: "Раз на квартал, вручну: тест «Перенавчання» в Лабораторії. Нові моделі діють з наступного ребалансу." },
}

const SOURCES: Record<ErrorSummary["source"], string> = { serve: "Сервер", quant: "Квант", notice: "Анонси" }

function name(row: ProcessRow, bots: Record<string, string>): string {
  if (row.kind === "server") return row.key === "server" ? `Сервер пульта :${row.port}` : `Сервер :${row.port}`
  if (row.kind === "bot") return bots[row.key] ?? row.key
  if (row.kind === "job") return row.title ?? "Тест"
  return `trader ${row.command ?? ""}`.trim()
}

function Load({ row }: { row: ProcessRow }) {
  if (!row.running) return <span className="text-text-3">—</span>
  return (
    <span className="num text-text-2">
      {row.cpu == null ? "—" : `${fmt.ratio(row.cpu, 0)} %`} · {row.memory_mb == null ? "—" : `${fmt.int(row.memory_mb)} МБ`}
    </span>
  )
}

function useRestartServer() {
  const client = useQueryClient()
  const [phase, setPhase] = useState<"idle" | "restarting" | "back">("idle")
  const mutation = useMutation({
    mutationFn: api.restartServer,
    onSuccess: async () => {
      setPhase("restarting")
      const started = Date.now()
      let down = false
      while (Date.now() - started < 45_000) {
        await new Promise((r) => setTimeout(r, 1000))
        const ok = await fetch("/health")
          .then((r) => r.ok)
          .catch(() => false)
        if (!ok) down = true
        if (ok && (down || Date.now() - started > 6000)) break
      }
      setPhase("back")
      await client.invalidateQueries()
      setTimeout(() => setPhase("idle"), 2500)
    },
  })
  return { mutation, phase }
}

function ProcessList({ rows, onLog }: { rows: ProcessRow[]; onLog: (source: string) => void }) {
  const client = useQueryClient()
  const overview = useOverview()
  const bots = Object.fromEntries((overview.data?.bots ?? []).map((b) => [b.key, b.name]))
  const refresh = () => void client.invalidateQueries()
  const stop = useMutation({ mutationFn: api.stopProcess, onSettled: refresh })
  const start = useMutation({ mutationFn: (bot: BotKey) => api.startBot(bot, "paper"), onSettled: refresh })
  const restart = useMutation({ mutationFn: api.restartBot, onSettled: refresh })
  const live = useMutation({
    mutationFn: async (v: { bot: BotKey; phrase: string; running: boolean }) => {
      if (v.running) await api.stopBot(v.bot)
      return api.startBot(v.bot, "live", v.phrase)
    },
    onSettled: refresh,
    onSuccess: () => setArming(null),
  })
  const [arming, setArming] = useState<BotKey | null>(null)
  const server = useRestartServer()
  const system = overview.data?.system
  const armed = overview.data?.bots.find((b) => b.key === arming)
  const error = [stop.error, start.error, restart.error, server.mutation.error].find(Boolean) as Error | undefined
  return (
    <div className="@container">
      {server.phase !== "idle" && (
        <p className="border-b border-line px-3.5 py-2 text-[12.5px] text-text-2" role="status">
          {server.phase === "restarting" ? "Перезапускаю сервер пульта… сторінка оновиться сама." : "Сервер знову на звʼязку."}
        </p>
      )}
      {error && (
        <p className="border-b border-line px-3.5 py-2 text-[12.5px] font-semibold" role="alert">
          ⚠ {error.message}
        </p>
      )}
      <ul className="divide-y divide-line @min-[720px]:grid @min-[720px]:grid-cols-[fit-content(20rem)_auto_auto_minmax(0,1fr)] @min-[720px]:gap-x-4">
        {rows.map((row) => (
          <li key={row.key} className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-1.5 px-3.5 py-2.5 @min-[720px]:col-span-4 @min-[720px]:grid-cols-subgrid">
            <span className="col-span-2 flex min-w-0 items-center gap-2.5 @min-[720px]:col-span-1" title={row.pid ? `PID ${row.pid}` : undefined}>
              <Pulse state={row.running ? "on" : "off"} beat={row.last_log_at} />
              <span className="truncate text-[13px] font-medium">{name(row, bots)}</span>
              {row.kind === "bot" && <ModeChip live={row.running && row.mode === "live"} />}
              {row.kind === "job" && row.progress && <span className="hidden truncate text-[12px] text-text-3 lg:inline">{row.progress}</span>}
            </span>
            <span className="display text-[12px] text-text-3">
              {row.running ? `працює ${when.duration(row.started_at ? (Date.now() - Date.parse(row.started_at)) / 1000 : null)}` : row.last_stop ? `зупинений ${when.ago(row.last_stop)}` : "зупинений"}
            </span>
            <span className="text-right text-[12px] @min-[720px]:text-left" title="Процесор (100 % — одне ядро) · пам'ять">
              <Load row={row} />
            </span>
            <span className="col-span-2 flex flex-wrap gap-1.5 @min-[720px]:col-span-1 @min-[720px]:justify-end">
              {row.log && (
                <button type="button" className="btn btn-quiet h-7 px-2 text-[12px]" onClick={() => onLog(row.log as string)} title="Показати лог">
                  <ScrollText size={13} aria-hidden /> Лог
                </button>
              )}
              {row.key === "server" && (
                <ConfirmButton confirm="Так, перезапустити" onConfirm={() => server.mutation.mutate()} disabled={server.phase !== "idle"}>
                  <RotateCw size={13} aria-hidden /> Перезапустити
                </ConfirmButton>
              )}
              {row.kind === "bot" &&
                (row.running ? (
                  <>
                    {row.mode !== "live" && (
                      <ConfirmButton confirm="Так, перезапустити" onConfirm={() => restart.mutate(row.key as BotKey)}>
                        <RotateCw size={13} aria-hidden /> Перезапустити
                      </ConfirmButton>
                    )}
                    <ConfirmButton confirm="Так, зупинити" onConfirm={() => stop.mutate(row.key)}>
                      Зупинити
                    </ConfirmButton>
                  </>
                ) : (
                  <button type="button" className="btn h-7 px-2.5 text-[12px]" onClick={() => start.mutate(row.key as BotKey)} disabled={start.isPending}>
                    <Play size={13} aria-hidden /> Запустити
                  </button>
                ))}
              {row.kind === "bot" && !(row.running && row.mode === "live") && (
                <button
                  type="button"
                  className="btn btn-live h-7 px-2.5 text-[12px]"
                  disabled={!system?.live_ready}
                  title={system?.live_ready ? "Перевести бота на реальні гроші" : "Ключі Binance API не налаштовані"}
                  onClick={() => setArming(row.key as BotKey)}
                >
                  Реальні гроші…
                </button>
              )}
              {row.kind === "job" && (
                <ConfirmButton confirm="Так, скасувати" onConfirm={() => stop.mutate(row.key)}>
                  Скасувати
                </ConfirmButton>
              )}
              {(row.kind === "cli" || (row.kind === "server" && row.key !== "server")) && (
                <ConfirmButton confirm="Так, зупинити" onConfirm={() => stop.mutate(row.key)}>
                  Зупинити
                </ConfirmButton>
              )}
            </span>
          </li>
        ))}
      </ul>
      {armed && system && (
        <LiveArm bot={armed} system={system} busy={live.isPending} error={live.error ? (live.error as Error).message : null} onConfirm={(phrase) => live.mutate({ bot: armed.key, phrase, running: armed.running })} onClose={() => setArming(null)} />
      )}
    </div>
  )
}

function Schedule({ items, now }: { items: ScheduleItem[]; now: number }) {
  return (
    <ul className="divide-y divide-line">
      {items.map((item) => {
        const soon = Date.parse(item.next) - now < 86_400_000
        return (
          <li key={item.key} className="flex items-center gap-3 px-3.5 py-2.5">
            <span className="min-w-0 flex-1">
              <span className="flex items-center gap-1.5 text-[13px] font-medium">
                {SCHEDULE[item.key].name}
                <Tip align="start">{SCHEDULE[item.key].tip}</Tip>
              </span>
              <span className="block text-[12px] text-text-3">
                {item.last ? `востаннє ${when.dateTime(item.last)}` : "ще не було"}
                {item.last_pnl != null && (
                  <>
                    {" · "}
                    <Signed value={item.last_pnl} arrow={false}>
                      {fmt.pnl(item.last_pnl)}
                    </Signed>
                  </>
                )}
              </span>
            </span>
            <span className="display text-right text-[13px] text-text">{soon ? countdown(item.next, now) : when.day(item.next)}</span>
          </li>
        )
      })}
    </ul>
  )
}

function Errors({ errors, onOpen }: { errors: ErrorSummary[]; onOpen: (source: string) => void }) {
  const total = errors.reduce((s, e) => s + e.count, 0)
  if (!total) return <p className="px-3.5 py-4 text-[13px] text-text-2">За добу помилок не було.</p>
  return (
    <ul className="divide-y divide-line">
      {errors
        .filter((e) => e.count)
        .map((e) => (
          <li key={e.source} className="px-3.5 py-2.5">
            <div className="flex items-center gap-2">
              <span className="text-[13px] font-semibold">⚠ {SOURCES[e.source]}</span>
              <span className="num text-[12px] text-text-2">{e.count}</span>
              <button type="button" className="btn btn-quiet ml-auto h-7 px-2 text-[12px]" onClick={() => onOpen(e.source)}>
                <ScrollText size={13} aria-hidden /> Відкрити
              </button>
            </div>
            {e.recent.map((r) => (
              <p key={r.at + r.line} className="mt-1 truncate text-[12px] text-text-3" title={`${r.line}\n${r.detail}`}>
                <span className="display">{when.time(r.at)}</span> · {r.detail || r.line}
              </p>
            ))}
          </li>
        ))}
    </ul>
  )
}

function Autostart() {
  const client = useQueryClient()
  const status = useQuery({ queryKey: ["autostart"], queryFn: api.autostart, refetchInterval: 15_000 })
  const toggle = useMutation({ mutationFn: api.setAutostart, onSettled: () => setTimeout(() => void client.invalidateQueries(), 4000) })
  const on = Boolean(status.data?.enabled)
  return (
    <div className="flex items-center gap-3 px-3.5 py-3">
      <span className="min-w-0 flex-1">
        <span className="block text-[13px] font-medium">{on ? "Увімкнено" : "Вимкнено"}</span>
        <span className="block text-[12px] text-text-3">{on ? "пульт і боти стартують після входу в macOS" : "після перезавантаження все треба запускати вручну"}</span>
      </span>
      <ConfirmButton confirm={on ? "Так, вимкнути" : "Так, увімкнути"} onConfirm={() => toggle.mutate(!on)} disabled={!status.data || toggle.isPending}>
        {on ? "Вимкнути" : "Увімкнути"}
      </ConfirmButton>
      {toggle.error && <span className="text-[12px] font-semibold">⚠ {(toggle.error as Error).message}</span>}
    </div>
  )
}

function Disk({ disk }: { disk: DiskInfo }) {
  const client = useQueryClient()
  const clean = useMutation({ mutationFn: api.cleanDisk, onSettled: () => void client.invalidateQueries({ queryKey: ["disk"] }) })
  const max = Math.max(1, ...disk.folders.map((f) => f.bytes))
  const share = disk.used / disk.total
  return (
    <div className="px-3.5 py-3">
      <div className="flex items-baseline justify-between text-[12.5px]">
        <span>
          вільно <b className="display text-[15px]">{fmt.bytes(disk.free)}</b>
        </span>
        <span className="text-text-3">
          {fmt.bytes(disk.used)} з {fmt.bytes(disk.total)}
        </span>
      </div>
      <div className="mt-2 h-2 overflow-hidden rounded-full bg-raised">
        <div className={clsx("grow-x h-full rounded-full", share > 0.9 ? "bg-text" : "bg-text-3")} style={{ width: `${100 * share}%` }} />
      </div>
      {share > 0.9 && <p className="mt-2 text-[12px] font-semibold">⚠ Диск майже повний: ребаланс може не записатися.</p>}
      <ul className="mt-3 space-y-1.5">
        {[...disk.folders]
          .filter((f) => f.bytes)
          .sort((a, b) => b.bytes - a.bytes)
          .map((f) => (
            <li key={f.key} className="grid grid-cols-[1fr_4.5rem] items-center gap-3 text-[12px]">
              <span className="min-w-0">
                <span className="block truncate text-text-2">{FOLDERS[f.key] ?? f.key}</span>
                <span className="mt-1 block h-1 rounded-full bg-raised">
                  <span className="block h-full rounded-full bg-text-3" style={{ width: `${(100 * f.bytes) / max}%` }} />
                </span>
              </span>
              <span className="num text-right text-text-2">{fmt.bytes(f.bytes)}</span>
            </li>
          ))}
      </ul>
      <div className="mt-3 flex items-center gap-3 border-t border-line pt-3 text-[12px]">
        <span className="min-w-0 flex-1 text-text-2">
          Котирування, старші за {disk.stale.keep_days} днів: {disk.stale.files ? `${disk.stale.files} файлів, ${fmt.bytes(disk.stale.bytes)}` : "немає"}
        </span>
        <ConfirmButton confirm="Так, видалити" onConfirm={() => clean.mutate()} disabled={!disk.stale.files || clean.isPending}>
          Очистити
        </ConfirmButton>
      </div>
      {clean.data && <p className="mt-2 text-[12px] text-text-2">Видалено {clean.data.files} файлів, звільнено {fmt.bytes(clean.data.freed)}.</p>}
    </div>
  )
}

export function Processes() {
  const now = useNow(1000)
  const list = useQuery({ queryKey: ["processes"], queryFn: api.processes, refetchInterval: 2000 })
  const schedule = useQuery({ queryKey: ["schedule"], queryFn: api.schedule, refetchInterval: 30_000 })
  const disk = useQuery({ queryKey: ["disk"], queryFn: api.disk, refetchInterval: 60_000 })
  const [source, setSource] = useState<string>("quant")
  const [errorsOnly, setErrorsOnly] = useState(false)
  const alerts = useAlertsEnabled()
  const sources = [
    { key: "quant", label: "Квант" },
    { key: "notice", label: "Анонси" },
    { key: "serve", label: "Сервер" },
    ...(list.data?.processes ?? []).filter((p) => p.kind === "job").map((p) => ({ key: p.log as string, label: p.title ?? "Тест" })),
  ]
  const openLog = (key: string, errors = false) => {
    setSource(key)
    setErrorsOnly(errors)
  }
  const rows = list.data?.processes ?? []
  const errorTotal = (schedule.data?.errors ?? []).reduce((s, e) => s + e.count, 0)
  return (
    <Page>
      <div className="mb-3 flex items-center justify-between gap-3">
        <h1 className="text-[20px] font-semibold tracking-[-0.01em]">Процеси</h1>
        <button
          type="button"
          className={clsx("btn h-8 px-3 text-[12.5px]", !alerts && "btn-ghost")}
          aria-pressed={alerts}
          onClick={() => void setAlerts(!alerts)}
          title="Сповіщення macOS: бот зупинився, ребаланс пройшов або не пройшов, тест завершився, нова помилка"
        >
          {alerts ? <Bell size={14} aria-hidden /> : <BellOff size={14} aria-hidden />}
          {alerts ? "Сповіщення увімкнені" : "Увімкнути сповіщення"}
        </button>
      </div>
      <Dock panels={PANELS} />
      <div className="grid items-start gap-3 lg:grid-cols-12">
        <Panel id="processes.list" title="Процеси" index={0} className="lg:col-span-8" summary={`працює ${rows.filter((r) => r.running).length} з ${rows.length}`}>
          {list.isLoading ? (
            <div className="space-y-2 p-3.5">
              <Skeleton className="h-6" />
              <Skeleton className="h-6" />
              <Skeleton className="h-6" />
            </div>
          ) : (
            <ProcessList rows={rows} onLog={(key) => openLog(key)} />
          )}
        </Panel>
        <Panel id="processes.schedule" title="Розклад" index={1} className="lg:col-span-4" summary={schedule.data ? `ребаланс за ${countdown(schedule.data.items[0]?.next, now)}` : undefined}>
          {schedule.data ? <Schedule items={schedule.data.items} now={now} /> : <Skeleton className="m-3.5 h-20" />}
        </Panel>
        <Panel
          id="processes.log"
          title="Лог наживо"
          index={2}
          className="h-[520px] lg:col-span-8 lg:row-span-3 lg:h-0 lg:min-h-full"
          wideClass="h-[600px] lg:col-span-12"
          foldClass="h-auto! lg:min-h-0! lg:row-span-1!"
          bodyClass="min-h-0 flex flex-col"
          side={
            <span className="ml-1 flex min-w-0 gap-1 overflow-x-auto [scrollbar-width:none]" role="tablist" aria-label="Чий лог">
              {sources.map((s) => (
                <button
                  key={s.key}
                  type="button"
                  role="tab"
                  aria-selected={source === s.key}
                  onClick={() => openLog(s.key)}
                  className={clsx("h-7 flex-none rounded-md px-2.5 text-[12px] whitespace-nowrap transition-colors", source === s.key ? "bg-press text-text" : "text-text-3 hover:bg-raised hover:text-text")}
                >
                  {s.label}
                </button>
              ))}
            </span>
          }
        >
          <LogView source={source} errorsOnly={errorsOnly} setErrorsOnly={setErrorsOnly} />
        </Panel>
        <Panel id="processes.errors" title="Помилки за добу" index={3} className="lg:col-span-4" summary={errorTotal ? `⚠ ${errorTotal}` : "немає"}>
          {schedule.data ? <Errors errors={schedule.data.errors} onOpen={(s) => openLog(s, true)} /> : <Skeleton className="m-3.5 h-16" />}
        </Panel>
        <Panel
          id="processes.autostart"
          title="Автозапуск"
          index={4}
          className="lg:col-span-4"
          tip="Запис в автозапуску macOS: після входу в систему стартує пульт, а за ним боти, що працювали до перезавантаження, лише на віртуальних грошах. Пульт також піднімається сам, якщо впаде. Під час увімкнення пульт перезапуститься."
        >
          <Autostart />
        </Panel>
        <Panel id="processes.disk" title="Диск" index={5} className="lg:col-span-4" summary={disk.data ? `вільно ${fmt.bytes(disk.data.free)}` : undefined}>
          {disk.data ? <Disk disk={disk.data} /> : <Skeleton className="m-3.5 h-24" />}
        </Panel>
      </div>
    </Page>
  )
}
