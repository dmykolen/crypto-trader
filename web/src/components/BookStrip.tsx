import clsx from "clsx"
import { useState, type CSSProperties } from "react"
import { useNavigate } from "react-router-dom"

import { fmt, ticker } from "../lib/format"
import type { QuantPosition } from "../lib/types"
import { Signed } from "./Print"
import { Tip } from "./ui"

function shade(p: QuantPosition, max: number): string {
  const pnl = p.pnl ?? 0
  const strength = Math.round(26 + 64 * Math.min(1, Math.abs(pnl) / max))
  return `color-mix(in oklab, ${pnl >= 0 ? "var(--gain)" : "var(--loss)"} ${strength}%, var(--raised))`
}

function Readout({ p }: { p: QuantPosition }) {
  return (
    <span className="flex min-w-0 items-baseline gap-2 truncate">
      <b className="text-text">{ticker(p.symbol)}</b>
      <span className={p.side === "long" ? "text-gain" : "text-loss"}>{p.side === "long" ? "лонг" : "шорт"}</span>
      <span className="num">{fmt.pctPlain(100 * Math.abs(p.weight), 2)}</span>
      <span className="num text-text-3">{fmt.usd(p.notional)}</span>
      <Signed value={p.pnl} arrow={false}>
        {fmt.pnl(p.pnl)}
      </Signed>
    </span>
  )
}

export function BookStrip({ positions }: { positions: QuantPosition[] }) {
  const navigate = useNavigate()
  const [hover, setHover] = useState<QuantPosition | null>(null)
  const longs = positions.filter((p) => p.weight > 0).sort((a, b) => b.weight - a.weight)
  const shorts = positions.filter((p) => p.weight < 0).sort((a, b) => a.weight - b.weight)
  const sideSum = (ps: QuantPosition[]) => ps.reduce((s, p) => s + Math.abs(p.weight), 0)
  const max = Math.max(0.01, ...positions.map((p) => Math.abs(p.pnl ?? 0)))
  const ranked = [...positions].filter((p) => p.pnl != null).sort((a, b) => (b.pnl ?? 0) - (a.pnl ?? 0))
  const best = ranked[0]
  const worst = ranked[ranked.length - 1]
  const segment = (p: QuantPosition, i: number, origin: "left" | "right") => (
    <button
      key={p.symbol}
      type="button"
      aria-label={`${ticker(p.symbol)}, ${p.side === "long" ? "лонг" : "шорт"} ${fmt.pctPlain(100 * Math.abs(p.weight), 2)}, з ребалансу ${fmt.pnl(p.pnl)}`}
      className={clsx("grow-x min-w-[3px] cursor-pointer transition-[filter] duration-150 hover:brightness-125 focus-visible:outline-1", hover && hover.symbol !== p.symbol && "brightness-[0.82]")}
      style={{ flex: `${Math.abs(p.weight)} 1 0`, background: shade(p, max), "--i": i, "--origin": origin } as CSSProperties}
      onMouseEnter={() => setHover(p)}
      onFocus={() => setHover(p)}
      onClick={() => navigate(`/bots/quant?symbol=${p.symbol}`)}
    />
  )
  return (
    <div>
      <div className="flex items-center justify-between gap-3 text-[11.5px]">
        <span className="label">
          Лонги · {longs.length} · {fmt.times(sideSum(longs))}
        </span>
        <span className="flex items-center gap-1.5">
          <span className="label">Портфель</span>
          <Tip>
            Кожна смужка — одна позиція. Ширина — частка рахунку. Колір — прибуток (зелений) чи збиток (червоний) з останнього ребалансу. Ліворуч лонги, праворуч шорти. Клацніть, щоб відкрити монету.
          </Tip>
        </span>
        <span className="label">
          {fmt.times(sideSum(shorts))} · {shorts.length} · Шорти
        </span>
      </div>
      <div className="mt-2 flex h-10 gap-px overflow-hidden rounded-md" onMouseLeave={() => setHover(null)}>
        {longs.map((p, i) => segment(p, longs.length - i, "right"))}
        <span className="w-[3px] flex-none rounded-sm bg-text" aria-hidden />
        {shorts.map((p, i) => segment(p, i, "left"))}
      </div>
      <div className="mt-2 flex min-h-5 flex-wrap items-center justify-between gap-x-4 gap-y-1 text-[12.5px] text-text-2">
        {hover ? (
          <Readout p={hover} />
        ) : (
          <>
            {best && (
              <span className="flex min-w-0 items-baseline gap-2 truncate">
                <span className="label">Найкраща</span>
                <Readout p={best} />
              </span>
            )}
            {worst && worst !== best && (
              <span className="flex min-w-0 items-baseline gap-2 truncate">
                <span className="label">Найгірша</span>
                <Readout p={worst} />
              </span>
            )}
          </>
        )}
      </div>
    </div>
  )
}
