import clsx from "clsx"
import type { ReactNode } from "react"

import { tone } from "../lib/format"

/** A signed figure in market notation: ▲/▼, sign and ink color carry the direction together, never color alone. */
export function Signed({ value, children, className, arrow = true, digits = 2 }: { value: number | null | undefined; children: ReactNode; className?: string; arrow?: boolean; digits?: number }) {
  const t = tone(value, digits)
  return (
    <span className={clsx("num whitespace-nowrap", t === "gain" && "text-gain", t === "loss" && "text-loss", className)}>
      {arrow && t !== "flat" && (
        <span aria-hidden className="mr-0.5 text-[0.78em]">
          {t === "gain" ? "▲" : "▼"}
        </span>
      )}
      {children}
    </span>
  )
}

export function KV({ rows, className }: { rows: [ReactNode, ReactNode][]; className?: string }) {
  return (
    <table className={clsx("agate", className)}>
      <tbody>
        {rows.map(([k, v], i) => (
          <tr key={i}>
            <td className="text-text-2">{k}</td>
            <td className="r">{v}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

export function ErrorNote({ error }: { error: unknown }) {
  const text = error instanceof Error ? error.message : String(error)
  return <p className="py-3 font-semibold text-text">⚠ Помилка: {text}</p>
}
