interface SparkProps {
  values: number[]
  label: string
  width?: number
  height?: number
  color?: string
  baseline?: number
  minSpan?: number
  fill?: boolean
  className?: string
}

/** A word-sized line of real data (Tufte): the series, its baseline and the last value marked; short series show every observation. */
export function Spark({ values, label, width = 160, height = 36, color = "var(--ink)", baseline, minSpan = 0, fill = false, className }: SparkProps) {
  const clean = values.filter((v) => Number.isFinite(v))
  if (clean.length < 2) {
    return (
      <svg width={width} height={height} className={className} role="img" aria-label={`${label}: замало даних`}>
        <line x1={0} x2={width} y1={height / 2} y2={height / 2} stroke="var(--rule)" strokeDasharray="2 3" />
      </svg>
    )
  }
  const rawLo = Math.min(...clean, baseline ?? Infinity)
  const rawHi = Math.max(...clean, baseline ?? -Infinity)
  const widen = Math.max(0, minSpan - (rawHi - rawLo)) / 2
  const lo = rawLo - widen
  const hi = rawHi + widen
  const span = hi - lo || 1
  const pad = 4
  const x = (i: number) => pad + (i / (clean.length - 1)) * (width - 2 * pad)
  const y = (v: number) => pad + (1 - (v - lo) / span) * (height - 2 * pad)
  const points = clean.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ")
  const lastX = x(clean.length - 1)
  const lastY = y(clean[clean.length - 1] as number)
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} className={className} role="img" aria-label={label}>
      {fill && <polygon points={`${x(0)},${height} ${points} ${lastX},${height}`} fill={color} fillOpacity={0.1} />}
      {baseline !== undefined && <line x1={0} x2={width} y1={y(baseline)} y2={y(baseline)} stroke="var(--ink-3)" strokeWidth={0.75} strokeDasharray="2 3" />}
      <polyline points={points} fill="none" stroke={color} strokeWidth={1.4} strokeLinejoin="round" strokeLinecap="round" />
      {clean.length <= 24 && clean.slice(0, -1).map((v, i) => <circle key={i} cx={x(i)} cy={y(v)} r={1.6} fill={color} />)}
      <circle cx={lastX} cy={lastY} r={2.6} fill={color} />
    </svg>
  )
}
