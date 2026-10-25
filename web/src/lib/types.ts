export type BotKey = "notice" | "quant"
export type Mode = "paper" | "live"
export type Tone = "info" | "gain" | "loss" | "quiet" | "warn"

export interface BotState {
  key: BotKey
  number: number
  name: string
  what: string
  commands: string[]
  confirm_phrase: string
  running: boolean
  pid: number | null
  mode: Mode
  started_at: string | null
  uptime_s: number | null
  managed: boolean
  log: string | null
  last_stop: string | null
}

export interface SystemInfo {
  now: string
  trading_mode_default: string
  live_ready: boolean
  testnet: boolean
  models_trained_through: string | null
  models_trained_at: string | null
  next_retrain_due: string
  next_quant_rebalance: string
  risk: {
    notice: { margin_fraction: number; max_leverage: number; max_open_positions: number }
    quant: { leverage: number; max_gross: number; max_position: number; kill_drawdown: number }
  }
}

export interface NoticeTradeBrief {
  symbol: string
  side: "LONG" | "SHORT"
  trigger: string
  entry_time: string
  status: string
  pnl: number | null
}

export interface NoticePaper {
  trades: number
  open: number
  closed: number
  win_rate_pct: number | null
  realized_pnl: number
  latest: NoticeTradeBrief[]
}

export interface LedgerRow {
  day: string
  rebalanced_at: string
  equity: number
  pnl_since_last: number
  funding_paid?: number
  cost: number
  turnover: number
  longs: number
  shorts: number
  gross: number
  return_since_start_pct: number
}

export interface QuantPaper {
  status?: string
  since?: string | null
  rebalances?: number
  start_equity?: number
  equity?: number
  return_pct?: number
  positions?: number
  equity_by_day?: Record<string, number>
  last_rebalance?: LedgerRow | null
}

export interface NoticeEvent {
  type: string
  symbols: string[]
}

interface TradeFacts {
  at: string
  bot: "notice"
  symbol: string
  side: "long" | "short"
  mode: Mode
  trigger: string
}

export type ActivityEvent =
  | { at: string; bot: "notice"; kind: "notice"; title: string; source: string; events: NoticeEvent[] }
  | (TradeFacts & { kind: "trade_open" })
  | (TradeFacts & { kind: "trade_close"; pnl: number; exit_reason: string | null })
  | { at: string; bot: "quant"; kind: "rebalance"; longs: number; shorts: number; pnl: number; cost: number; equity: number; opening: boolean }
  | { at: string; bot: "lab"; kind: "job"; title: string; status: JobStatus; job: string }

export interface Overview {
  system: SystemInfo
  bots: BotState[]
  paper: { notice: NoticePaper; quant: QuantPaper }
  events: ActivityEvent[]
}

export interface QuantPosition {
  symbol: string
  side: "long" | "short"
  weight: number
  notional: number
  entry: number
  price: number | null
  move: number | null
  pnl: number | null
}

export interface QuantLedger {
  started: boolean
  start_equity: number
  equity: number
  equity_now: number
  unrealized: number
  return_now_pct: number
  history: LedgerRow[]
  positions: QuantPosition[]
  gross: number
  net: number
  priced_at: string
  next_rebalance: string
}

export interface Stats {
  start_equity: number
  final_equity: number
  return_pct: number
  annual_return_pct: number | null
  sharpe: number | null
  max_drawdown_pct: number
  worst_day_pct: number
  best_day_pct: number
  positive_days_pct: number
  positive_months: number
  months: number
  days: number
}

export interface EvidencePeriod {
  key: string
  name: string
  note: string
  start: string
  end: string | null
  from: string
  to: string
  stats: Stats
}

export interface Evidence {
  built_at: string
  days: string[]
  equity: number[]
  drawdown: number[]
  stats: Stats
  periods: EvidencePeriod[]
}

export interface SeriesResult {
  days: string[]
  returns: number[]
  equity: number[]
  drawdown: number[]
  monthly: { month: string; return: number }[]
  stats: Stats
}

export interface BookSide {
  symbol: string
  weight: number
}

export interface BookSummary {
  longs: BookSide[]
  shorts: BookSide[]
  gross: number
  net: number
  positions: number
}

export type JobStatus = "queued" | "running" | "done" | "failed" | "cancelled"

export interface Job<R = unknown> {
  id: string
  kind: JobKind
  title: string
  params: Record<string, unknown>
  status: JobStatus
  created_at: string
  started_at?: string
  finished_at?: string
  progress: string | null
  pid: number | null
  error?: string
  trace?: string
  result?: R
}

export type JobKind = "quant_period" | "quant_forward" | "quant_book" | "notice_replay" | "quant_retrain" | "quant_evidence"

export interface DayCount {
  day: string
  total: number
  events: number
}

export interface NoticeItem {
  id: string
  source: string
  title: string
  url: string | null
  published_at: string
  seen_at: string
  latency_s: number
  events: NoticeEvent[]
}

export interface Trade {
  id: number
  mode: string
  symbol: string
  side: number
  leverage: number
  margin: number
  quantity: number
  entry_price: number
  entry_time: string
  stop_price: number | null
  take_profit_price: number | null
  exit_due: string
  trigger: string
  status: string
  exit_price: number | null
  exit_time: string | null
  exit_reason: string | null
  fees: number
  pnl: number | null
}

export interface Klines {
  symbol: string
  interval?: string
  bars: [number, number, number, number, number, number][]
}

export interface QuantConfig {
  ensemble: Record<string, unknown>
  models: Record<string, unknown>
  decision: string
  costs: { per_side: number; note: string }
}
