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
  last_log_at?: string | null
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
  trades?: Record<string, number>
}

export type LimitVerdict = "collecting" | "cheaper" | "dearer" | "unclear"

export interface LimitTest {
  orders: number
  enough: number
  min_days: number
  verdict: LimitVerdict
  days?: number
  first?: number
  last?: number
  filled_through?: number
  filled_touch?: number
  market_cost?: number
  market_slippage?: number
  limit_cost_through?: number
  limit_cost_touch?: number
  saving?: number
  saving_se?: number | null
  saving_touch?: number
  saving_per_day_pct?: number
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

export type JobKind = "quant_period" | "quant_forward" | "quant_book" | "notice_replay" | "quant_retrain" | "quant_evidence" | "quant_day"

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
  decisions?: { at: string; event: string; token: string; outcome: "entered" | "scheduled" | "no_rule" | "too_old" | "too_slow" | "no_perp" | "blocked"; detail: string }[]
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

export interface PairTrade {
  side: "LONG" | "SHORT"
  entry_time: number
  exit_time: number
  entry: number
  exit: number
  reason: string
  stop?: number | null
  take?: number | null
  return_on_margin_pct: number
  pnl: number
  why: Record<string, number>
}

export type TacticFamily = "trend" | "revert" | "pattern" | "ml"

export type PairRole = "best" | "second" | "third" | "reference" | "worst"

export interface PairTactic {
  key: string
  label: string
  rule: string
  family: TacticFamily
  overlay: string
  pnl: number
  return_pct: number
  worst_pct: number
  in_market_hours: number
  pair_90d_sharpe: number | null
  record: { dev?: number | null; holdout?: number | null; untouched?: number | null }
}

export interface PairDay {
  symbol: string
  from: string
  to: string
  days: number
  source: string
  bars_in_window: number
  warmup_bars: number
  capital: number
  leverage: number
  leverage_rule: string
  price_move_pct: number
  atr_pct?: number
  bot?: { source: "paper" | "history"; return_pct: number; pnl?: number } | null
  summary: { tactics: number; positive: number; negative: number; flat: number; median_pnl: number; total_pnl?: number; tied_best?: number; robust: number; best: string; worst: string }
  families: Record<TacticFamily, { tactics: number; positive: number; pnl_sum: number }>
  reference: string
  book: { day: string; weight: number }[]
  book_known?: boolean
  candles: { time: number; open: number; high: number; low: number; close: number }[]
  tactics: PairTactic[]
  detail: { key: string; role?: PairRole; title?: string; label: string; about?: string; pnl?: number; trades: PairTrade[] }[]
}

export interface Upload {
  upload: string
  bars: number
  from: string
  to: string
}

export interface ProcessRow {
  key: string
  kind: "server" | "bot" | "job" | "cli"
  pid: number | null
  running: boolean
  started_at: string | null
  log: string | null
  cpu: number | null
  memory_mb: number | null
  port?: number | null
  mode?: Mode
  last_stop?: string | null
  last_log_at?: string | null
  managed?: boolean
  status?: JobStatus
  title?: string
  progress?: string | null
  command?: string
}

export interface DiskInfo {
  total: number
  used: number
  free: number
  folders: { key: string; bytes: number }[]
  stale: { files: number; bytes: number; keep_days: number }
}

export interface ScheduleItem {
  key: "rebalance" | "limit_test" | "retrain"
  next: string
  last: string | null
  last_pnl?: number | null
}

export interface ErrorSummary {
  source: "serve" | "quant" | "notice"
  count: number
  last_at: string | null
  recent: { at: string; line: string; detail: string }[]
}

export interface Autostart {
  enabled: boolean
  loaded: boolean
  supervised: boolean
  path: string
}

export type WhyGroup = "trend" | "momentum" | "overbought" | "volatility" | "volume" | "funding" | "btc" | "patterns" | "regime" | "time" | "other"

export interface Why {
  symbol: string
  day: string
  source: "reproduced" | "recorded"
  rebalanced_at: string
  decided_at: string
  of: number
  rank: number | null
  weight: number
  edge_pct: number | null
  xs_pct: number | null
  history: { day: string; rank: number; of: number; weight: number }[]
  factors: { group: WhyGroup; value: number; top: { feature: string; value: number }[] }[]
}
