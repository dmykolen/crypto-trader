import { useQuery } from "@tanstack/react-query"
import { useEffect, useRef, useSyncExternalStore } from "react"

import { api } from "./api"
import { fmt } from "./format"
import { useJobs, useOverview } from "./hooks"

const KEY = "alerts"
const listeners = new Set<() => void>()

function read(): boolean {
  try {
    return localStorage.getItem(KEY) === "1" && "Notification" in window && Notification.permission === "granted"
  } catch {
    return false
  }
}

export function useAlertsEnabled(): boolean {
  return useSyncExternalStore(
    (fn) => {
      listeners.add(fn)
      return () => listeners.delete(fn)
    },
    read,
    () => false,
  )
}

export async function setAlerts(on: boolean): Promise<void> {
  const granted = on && "Notification" in window && (Notification.permission === "granted" || (await Notification.requestPermission()) === "granted")
  try {
    localStorage.setItem(KEY, granted ? "1" : "0")
  } catch {
    return
  }
  listeners.forEach((fn) => fn())
}

function notify(title: string, body: string) {
  try {
    new Notification(title, { body, tag: `${title}|${body}` })
  } catch {
    return
  }
}

export function useAlerts() {
  const enabled = useAlertsEnabled()
  const { data } = useOverview()
  const jobs = useJobs()
  const schedule = useQuery({ queryKey: ["schedule"], queryFn: api.schedule, refetchInterval: 60_000, enabled })
  const seen = useRef<{ bots: Record<string, boolean>; rebalance?: string; jobs: Record<string, string>; errors: number } | null>(null)
  useEffect(() => {
    if (!data) return
    const rebalance = data.events.find((e) => e.kind === "rebalance")
    const errors = (schedule.data?.errors ?? []).reduce((s, e) => s + e.count, 0)
    const prev = seen.current
    seen.current = { bots: Object.fromEntries(data.bots.map((b) => [b.key, b.running])), rebalance: rebalance?.at, jobs: Object.fromEntries((jobs.data ?? []).map((j) => [j.id, j.status])), errors }
    if (!prev || !enabled) return
    for (const b of data.bots)
      if (prev.bots[b.key] && !b.running) notify(`⚠ ${b.name} зупинився`, b.last_stop && Date.parse(b.last_stop) > Date.now() - 60_000 ? "Зупинено з пульта." : "Процес завершився сам. Лог — у «Процесах».")
    if (rebalance?.kind === "rebalance" && rebalance.at !== prev.rebalance) notify("Квант: ребаланс", `${fmt.pnl(rebalance.pnl)} за добу · рахунок ${fmt.usd(rebalance.equity)}`)
    for (const j of jobs.data ?? [])
      if (prev.jobs[j.id] && prev.jobs[j.id] !== j.status && (j.status === "done" || j.status === "failed")) notify(j.status === "done" ? "Тест завершено" : "⚠ Тест упав", j.title)
    if (errors > prev.errors) notify("⚠ Нова помилка", "Подробиці — у «Процесах», «Помилки за добу».")
  }, [data, jobs.data, schedule.data, enabled])
}
