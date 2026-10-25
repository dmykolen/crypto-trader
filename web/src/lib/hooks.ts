import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useEffect, useRef, useState } from "react"

import { api } from "./api"
import type { BotKey, Job, JobKind, Mode } from "./types"

export function useOverview() {
  return useQuery({ queryKey: ["overview"], queryFn: api.overview, refetchInterval: 5000 })
}

export function useLedger() {
  return useQuery({ queryKey: ["ledger"], queryFn: api.quantLedger, refetchInterval: 15000 })
}

export function useEvidence() {
  return useQuery({ queryKey: ["evidence"], queryFn: api.evidence, retry: false, staleTime: 60_000 })
}

export function useJobs() {
  return useQuery({
    queryKey: ["jobs"],
    queryFn: api.jobs,
    refetchInterval: (q) => ((q.state.data ?? []).some((j) => j.status === "running" || j.status === "queued") ? 2000 : 10000),
  })
}

export function useJob<R>(id: string | undefined) {
  return useQuery({
    queryKey: ["job", id],
    queryFn: () => api.job<R>(id as string),
    enabled: Boolean(id),
    refetchInterval: (q) => (q.state.data && (q.state.data.status === "running" || q.state.data.status === "queued") ? 1500 : false),
  })
}

export function useBotControl() {
  const client = useQueryClient()
  const refresh = () => {
    void client.invalidateQueries({ queryKey: ["overview"] })
    void client.invalidateQueries({ queryKey: ["bots"] })
  }
  const start = useMutation({ mutationFn: (v: { bot: BotKey; mode: Mode; confirm?: string }) => api.startBot(v.bot, v.mode, v.confirm), onSettled: refresh })
  const stop = useMutation({ mutationFn: (bot: BotKey) => api.stopBot(bot), onSettled: refresh })
  return { start, stop }
}

export function useCreateJob() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (v: { kind: JobKind; params: Record<string, unknown> }) => api.createJob(v.kind, v.params),
    onSuccess: (job: Job) => {
      client.setQueryData<Job[]>(["jobs"], (old) => [job, ...(old ?? [])])
      void client.invalidateQueries({ queryKey: ["jobs"] })
    },
  })
}

/** True for a few seconds after `value` changes: the figure is reprinted in wet ink. */
export function useWet(value: unknown): number {
  const [stamp, setStamp] = useState(0)
  const first = useRef(true)
  const last = useRef(value)
  useEffect(() => {
    if (first.current) {
      first.current = false
      return
    }
    if (last.current !== value) {
      last.current = value
      setStamp(Date.now())
    }
  }, [value])
  return stamp
}

/** Keys seen on a previous render; anything new prints wet. */
export function useFreshKeys(keys: string[]): Set<string> {
  const seen = useRef<Set<string> | null>(null)
  const [fresh, setFresh] = useState<Set<string>>(new Set())
  const signature = keys.join("|")
  useEffect(() => {
    if (seen.current === null) {
      seen.current = new Set(keys)
      return
    }
    const next = new Set(keys.filter((k) => !seen.current?.has(k)))
    keys.forEach((k) => seen.current?.add(k))
    if (next.size) setFresh(next)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [signature])
  return fresh
}

export function useNow(intervalMs = 1000): number {
  const [now, setNow] = useState(Date.now())
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), intervalMs)
    return () => clearInterval(id)
  }, [intervalMs])
  return now
}
