import type { ActivityEvent, JobStatus } from "./types"

const usd = new Intl.NumberFormat("uk-UA", { minimumFractionDigits: 2, maximumFractionDigits: 2 })
const usd0 = new Intl.NumberFormat("uk-UA", { maximumFractionDigits: 0 })
const num = new Intl.NumberFormat("uk-UA", { maximumFractionDigits: 2 })
const priceTiers = [
  { from: 1000, nf: new Intl.NumberFormat("uk-UA", { minimumFractionDigits: 1, maximumFractionDigits: 1 }) },
  { from: 100, nf: new Intl.NumberFormat("uk-UA", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) },
  { from: 1, nf: new Intl.NumberFormat("uk-UA", { minimumFractionDigits: 3, maximumFractionDigits: 3 }) },
  { from: 0, nf: new Intl.NumberFormat("uk-UA", { minimumSignificantDigits: 4, maximumSignificantDigits: 4 }) },
]
const plurals = new Intl.PluralRules("uk-UA")

const MINUS = "\u2212"

function isZero(value: number, digits: number): boolean {
  return Number(Math.abs(value).toFixed(digits)) === 0
}

function signed(text: string, value: number, digits = 2): string {
  if (isZero(value, digits)) return text
  return value > 0 ? `+${text}` : `${MINUS}${text}`
}

export const fmt = {
  usd: (v: number | null | undefined) => (v == null ? "—" : `$${usd.format(isZero(v, 2) ? 0 : v).replace("-", MINUS)}`),
  usd0: (v: number | null | undefined) => (v == null ? "—" : `$${usd0.format(v)}`),
  pnl: (v: number | null | undefined) => (v == null ? "—" : signed(`$${usd.format(Math.abs(v))}`, v)),
  pct: (v: number | null | undefined, digits = 2) => (v == null ? "—" : signed(`${Math.abs(v).toFixed(digits).replace(".", ",")} %`, v, digits)),
  pctPlain: (v: number | null | undefined, digits = 1) => (v == null ? "—" : `${v.toFixed(digits).replace(".", ",").replace("-", MINUS)} %`),
  ratio: (v: number | null | undefined, digits = 2) => (v == null ? "—" : num.format(Number(v.toFixed(digits)))),
  times: (v: number | null | undefined, digits = 2) => (v == null ? "—" : `${num.format(Number(v.toFixed(digits)))}×`),
  weight: (v: number) => signed(`${Math.abs(100 * v).toFixed(2).replace(".", ",")} %`, 100 * v),
  price: (v: number | null | undefined, reference?: number) => {
    if (v == null) return "—"
    const size = Math.abs(reference ?? v)
    return (priceTiers.find((t) => size >= t.from) ?? priceTiers[priceTiers.length - 1]!).nf.format(v)
  },
  int: (v: number | null | undefined) => (v == null ? "—" : usd0.format(v)),
}

export function plural(n: number, one: string, few: string, many: string): string {
  const rule = plurals.select(n)
  return `${n} ${rule === "one" ? one : rule === "few" ? few : many}`
}

export const ticker = (symbol: string) => symbol.replace(/USDT$/, "")

