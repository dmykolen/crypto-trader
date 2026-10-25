import type { BotKey, BotState, DayCount, Evidence, Job, JobKind, Klines, Mode, NoticeItem, Overview, QuantConfig, QuantLedger, SystemInfo, Trade } from "./types"

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message)
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const mutating = init.method && init.method !== "GET"
  const res = await fetch(`/api/v1${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(mutating ? { "X-Trader-UI": "1" } : {}), ...init.headers },
  })
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail)
    } catch {
      /* the body was not JSON; keep the status text */
    }
    throw new ApiError(res.status, detail)
  }
  return res.json() as Promise<T>
}

export const api = {
  overview: () => request<Overview>("/overview"),
  system: () => request<SystemInfo>("/system"),
  bots: () => request<BotState[]>("/bots"),
  startBot: (bot: BotKey, mode: Mode, confirm?: string) => request<BotState>(`/bots/${bot}/start`, { method: "POST", body: JSON.stringify({ mode, confirm }) }),
  stopBot: (bot: BotKey) => request<BotState>(`/bots/${bot}/stop`, { method: "POST" }),
  logs: (bot: BotKey, lines = 300) => request<{ bot: BotKey; lines: string[] }>(`/bots/${bot}/logs?lines=${lines}`),
  quantLedger: () => request<QuantLedger | { started: false }>("/quant/ledger"),
  quantConfig: () => request<QuantConfig>("/quant/config"),
  evidence: () => request<Evidence>("/quant/evidence"),
  noticeFeed: (limit = 100, eventsOnly = false) => request<NoticeItem[]>(`/notice/feed?limit=${limit}&events_only=${eventsOnly}`),
  noticeDaily: (days = 14) => request<DayCount[]>(`/notice/daily?days=${days}`),
  trades: (limit = 200) => request<Trade[]>(`/notice/trades?limit=${limit}`),
  playbooks: () => request<Record<string, unknown>>("/playbooks"),
  klines: (symbol: string, interval = "1h", hours = 72) => request<Klines>(`/market/klines?symbol=${encodeURIComponent(symbol)}&interval=${interval}&hours=${hours}`),
  jobs: () => request<Job[]>("/jobs"),
  job: <R>(id: string) => request<Job<R>>(`/jobs/${id}`),
  createJob: (kind: JobKind, params: Record<string, unknown>) => request<Job>("/jobs", { method: "POST", body: JSON.stringify({ kind, params }) }),
  cancelJob: (id: string) => request<Job>(`/jobs/${id}`, { method: "DELETE" }),
}
