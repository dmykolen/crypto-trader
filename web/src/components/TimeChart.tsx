import { AreaSeries, BaselineSeries, CandlestickSeries, ColorType, createChart, createSeriesMarkers, CrosshairMode, HistogramSeries, LineSeries, TickMarkType, type IChartApi, type Time } from "lightweight-charts"
import { useEffect, useRef } from "react"

import { fmt } from "../lib/format"
import { alpha, cssVar, useEdition, useSkin } from "../lib/theme"

export interface LinePoint {
  time: string | number
  value: number
}

export interface CandlePoint {
  time: number
  open: number
  high: number
  low: number
  close: number
}

export interface SeriesSpec {
  kind: "line" | "area" | "underwater" | "histogram" | "candles"
  data: LinePoint[] | CandlePoint[]
  color?: string
  title?: string
  priceFormat?: "usd" | "pct" | "price"
  baseline?: { value: number; title: string }
  minRange?: number
  markers?: { time: number; position: "aboveBar" | "belowBar"; color: string; shape: "arrowUp" | "arrowDown" | "circle"; text: string }[]
  muteBefore?: number
  priceLines?: { price: number; title: string; color?: string }[]
  quiet?: boolean
}

interface TimeChartProps {
  series: SeriesSpec[]
  height?: number
  label: string
  logScale?: boolean
}

function resolve(color: string | undefined, fallback: string): string {
  if (!color) return cssVar(fallback)
  const m = color.match(/^var\((--[\w-]+)\)$/)
  return m ? cssVar(m[1] as string) : color
}

function formatter(kind: SeriesSpec["priceFormat"]) {
  if (kind === "pct") return { type: "custom" as const, minMove: 0.0001, formatter: (v: number) => fmt.pct(100 * v, 1) }
  if (kind === "usd") return { type: "custom" as const, minMove: 0.01, formatter: (v: number) => (Math.abs(v) >= 10000 ? fmt.usd0(v) : fmt.usd(v)) }
  return { type: "price" as const, precision: 4, minMove: 0.0001 }
}

type Range = { priceRange: { minValue: number; maxValue: number } } | null

const ticks = {
  year: new Intl.DateTimeFormat("uk-UA", { year: "numeric", timeZone: "UTC" }),
  month: new Intl.DateTimeFormat("uk-UA", { month: "short", timeZone: "UTC" }),
  day: new Intl.DateTimeFormat("uk-UA", { day: "numeric", month: "short", timeZone: "UTC" }),
  time: new Intl.DateTimeFormat("uk-UA", { hour: "2-digit", minute: "2-digit", timeZone: "UTC" }),
}

function asDate(time: Time): Date {
  if (typeof time === "number") return new Date(time * 1000)
  if (typeof time === "string") return new Date(`${time}T00:00:00Z`)
  return new Date(Date.UTC(time.year, time.month - 1, time.day))
}

/** Axis labels in Ukrainian: a full year at year boundaries, month names, day and month, then UTC clock time. */
function tickMark(time: Time, type: TickMarkType): string {
  const at = asDate(time)
  if (type === TickMarkType.Year) return ticks.year.format(at).replace(/\s*р\.$/, "")
  if (type === TickMarkType.Month) return ticks.month.format(at)
  if (type === TickMarkType.DayOfMonth) return ticks.day.format(at)
  return ticks.time.format(at)
}

/** Never let autoscale blow a small move up to the full height: the visible range spans at least `minRange` and includes the baseline. */
function scale(spec: SeriesSpec) {
  if (spec.minRange === undefined && spec.baseline === undefined) return {}
  return {
    autoscaleInfoProvider: (original: () => Range): Range => {
      const res = original()
      if (!res) return res
      let lo = Math.min(res.priceRange.minValue, spec.baseline?.value ?? Infinity)
      let hi = Math.max(res.priceRange.maxValue, spec.baseline?.value ?? -Infinity)
      const widen = Math.max(0, (spec.minRange ?? 0) - (hi - lo)) / 2
      lo -= widen
      hi += widen
      return { ...res, priceRange: { minValue: lo, maxValue: hi } }
    },
  }
}