const dayFmt = new Intl.DateTimeFormat("uk-UA", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" })
const dayShort = new Intl.DateTimeFormat("uk-UA", { day: "numeric", month: "short", timeZone: "UTC" })
const timeFmt = new Intl.DateTimeFormat("uk-UA", { hour: "2-digit", minute: "2-digit", timeZone: "UTC" })
const dateTimeFmt = new Intl.DateTimeFormat("uk-UA", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", timeZone: "UTC" })
const editionFmt = new Intl.DateTimeFormat("uk-UA", { weekday: "long", day: "numeric", month: "long", year: "numeric", timeZone: "UTC" })

export const when = {
  day: (iso: string) => dayFmt.format(new Date(iso)),
  dayShort: (iso: string) => dayShort.format(new Date(iso)),
  time: (iso: string) => `${timeFmt.format(new Date(iso))} UTC`,
  dateTime: (iso: string) => `${dateTimeFmt.format(new Date(iso))} UTC`,
  edition: (iso: string) => editionFmt.format(new Date(iso)),
  ago: (iso: string, now = Date.now()) => {
    const s = Math.round((now - new Date(iso).getTime()) / 1000)
    if (s < 60) return `${Math.max(s, 0)} с тому`
    if (s < 3600) return `${Math.floor(s / 60)} хв тому`
    if (s < 86400) return `${Math.floor(s / 3600)} год ${Math.floor((s % 3600) / 60)} хв тому`
    return `${Math.floor(s / 86400)} дн тому`
  },
  until: (iso: string, now = Date.now()) => {
    const s = Math.max(0, Math.round((new Date(iso).getTime() - now) / 1000))
    const h = Math.floor(s / 3600)
    const m = Math.floor((s % 3600) / 60)
    return h ? `через ${h} год ${m} хв` : `через ${m} хв`
  },
  duration: (seconds: number | null | undefined) => {
    if (seconds == null) return "—"
    const d = Math.floor(seconds / 86400)
    const h = Math.floor((seconds % 86400) / 3600)
    const m = Math.floor((seconds % 3600) / 60)
    if (d) return `${d} дн ${h} год`
    if (h) return `${h} год ${m} хв`
    return `${m} хв`
  },
}

/** Direction of a figure as it will be printed: values that round to zero at `digits` are flat, so color never contradicts the text. */
export function tone(v: number | null | undefined, digits = 2): "gain" | "loss" | "flat" {
  if (v == null || isZero(v, digits)) return "flat"
  return v > 0 ? "gain" : "loss"
}

export const EVENT_LABELS: Record<string, string> = {
  binance_spot_listing: "Лістинг Binance (спот)",
  binance_perp_listing: "Лістинг Binance (ф’ючерс)",
  binance_spot_delisting: "Делістинг Binance (спот)",
  binance_perp_delisting: "Делістинг Binance (ф’ючерс)",
  binance_monitoring_tag: "Тег моніторингу",
  binance_seed_tag: "Seed-тег",
  upbit_krw_listing: "Лістинг Upbit (KRW)",
  upbit_btc_listing: "Лістинг Upbit (BTC)",
  upbit_warning: "Попередження Upbit",
  upbit_caution: "Застереження Upbit",
  upbit_delisting: "Делістинг Upbit",
  upbit_warning_lifted: "Попередження Upbit знято",
  upbit_listing: "Лістинг Upbit (BTC/USDT)",
  shock_pump_1h: "Різкий ріст за 1 год",
  shock_dump_1h: "Різке падіння за 1 год",
  shock_pump_4h: "Різкий ріст за 4 год",
  shock_dump_4h: "Різке падіння за 4 год",
  volume_spike: "Сплеск обсягу",
  breakout_30d: "Пробій 30-денного максимуму",
  breakdown_30d: "Пробій 30-денного мінімуму",
  funding_squeeze: "Фандінг-стиснення",
  funding_crowded: "Перекошений фандінг",
  new_perp: "Новий ф’ючерс",
}

export function eventLabel(type: string): string {
  return EVENT_LABELS[type] ?? type.replaceAll("_", " ")
}

function seconds(n: number): string {
  return n < 60 ? `${n} с` : n % 3600 === 0 && n >= 7200 ? `${n / 3600} год` : `${Math.round(n / 60)} хв`
}

/** A playbook in words: "SHORT 10x hold 600s SL 5% TP 10%" and "LONG 1x, enter +60m, hold ≤480m, SL 10%" read as Ukrainian trading shorthand. */
export function playbookText(text: string | null | undefined): string {
  if (!text) return "—"
  return text
    .replace(/\bLONG\b/g, "лонг")
    .replace(/\bSHORT\b/g, "шорт")
    .replace(/(\d+(?:\.\d+)?)x\b/g, "$1×")
    .replace(/enter \+(\d+)m\b/g, (_, m: string) => `вхід через ${seconds(60 * Number(m))}`)
    .replace(/hold ≤(\d+)m\b/g, (_, m: string) => `тримати до ${seconds(60 * Number(m))}`)
    .replace(/hold (\d+)s\b/g, (_, n: string) => `тримати ${seconds(Number(n))}`)
    .replace(/\bSL (\d+(?:\.\d+)?)%/g, "стоп $1 %")
    .replace(/\bTP (\d+(?:\.\d+)?)%/g, "тейк $1 %")
    .replace(/\btrail (\d+(?:\.\d+)?)%/g, "трейл $1 %")
}

/** A trade trigger "upbit_caution: LONG 1x, enter +60m, …" split into the event and the playbook it ran. */
export function triggerParts(trigger: string): { event: string; playbook: string } {
  const at = trigger.indexOf(": ")
  return at < 0 ? { event: eventLabel(trigger), playbook: "" } : { event: eventLabel(trigger.slice(0, at)), playbook: playbookText(trigger.slice(at + 2)) }
}

export const JOB_STATUS: Record<JobStatus, string> = { queued: "у черзі", running: "рахується", done: "готово", failed: "помилка", cancelled: "скасовано" }

const JOB_TAPE: Record<JobStatus, string> = { queued: "тест у черзі", running: "тест рахується", done: "тест завершено", failed: "тест завершився помилкою", cancelled: "тест скасовано" }

const EXIT_REASONS: Record<string, string> = { stop: "стоп", take_profit: "тейк-профіт", time: "вихід за часом", liquidation: "ліквідація", closed: "закрито" }

export const exitReason = (reason: string | null | undefined) => (reason ? (EXIT_REASONS[reason] ?? reason.replaceAll("_", " ")) : "")

const SOURCES: Record<string, string> = { binance: "Binance", upbit: "Upbit" }

export const sideLabel = (side: "long" | "short") => (side === "long" ? "лонг" : "шорт")

export interface EventLine {
  title: string
  detail: string
  amount: number | null
  quiet: boolean
  alert: boolean
}

/** One tape entry in words: every event kind gets its Ukrainian wording and figures here, nowhere else. */
export function describeEvent(e: ActivityEvent): EventLine {
  switch (e.kind) {
    case "notice":
      return {
        title: e.title,
        detail: e.events.length ? e.events.map((x) => [eventLabel(x.type), x.symbols.map(ticker).join(", ")].filter(Boolean).join(": ")).join("; ") : `${SOURCES[e.source] ?? e.source} · без торгової події`,
        amount: null,
        quiet: !e.events.length,
        alert: false,
      }
    case "trade_open":
      return { title: `${ticker(e.symbol)}: відкрито ${sideLabel(e.side)}`, detail: `${triggerParts(e.trigger).event} · ${e.mode === "live" ? "реальні гроші" : "папір"}`, amount: null, quiet: false, alert: false }
    case "trade_close":
      return { title: `${ticker(e.symbol)}: закрито ${sideLabel(e.side)}`, detail: [exitReason(e.exit_reason), e.mode === "live" ? "реальні гроші" : "папір"].filter(Boolean).join(" · "), amount: e.pnl, quiet: false, alert: false }
    case "rebalance":
      return { title: `${e.opening ? "Книгу відкрито" : "Ребаланс"}: ${plural(e.longs, "лонг", "лонги", "лонгів")}, ${plural(e.shorts, "шорт", "шорти", "шортів")}`, detail: `витрати ${fmt.usd(e.cost)} · капітал ${fmt.usd(e.equity)}`, amount: e.pnl, quiet: false, alert: false }
    case "job":
      return { title: e.title, detail: JOB_TAPE[e.status], amount: null, quiet: e.status === "cancelled", alert: e.status === "failed" }
  }
}
