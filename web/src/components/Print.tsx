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

export function Headline({ title, dek, hue, children, as = "h2" }: { title: ReactNode; dek?: ReactNode; hue?: string; children?: ReactNode; as?: "h1" | "h2" | "h3" }) {
  const Tag = as
  return (
    <header className="flex flex-wrap items-end justify-between gap-x-6 gap-y-2 pb-2">
      <div className="min-w-0">
        <Tag className={clsx("head font-extrabold", as === "h1" ? "text-[2.6rem]" : as === "h2" ? "text-[1.75rem]" : "text-[1.25rem]")} style={hue ? { color: hue } : undefined}>
          {title}
        </Tag>
        {dek && <p className="mt-1 max-w-[70ch] text-ink-2">{dek}</p>}
      </div>
      {children && <div className="flex flex-wrap items-center gap-2">{children}</div>}
    </header>
  )
}

export function Dot({ on, live = false }: { on: boolean; live?: boolean }) {
  return (
    <span
      aria-hidden
      className={clsx("inline-block h-2 w-2 rounded-full align-middle", on ? (live ? "bg-live" : "bg-gain") : "border border-ink-3")}
    />
  )
}

export function KV({ rows, className }: { rows: [ReactNode, ReactNode][]; className?: string }) {
  return (
    <table className={clsx("agate", className)}>
      <tbody>
        {rows.map(([k, v], i) => (
          <tr key={i}>
            <td className="text-ink-2">{k}</td>
            <td className="r">{v}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="py-6 text-ink-3">{children}</p>
}

export function ErrorNote({ error }: { error: unknown }) {
  const text = error instanceof Error ? error.message : String(error)
  return <p className="border-l-0 py-3 text-loss">Помилка: {text}</p>
}