/** Interactive time-series chart in the page's ink: crosshair, zoom, the edition's colors. */
export function TimeChart({ series, height = 280, label, logScale = false }: TimeChartProps) {
  const host = useRef<HTMLDivElement>(null)
  const chart = useRef<IChartApi | null>(null)
  const edition = useEdition()
  const skin = useSkin()

  useEffect(() => {
    if (!host.current) return
    const ink = cssVar("--raised")
    const rule = cssVar("--line")
    const c = createChart(host.current, {
      height,
      autoSize: true,
      layout: { background: { type: ColorType.Solid, color: "transparent" }, textColor: cssVar("--text-3"), fontFamily: "Geologica Variable, sans-serif", fontSize: 11, attributionLogo: false },
      grid: { vertLines: { visible: false }, horzLines: { color: alpha(rule, 0.7), style: 1 } },
      rightPriceScale: { borderColor: rule, mode: logScale ? 1 : 0, minimumWidth: 72 },
      timeScale: { borderColor: rule, timeVisible: series.some((s) => s.kind === "candles"), secondsVisible: false, tickMarkFormatter: tickMark },
      crosshair: { mode: CrosshairMode.Magnet, vertLine: { color: cssVar("--line-strong"), labelBackgroundColor: ink }, horzLine: { color: cssVar("--line-strong"), labelBackgroundColor: ink } },
      localization: { locale: "uk-UA" },
    })
    chart.current = c
    for (const s of series) {
      const color = resolve(s.color, "--text")
      if (s.kind === "candles") {
        const gain = cssVar("--gain")
        const loss = cssVar("--loss")
        const cs = c.addSeries(CandlestickSeries, { upColor: gain, downColor: loss, borderUpColor: gain, borderDownColor: loss, wickUpColor: gain, wickDownColor: loss })
        const mute = cssVar("--text-3")
        cs.setData((s.data as CandlePoint[]).map((d) => ({ ...d, time: d.time as Time, ...(s.muteBefore !== undefined && d.time < s.muteBefore ? { color: mute, wickColor: mute, borderColor: mute } : {}) })))
        if (s.markers?.length) createSeriesMarkers(cs, [...s.markers].sort((a, b) => a.time - b.time).map((m) => ({ ...m, time: m.time as Time, color: resolve(m.color, "--text") })))
        for (const line of s.priceLines ?? []) cs.createPriceLine({ price: line.price, color: resolve(line.color, "--text-3"), lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: line.title })
      } else if (s.kind === "histogram") {
        const hs = c.addSeries(HistogramSeries, { color, priceFormat: formatter(s.priceFormat), title: s.title })
        hs.setData((s.data as LinePoint[]).map((d) => ({ time: d.time as Time, value: d.value, color: d.value >= 0 ? cssVar("--gain") : cssVar("--loss") })))
      } else if (s.kind === "underwater") {
        const us = c.addSeries(BaselineSeries, {
          baseValue: { type: "price", price: 0 },
          topLineColor: color,
          topFillColor1: "transparent",
          topFillColor2: "transparent",
          bottomLineColor: color,
          bottomFillColor1: alpha(color, 0.15),
          bottomFillColor2: alpha(color, 0.25),
          lineWidth: 1,
          priceFormat: formatter(s.priceFormat),
          title: s.title,
          lastValueVisible: false,
          priceLineVisible: false,
        })
        us.setData((s.data as LinePoint[]).map((d) => ({ time: d.time as Time, value: d.value })))
      } else if (s.kind === "area") {
        const as = c.addSeries(AreaSeries, { lineColor: color, topColor: alpha(color, 0.3), bottomColor: alpha(color, 0.02), lineWidth: 2, priceFormat: formatter(s.priceFormat), title: s.title, ...scale(s) })
        as.setData((s.data as LinePoint[]).map((d) => ({ time: d.time as Time, value: d.value })))
        if (s.baseline) as.createPriceLine({ price: s.baseline.value, color: cssVar("--text-3"), lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: s.baseline.title })
      } else {
        const ls = c.addSeries(LineSeries, {
          color,
          lineWidth: s.quiet ? 1 : 2,
          lineStyle: s.quiet ? 2 : 0,
          priceFormat: formatter(s.priceFormat),
          title: s.title,
          lastValueVisible: !s.quiet,
          priceLineVisible: false,
          crosshairMarkerVisible: !s.quiet,
          pointMarkersVisible: !s.quiet && s.data.length <= 40,
          ...scale(s),
        })
        ls.setData((s.data as LinePoint[]).map((d) => ({ time: d.time as Time, value: d.value })))
        if (s.baseline) ls.createPriceLine({ price: s.baseline.value, color: cssVar("--text-3"), lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: s.baseline.title })
      }
    }
    const fit = () => c.timeScale().fitContent()
    fit()
    c.timeScale().subscribeSizeChange(fit)
    const el = host.current
    const scrollPage = (e: WheelEvent) => !e.ctrlKey && !e.metaKey && Math.abs(e.deltaY) > Math.abs(e.deltaX) && e.stopPropagation()
    el.addEventListener("wheel", scrollPage, { capture: true })
    return () => {
      el.removeEventListener("wheel", scrollPage, { capture: true })
      c.timeScale().unsubscribeSizeChange(fit)
      c.remove()
      chart.current = null
    }
  }, [series, height, edition, skin, logScale])

  return <div ref={host} role="img" aria-label={label} style={{ height }} className="w-full" />
}
