import { when } from "../lib/format"
import type { DayCount } from "../lib/types"

/** Announcements per day as a bar strip: grey for every notice, the bot's hue for the share that carried a tradable event. */
export function DayBars({ days, height = 52 }: { days: DayCount[]; height?: number }) {
  if (!days.length) return null
  const width = 520
  const gap = 3
  const max = Math.max(1, ...days.map((d) => d.total))
  const bar = (width - gap * (days.length - 1)) / days.length
  const scale = (n: number) => (n / max) * (height - 1)
  const first = days[0] as DayCount
  const total = days.reduce((a, d) => a + d.total, 0)
  const withEvents = days.reduce((a, d) => a + d.events, 0)
  return (
    <figure>
      <figcaption className="num mb-1 text-[11.5px] text-text-3">
        <span aria-hidden className="inline-block h-2 w-2 bg-text-3/40" /> анонси по днях: {total} ·{" "}
        <span aria-hidden className="inline-block h-2 w-2" style={{ background: "var(--text)" }} /> з торговою подією: {withEvents}
      </figcaption>
      <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" className="block w-full" style={{ height }} role="img" aria-label={`Анонси по днях за ${days.length} днів: ${total}, з торговою подією ${withEvents}`}>
        <line x1={0} x2={width} y1={height - 0.5} y2={height - 0.5} stroke="var(--text-3)" strokeWidth={1} vectorEffect="non-scaling-stroke" />
        {days.map((d, i) => {
          const x = i * (bar + gap)
          return (
            <g key={d.day}>
              <title>{`${when.dayShort(d.day)}: анонсів ${d.total}, з подією ${d.events}`}</title>
              <rect x={x} y={height - scale(d.total)} width={bar} height={scale(d.total)} fill="var(--text-3)" fillOpacity={0.4} />
              {d.events > 0 && <rect x={x} y={height - scale(d.events)} width={bar} height={scale(d.events)} fill="var(--text)" />}
            </g>
          )
        })}
      </svg>
      <div className="num mt-1 flex justify-between gap-2 text-[11.5px] text-text-3" aria-hidden>
        <span>{when.dayShort(first.day)}</span>
        <span>сьогодні</span>
      </div>
    </figure>
  )
}
