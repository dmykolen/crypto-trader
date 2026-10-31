import { useMemo, useState } from "react"

import { fmt, when } from "../lib/format"
import type { Evidence } from "../lib/types"

interface Props {
  evidence: Evidence
  height?: number
}

const SHADES = ["0.13", "0.03", "0.07", "0.22"]

/** The production book, $1000 from July 2021, log scale, each evidence period printed as its own band. */
export function EvidenceChart({ evidence, height = 300 }: Props) {
  const [hover, setHover] = useState<number | null>(null)
  const W = 960
  const H = height
  const L = 54
  const R = 12
  const T = 26
  const B = 26
  const n = evidence.days.length
  const geo = useMemo(() => {
    const lo = Math.log(Math.min(...evidence.equity) * 0.92)
    const hi = Math.log(Math.max(...evidence.equity) * 1.06)
    const x = (i: number) => L + ((W - L - R) * i) / Math.max(n - 1, 1)
    const y = (v: number) => T + (H - T - B) * (1 - (Math.log(v) - lo) / (hi - lo))
    const points = evidence.equity.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ")
    const ticks = [500, 750, 1000, 1500, 2000, 3000, 4000, 6000, 8000, 12000, 16000].filter((v) => Math.log(v) >= lo && Math.log(v) <= hi)
    const index = new Map(evidence.days.map((d, i) => [d, i]))
    const years = Array.from(new Set(evidence.days.map((d) => d.slice(0, 4))))
      .slice(1)
      .map((yr) => ({ yr, i: index.get(evidence.days.find((d) => d.startsWith(yr)) ?? "") ?? 0 }))
    return { x, y, points, ticks, index, years }
  }, [evidence, n, H])

  const at = hover ?? n - 1
  const atDay = evidence.days[at] ?? ""
  const atEquity = evidence.equity[at] ?? 0
  return (
    <figure className="w-full">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="h-auto w-full"
        role="img"
        aria-label={`Капітал бойової стратегії з ${evidence.days[0]} по ${evidence.days[n - 1]}: від $1 000 до ${fmt.usd0(evidence.equity[n - 1])}`}
        onMouseMove={(e) => {
          const box = (e.currentTarget as SVGSVGElement).getBoundingClientRect()
          const px = ((e.clientX - box.left) / box.width) * W
          setHover(Math.max(0, Math.min(n - 1, Math.round(((px - L) / (W - L - R)) * (n - 1)))))
        }}
        onMouseLeave={() => setHover(null)}
      >
        {evidence.periods.map((p, k) => {
          const a = geo.index.get(p.from) ?? 0
          const b = geo.index.get(p.to) ?? n - 1
          const xa = geo.x(a)
          const xb = geo.x(b)
          return (
            <g key={p.key}>
              <rect x={xa} y={T} width={Math.max(xb - xa, 3)} height={H - T - B} fill="var(--text)" opacity={SHADES[k] ?? "0.06"} />
              <text
                x={xb - xa > 70 ? (xa + xb) / 2 : Math.min(xb, W - R)}
                y={T - 9}
                textAnchor={xb - xa > 70 ? "middle" : "end"}
                fontSize={11}
                fill="var(--text-2)"
                style={{ fontFamily: "var(--font-head)", fontWeight: 700 }}
              >
                {p.name}
              </text>
            </g>
          )
        })}
        {geo.ticks.map((v) => (
          <g key={v}>
            <line x1={L} x2={W - R} y1={geo.y(v)} y2={geo.y(v)} stroke="var(--line)" strokeWidth={v === 1000 ? 1 : 0.6} strokeDasharray={v === 1000 ? undefined : "2 4"} />
            <text x={L - 6} y={geo.y(v) + 3.5} textAnchor="end" fontSize={10} fill="var(--text-3)" className="num">
              ${v.toLocaleString("uk-UA")}
            </text>
          </g>
        ))}
        {geo.years.map(({ yr, i }) => (
          <text key={yr} x={geo.x(i)} y={H - 8} textAnchor="middle" fontSize={10} fill="var(--text-3)" className="num">
            {yr}
          </text>
        ))}
        <polyline points={geo.points} fill="none" stroke="var(--data)" strokeWidth={1.75} strokeLinejoin="round" />
        <line x1={geo.x(at)} x2={geo.x(at)} y1={T} y2={H - B} stroke="var(--text-3)" strokeWidth={0.75} />
        <circle cx={geo.x(at)} cy={geo.y(atEquity)} r={3.2} fill="var(--data)" stroke="var(--bg)" strokeWidth={1.5} />
      </svg>
      <figcaption className="num mt-1 flex flex-wrap gap-x-4 text-[12px] text-text-2">
        <span>{atDay ? `${hover === null ? "останній день у даних: " : ""}${when.day(atDay)}` : ""}</span>
        <span>капітал {fmt.usd(atEquity)}</span>
        <span>просідання {fmt.pct(100 * (evidence.drawdown[at] ?? 0), 1)}</span>
      </figcaption>
    </figure>
  )
}
